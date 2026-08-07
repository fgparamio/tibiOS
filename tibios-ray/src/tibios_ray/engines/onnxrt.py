"""The ONNX Runtime embedding/rerank Engine (`onnxruntime-backend`
spec) — the third concrete, SDK-bound half of boundary ③→④ in
`design.md`'s canonical data flow: `ResolvedModelRef -> ONNX Runtime
Engine -> Sequence[Vector] | Sequence[RerankResult]`, and the first
non-text-generation Backend Adapter.

`backends/` is the contract; this module is the wiring. Two classes,
`OnnxEmbeddingBackend` and `OnnxRerankBackend`, each satisfy exactly one
modality Protocol structurally (no base-Protocol edge, design decision
D1), over one private, shared residency implementation, `_OnnxBackendBase`
(OR5) — never exported, never a Protocol edge.

ONNX Runtime is the off-diagonal cell of the residency/bridge axes
llama.cpp and vLLM each picked one side of: **stateless and blocking**.
Residency is shared and refcounted, reusing VL2/VL6/VL13 verbatim
(OR2) — `InferenceSession` owns no per-request mutable state, so
sharing is free rather than merely convenient. The async bridge is
llama.cpp's off-loop thread hop (OR7), not vLLM's native-async
`generate()` — ORT's `run()` is a blocking call.

PR 1 (this file's current state) builds the seams: both Protocols, both
default factories, `_OnnxResidency`, and `_OnnxBackendBase`'s residency
lifecycle (`backend_id`/`supports`/`acquire`/`release`). Both public
classes exist with their execution method (`embed`/`rerank`) raising
`NotImplementedError` — PR 2 implements `_infer`, `_rows`, and the two
execution methods (design.md "Slice Plan").
"""

import asyncio
import importlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from tibios_ray.backends.adapter import BackendId, BackendSession, ServingPlanLike
from tibios_ray.backends.embedding import Vector
from tibios_ray.backends.rerank import RerankResult

ONNXRUNTIME_BACKEND_ID = BackendId("onnxruntime")

_DEFAULT_PROVIDERS: tuple[str, ...] = ("CPUExecutionProvider",)


class NodeArgLike(Protocol):
    """Structural shape of one `onnxruntime.NodeArg` — the graph's own
    declared input names are the authority for input filtering (OR8)."""

    @property
    def name(self) -> str: ...


class InferenceSessionLike(Protocol):
    """Structural shape of `onnxruntime.InferenceSession` — the only SDK
    surface this module uses (design.md "Key Contracts")."""

    def get_inputs(self) -> Sequence[NodeArgLike]: ...

    def run(
        self, output_names: Sequence[str] | None, input_feed: Mapping[str, Any]
    ) -> Sequence[Any]: ...  # OR3: called off-loop, unlocked (PR 2)


class TokenizerLike(Protocol):
    """Structural shape of `PreTrainedTokenizerBase.__call__` (OR6).
    `text_pair` is what makes cross-encoder rerank possible;
    `return_tensors="np"` is what keeps numpy out of this module."""

    def __call__(
        self,
        text: Sequence[str],
        text_pair: Sequence[str] | None = None,
        *,
        padding: bool = True,
        truncation: bool = True,
        return_tensors: str = "np",
    ) -> Mapping[str, Any]: ...


type SessionFactory = Callable[[str, Sequence[str]], InferenceSessionLike]
type TokenizerFactory = Callable[[str], TokenizerLike]


def default_session_factory(model_path: str, providers: Sequence[str]) -> InferenceSessionLike:
    """Constructs the real `onnxruntime.InferenceSession`, importing the
    SDK lazily and only when this function runs (design decision LC11/
    VL8 inherited) — never at module import time. `importlib.import_module`,
    not a top-level `import onnxruntime`: the same `reportMissingImports`/
    `reportUnnecessaryTypeIgnoreComment` pincer `llamacpp.py`/`vllm.py`
    document applies here too."""

    try:
        onnxruntime = importlib.import_module("onnxruntime")
    except ModuleNotFoundError as error:
        raise ModuleNotFoundError(
            "onnxruntime is required to construct the default ONNX Runtime "
            "session but is not installed. Install it with the optional "
            "extra: `uv add tibios-ray[onnx]` (or `pip install tibios-ray[onnx]`)."
        ) from error
    return onnxruntime.InferenceSession(model_path, providers=list(providers))


def default_tokenizer_factory(tokenizer_path: str) -> TokenizerLike:
    """Constructs the real `transformers.AutoTokenizer`, importing the
    SDK lazily (LC11/VL8 inherited) — the tokenizer is a second injected
    seam, part of residency, not lazily loaded at first `embed()` (OR6)."""

    try:
        transformers = importlib.import_module("transformers")
    except ModuleNotFoundError as error:
        raise ModuleNotFoundError(
            "transformers is required to construct the default tokenizer "
            "but is not installed. Install it with the optional extra: "
            "`uv add tibios-ray[onnx]` (or `pip install tibios-ray[onnx]`)."
        ) from error
    return transformers.AutoTokenizer.from_pretrained(tokenizer_path)


class UnknownSessionError(LookupError):
    """Raised by `release()` for a `session_id` absent from the
    residency side table — either never acquired on this adapter
    instance, or already released. Redefined module-locally again
    (VL's rationale, unchanged) — this is the third occurrence, the
    rule of three is now met, and extraction to `engines/errors.py` is
    deliberately deferred to its own change (design.md "File Changes")."""

    def __init__(self, session_id: str) -> None:
        super().__init__(f"unknown or already-released ONNX Runtime session: {session_id!r}")
        self.session_id = session_id


@dataclass(slots=True)
class _OnnxResidency:
    """The shared, refcounted residency (design decision OR2): a private
    collaborator owned by exactly one `_OnnxBackendBase` instance, never
    exported, never injectable. `input_names` is the graph's own
    declared input set, cached here at `acquire()` time so `_infer()`'s
    hot path (PR 2) is a plain set intersection (OR8)."""

    session: InferenceSessionLike
    tokenizer: TokenizerLike
    input_names: frozenset[str]
    refcount: int = 0


class _OnnxBackendBase:
    """Private residency host (OR5) — never exported, never a Protocol
    edge. `OnnxEmbeddingBackend` and `OnnxRerankBackend` each add
    exactly one execution method on top of this shared surface."""

    def __init__(
        self,
        *,
        model_path: str,
        tokenizer_path: str,
        session_factory: SessionFactory,
        tokenizer_factory: TokenizerFactory,
        providers: Sequence[str] = _DEFAULT_PROVIDERS,
        output_name: str | None = None,
    ) -> None:
        # OR10: every artifact and hardware fact is a construction
        # argument — `ServingPlanLike` gains no field, and `supports()`
        # consults none of these.
        self._model_path = model_path
        self._tokenizer_path = tokenizer_path
        self._session_factory = session_factory
        self._tokenizer_factory = tokenizer_factory
        self._providers = tuple(providers)
        self._output_name = output_name
        self._lock = asyncio.Lock()
        self._residency: _OnnxResidency | None = None
        self._sessions: dict[str, _OnnxResidency] = {}

    @property
    def backend_id(self) -> BackendId:
        return ONNXRUNTIME_BACKEND_ID

    def supports(self, plan: ServingPlanLike) -> bool:
        raise NotImplementedError  # task 1.5

    async def acquire(self, plan: ServingPlanLike) -> BackendSession:
        raise NotImplementedError  # tasks 1.6/1.7

    async def release(self, session: BackendSession) -> None:
        raise NotImplementedError  # task 1.8

    def _residency_for(self, session: BackendSession) -> _OnnxResidency:
        residency = self._sessions.get(session.session_id)
        if residency is None:
            raise UnknownSessionError(session.session_id)
        return residency


class OnnxEmbeddingBackend(_OnnxBackendBase):
    """Satisfies `EmbeddingBackend` structurally — no base-Protocol
    edge (OR5). `embed()` is implemented in PR 2 (design.md "Slice
    Plan")."""

    async def embed(self, session: BackendSession, inputs: Sequence[str]) -> Sequence[Vector]:
        raise NotImplementedError  # PR 2: `_infer`/`_rows` (OR3/OR7/OR8/OR9)


class OnnxRerankBackend(_OnnxBackendBase):
    """Satisfies `RerankBackend` structurally — no base-Protocol edge
    (OR5). `rerank()` is implemented in PR 2 (design.md "Slice Plan")."""

    async def rerank(
        self, session: BackendSession, query: str, documents: Sequence[str]
    ) -> Sequence[RerankResult]:
        raise NotImplementedError  # PR 2: `_infer`/`_rows` (OR3/OR6/OR9)


def _new_session_id() -> str:
    return f"onnxrt-{uuid4().hex}"
