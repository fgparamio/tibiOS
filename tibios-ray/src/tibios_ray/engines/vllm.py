"""The vLLM text-generation Engine (`vllm-text-backend` spec) — the
second concrete, SDK-bound half of boundary ③→④ in `design.md`'s
canonical data flow: `ResolvedModelRef -> vLLM Engine -> Token
Iterator`.

`backends/` is the contract; this module is the wiring. One class,
`VllmTextBackend`, satisfies `TextGenerationBackend` structurally (no
base class, design decision D1) — reusing LC1 (canonical boundary),
LC11 (lazy `importlib` seam) and LC12 (`supports()` is a family check)
verbatim from `llamacpp-backend`, and discarding LC2-LC9 entirely: vLLM
is natively async, so none of llama.cpp's thread-bridge machinery (pump
thread, bounded queue, `stop_event`, per-session lock, one-token
lookahead) applies here.

Where this Backend differs structurally from llama.cpp's: residency is
**shared**, not per-session. One lazily-constructed `AsyncLLM` serves
every session of the same model, refcounted by a private Model Runtime
(design decisions VL2-VL6). The lock guards residency transitions only
— never `generate()` itself (VL5, the exact inversion of LC4).

PR 1 (this file's current state) builds the Model Runtime and residency
seam: `backend_id`, `supports`, `acquire`, `release`. PR 2 adds the
real `generate()` streaming implementation, uniform cancellation, and
the sampling-params factory (VL9-VL14) — not built yet.

Accepted, explicit limitations (design.md):
- Model resolution is out of band (inherited debt, unchanged): the
  model id/path is supplied at construction, not derived from
  `ResolvedModelRef`. `supports()` cannot verify this adapter actually
  serves `plan.model` (VL4).
- Residency is per-Backend-instance, not per-process (VL2): two
  `VllmTextBackend` instances for the same model load it twice. "One
  instance per backend family" is a composition-root obligation that
  does not exist yet.
- Sessions are coupled: one shared engine means head-of-line blocking
  and a shared OOM blast radius across sessions — inherent to
  continuous batching, and the trade being bought deliberately.
- Quantization never reaches the engine: `ServingPlanLike` does not
  expose it, so it travels with the out-of-band configuration.
"""

import asyncio
import importlib
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4

from tibios_ray.backends.adapter import BackendId, BackendSession, ServingPlanLike
from tibios_ray.backends.text import TextChunk, TextRequest

VLLM_BACKEND_ID = BackendId("vllm")


class CompletionOutputLike(Protocol):
    """Structural shape of one `RequestOutput.outputs[N]` entry."""

    @property
    def text(self) -> str: ...  # the DELTA under VL9, not cumulative


class RequestOutputLike(Protocol):
    """Structural shape of one item yielded by `AsyncLLMLike.generate()`."""

    @property
    def outputs(self) -> Sequence[CompletionOutputLike]: ...

    @property
    def finished(self) -> bool: ...  # authoritative terminator (VL10)


class AsyncLLMLike(Protocol):
    """Structural shape of vLLM's `AsyncLLM` — the only SDK surface this
    module uses (design.md "Key Contracts")."""

    def generate(
        self, prompt: str, sampling_params: Any, request_id: str
    ) -> AsyncIterator[RequestOutputLike]: ...

    async def abort(self, request_id: str) -> None: ...

    def shutdown(self) -> None: ...


type AsyncLLMFactory = Callable[[str], Awaitable[AsyncLLMLike]]  # VL7: async
type SamplingParamsFactory = Callable[[TextRequest], Any]  # VL8: second seam


async def default_engine_factory(model: str) -> AsyncLLMLike:
    """Constructs the real `vllm.AsyncLLM`, importing the SDK lazily and
    only when this function runs (design decision LC11 inherited via
    VL8) — never at module import time. `importlib.import_module`, not
    a top-level `import vllm`: the same `reportMissingImports` /
    `reportUnnecessaryTypeIgnoreComment` pincer `llamacpp.py` documents
    applies here too, and the wheel is far heavier (torch, CUDA)."""

    try:
        vllm = importlib.import_module("vllm")
    except ModuleNotFoundError as error:
        raise ModuleNotFoundError(
            "vllm is required to construct the default vLLM engine but is "
            "not installed. Install it with the optional extra: "
            "`uv add tibios-ray[vllm]` (or `pip install tibios-ray[vllm]`)."
        ) from error
    engine_args = vllm.AsyncEngineArgs(model=model)
    return vllm.AsyncLLM.from_engine_args(engine_args)


def default_sampling_params_factory(request: TextRequest) -> Any:
    """PR 2 (task 2.3) — not implemented yet. Placeholder so the module
    exposes the name design.md's "Key Contracts" documents; raises if
    reached before PR 2 lands."""
    raise NotImplementedError("default_sampling_params_factory lands in PR 2 (task 2.3)")


class UnknownSessionError(LookupError):
    """Raised by `release()`/`generate()` for a `session_id` absent from
    the residency side table — either never acquired on this adapter
    instance, or already released. Redefined module-locally rather than
    imported from `engines/llamacpp.py` (design.md "File Changes"):
    importing it would couple two engines through a module named after
    an unrelated SDK for a 12-line win before the rule of three."""

    def __init__(self, session_id: str) -> None:
        super().__init__(f"unknown or already-released vLLM session: {session_id!r}")
        self.session_id = session_id


@dataclass(slots=True)
class _ModelRuntime:
    """The shared, refcounted engine instance (design decision VL2): a
    private collaborator owned by exactly one `VllmTextBackend`
    instance, never exported, never injectable. `pending` holds
    scheduled-but-not-yet-joined finalize tasks (VL11), drained by
    `release()`'s teardown path (VL13) — populated starting in PR 2."""

    engine: AsyncLLMLike
    refcount: int = 0
    pending: set[Any] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class _SessionEntry:
    """One acquired session's borrow of the shared `_ModelRuntime`
    (VL2's `_sessions: dict[session_id, _SessionEntry]`). `live` starts
    empty and is populated by `generate()` in PR 2 (VL14)."""

    runtime: _ModelRuntime


class VllmTextBackend:
    """The second concrete Backend Adapter (`vllm-text-backend` spec).
    Satisfies `TextGenerationBackend` structurally — no base class.

    Unlike `LlamaCppTextBackend`'s one-engine-per-session shape, this
    Backend owns a single, lazily-constructed, refcounted Model Runtime
    (design decisions VL2-VL6) shared across every acquired session of
    `model`. `generate()` is not implemented until PR 2."""

    def __init__(
        self,
        *,
        model: str,
        engine_factory: AsyncLLMFactory = default_engine_factory,
        sampling_params_factory: SamplingParamsFactory = default_sampling_params_factory,
    ) -> None:
        self._model = model
        self._engine_factory = engine_factory
        self._params_factory = sampling_params_factory
        self._lock = asyncio.Lock()
        self._runtime: _ModelRuntime | None = None
        self._sessions: dict[str, _SessionEntry] = {}

    @property
    def backend_id(self) -> BackendId:
        return VLLM_BACKEND_ID

    def supports(self, plan: ServingPlanLike) -> bool:
        # VL4: identity, not selection — a backend-family check only,
        # exactly LC12's rule inherited unchanged.
        return plan.backend == VLLM_BACKEND_ID

    async def acquire(self, plan: ServingPlanLike) -> BackendSession:
        # VL5/VL6: the entire residency state machine — construct-or-
        # reuse, refcount increment — runs under self._lock, and there
        # is no `await` between the factory returning and the slot
        # assignment, so construction is atomic w.r.t. cancellation.
        async with self._lock:
            runtime = self._runtime
            if runtime is None:
                engine = await self._engine_factory(self._model)
                runtime = _ModelRuntime(engine=engine)
                self._runtime = runtime
            runtime.refcount += 1

        session_id = _new_session_id()
        self._sessions[session_id] = _SessionEntry(runtime=runtime)
        return BackendSession(backend_id=VLLM_BACKEND_ID, session_id=session_id)

    async def release(self, session: BackendSession) -> None:
        raise NotImplementedError("release() lands in task 1.8")

    async def generate(
        self, session: BackendSession, request: TextRequest
    ) -> AsyncIterator[TextChunk]:
        raise NotImplementedError("generate() lands in PR 2")
        yield  # pragma: no cover - makes this an async generator function


def _new_session_id() -> str:
    return f"vllm-{uuid4().hex}"
