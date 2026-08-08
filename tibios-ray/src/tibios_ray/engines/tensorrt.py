"""The TensorRT-LLM text-generation Engine (`tensorrt-llm-text-backend`
spec) — the third concrete Backend Adapter for `chat.generate`,
executing against a **precompiled** engine artifact. `engines/tensorrt.py`
mirrors `engines/vllm.py` end to end (design.md "Technical Approach"):
module-local structural Protocols for the SDK surface, a lazy
`importlib` factory seam (LC11/VL8), and one shared lazily-constructed
refcounted `_ModelRuntime` (VL2, adopted wholesale per design decision
D34).

**This file's current state is PR 3 of the change's slice plan: the SDK
seam (PR 2) plus residency** — `_ModelRuntime`/`_SessionEntry`,
`TensorrtLlmTextBackend.__init__`, `backend_id`, `supports`, `acquire`
(single-flight under the lock), and `release` (refcounted teardown).
`generate()`, cancellation, and Composition Root wiring land in PR 4.

Two SDK-shape differences from `vllm.py`, both already structural in
this PR's contracts even though `generate()` itself is not implemented
yet: construction is **blocking** — `LLMLike.shutdown()`/the real
constructor are plain synchronous calls, so the default factory's body
is `await asyncio.to_thread(...)` (design decision D35) instead of
vLLM's on-loop `AsyncLLM.from_engine_args(...)` — and the incremental
token lives in a **separate field**, `CompletionOutputLike.text_diff`,
never the cumulative `.text` (design decision D37; encoded structurally
in the Protocol shape now, read at the actual call site in PR 4).

The Core Principle this Backend exists to make structural — "engine
compilation is an out-of-band operator/provisioning concern, never a
Worker responsibility" (Invariant 2 of the spec) — is enforced here by
`default_engine_factory`'s pre-flight artifact predicate (design
decision D39): the configured path must exist, be a directory, and
contain at least one compiled-engine file, checked entirely on the
filesystem, before `tensorrt_llm` is ever imported. A path that fails
this check raises `InvalidEngineArtifactError` — a module-local,
`ConfigError`-shaped failure (the real `tibios_ray.config.ConfigError`
cannot be imported here: the layering guard restricts `engines/*.py` to
importing only `tibios_ray.backends`) — instead of ever reaching a
constructor call that could otherwise start an implicit, unbounded
compilation step.
"""

import asyncio
import importlib
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from tibios_ray.backends.adapter import BackendId, BackendSession, ServingPlanLike
from tibios_ray.backends.text import TextChunk, TextRequest

TENSORRT_LLM_BACKEND_ID = BackendId("tensorrt_llm")

# D38/D39: the same env var name `config.py`'s `_TENSORRT_ENGINE_PATH`
# constant carries — duplicated here, not imported, per the layering
# guard's `engines -> backends` only rule. Naming it in the pre-flight
# failure message is what makes the failure attributable.
_ENGINE_PATH_ENV_VAR = "TIBIOS_RAY_TENSORRT_ENGINE_PATH"


class CompletionOutputLike(Protocol):
    """Structural shape of one `RequestOutput.outputs[N]` entry."""

    @property
    def text_diff(self) -> str: ...  # the DELTA (D37) — `.text` is CUMULATIVE, never read it


class RequestOutputLike(Protocol):
    """Structural shape of the handle `LLMLike.generate_async` returns —
    the handle IS the async iterator (D36), unlike vLLM's separate
    `AsyncIterator[RequestOutputLike]` return type."""

    @property
    def outputs(self) -> Sequence[CompletionOutputLike]: ...

    @property
    def finished(self) -> bool: ...  # authoritative terminator (VL10 inherited)

    def __aiter__(self) -> AsyncIterator["RequestOutputLike"]: ...

    async def abort(self) -> None: ...  # D36: handle-scoped, no engine-level abort(request_id)


class LLMLike(Protocol):
    """Structural shape of `tensorrt_llm.LLM` — the only SDK surface
    this module uses (design.md "Key Contracts")."""

    def generate_async(
        self, prompt: str, sampling_params: Any, streaming: bool
    ) -> RequestOutputLike: ...

    def shutdown(self) -> None: ...  # blocking → to_thread (D35)


type LLMFactory = Callable[[str], Awaitable[LLMLike]]  # VL7's signature, D35's body
type SamplingParamsFactory = Callable[[TextRequest], Any]  # VL8's quarantine, minus VL9's flag


class InvalidEngineArtifactError(Exception):
    """Raised by `default_engine_factory`'s D39 pre-flight predicate for
    a configured `engine_path` that does not exist, is not a directory,
    or contains no compiled-engine file. Deliberately module-local and
    shaped like `tibios_ray.config.ConfigError` (`variable`/`reason`,
    same `f"{variable!r}: {reason}"` message) rather than importing that
    class: `engines/*.py` may import only `tibios_ray.backends`, per the
    layering guard (`test_engines_layering.py`)."""

    def __init__(self, *, variable: str, reason: str) -> None:
        self.variable = variable
        self.reason = reason
        super().__init__(f"{variable!r}: {reason}")


def _check_engine_artifact(engine_path: str) -> None:
    """D39's pre-flight predicate — evaluated entirely on the
    filesystem, before `tensorrt_llm` is ever imported, so a
    misconfigured path never reaches a constructor call that could
    otherwise start an implicit, unbounded compilation step. Layout
    knowledge is deliberately shallow (design.md "Accepted, explicit
    limitations"): existence, directory-ness, and the presence of at
    least one `*.engine` file — nothing about its internal contents."""
    path = Path(engine_path)
    if not path.exists():
        raise InvalidEngineArtifactError(
            variable=_ENGINE_PATH_ENV_VAR,
            reason=f"path {engine_path!r} does not exist",
        )
    if not path.is_dir():
        raise InvalidEngineArtifactError(
            variable=_ENGINE_PATH_ENV_VAR,
            reason=f"path {engine_path!r} is not a directory",
        )
    if not any(path.glob("*.engine")):
        raise InvalidEngineArtifactError(
            variable=_ENGINE_PATH_ENV_VAR,
            reason=(
                f"directory {engine_path!r} contains no compiled engine artifact "
                "(*.engine) — point this at a precompiled TensorRT-LLM engine "
                "directory (see the Operational Model)"
            ),
        )


async def default_engine_factory(engine_path: str) -> LLMLike:
    """Constructs the real `tensorrt_llm.LLM`, importing the SDK lazily
    and only when this function runs (design decision LC11 inherited
    via VL8) — never at module import time.

    D39's pre-flight predicate runs first, entirely off the SDK. Only a
    path that passes it reaches the lazy import below.

    D35: the SDK constructor is a plain, synchronous call — unlike
    vLLM's `AsyncLLM`, it attaches no asyncio machinery to the
    constructing loop, so running it on-loop would stall the event loop
    (and therefore the gRPC transport serving every other capability)
    for the entire engine load. `asyncio.to_thread` confines that stall
    to a worker thread. Teardown is symmetric — see the `to_thread`
    call `vllm.py`'s `release()` already makes for `shutdown()`."""

    _check_engine_artifact(engine_path)
    try:
        tensorrt_llm = importlib.import_module("tensorrt_llm")
    except ModuleNotFoundError as error:
        raise ModuleNotFoundError(
            "tensorrt_llm is required to construct the default TensorRT-LLM "
            "engine but is not installed. It has no repo-wide package index "
            "(D32): install it with `uv add tibios-ray[tensorrt] --index "
            "<the NVIDIA wheel index named in pyproject.toml's tensorrt extra "
            "comment>`, or use a prebuilt NGC container image that already "
            "provides it. See the Operational Model for both channels."
        ) from error
    return await asyncio.to_thread(tensorrt_llm.LLM, model=engine_path)


def default_sampling_params_factory(request: TextRequest) -> Any:
    """Constructs the real `tensorrt_llm.SamplingParams`, importing the
    SDK lazily (LC11/VL8 inherited). Unlike vLLM's `SamplingParams`,
    no `output_kind`/DELTA flag exists to set (D37 — TensorRT-LLM solves
    cumulative-vs-delta with `CompletionOutputLike.text_diff`, a field,
    not a sampling parameter), so this factory carries only the fields
    `TextRequest` actually maps: `max_tokens`, `temperature`, `stop`,
    and `n=1` (the only index `generate()` reads)."""

    try:
        tensorrt_llm = importlib.import_module("tensorrt_llm")
    except ModuleNotFoundError as error:
        raise ModuleNotFoundError(
            "tensorrt_llm is required to construct the default TensorRT-LLM "
            "sampling params but is not installed. Install it with the "
            "optional extra: `uv add tibios-ray[tensorrt] --index <the NVIDIA "
            "wheel index named in pyproject.toml's tensorrt extra comment>` "
            "(or use a prebuilt NGC container image)."
        ) from error
    SamplingParams = tensorrt_llm.SamplingParams
    return SamplingParams(
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        stop=list(request.stop),
        n=1,  # TextRequest has no `n` field; generate() only reads outputs[0]
    )


class UnknownSessionError(LookupError):
    """Raised by `release()`/`generate()` (PR 3/PR 4) for a `session_id`
    absent from the residency side table — either never acquired on
    this adapter instance, or already released. Redefined module-locally
    rather than imported from `engines/vllm.py` (design.md "File
    Changes"): importing it would couple two engines through a module
    named after an unrelated SDK for a small win before the rule of
    three (the third engine to need this exact shape is the one that
    should extract it, per design.md's Open Questions)."""

    def __init__(self, session_id: str) -> None:
        super().__init__(f"unknown or already-released TensorRT-LLM session: {session_id!r}")
        self.session_id = session_id


@dataclass(slots=True)
class _ModelRuntime:
    """The shared, refcounted engine instance (design decision D34,
    VL2 adopted wholesale): a private collaborator owned by exactly one
    `TensorrtLlmTextBackend` instance, never exported, never injectable.
    `pending` holds scheduled-but-not-yet-joined finalize tasks (VL11),
    drained by `release()`'s teardown path (VL13) — populated starting
    in PR 4, once `generate()`/cancellation exist."""

    engine: LLMLike
    refcount: int = 0
    pending: set[asyncio.Task[None]] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class _SessionEntry:
    """One acquired session's borrow of the shared `_ModelRuntime`
    (VL2's `_sessions: dict[session_id, _SessionEntry]` inherited).
    `live` tracks this session's in-flight `generate()` streams, keyed
    by a locally-minted `stream_key` (D36) — consulted by `release()`
    to abort any stranded stream before tearing down a zero-refcount
    engine. Populated starting in PR 4."""

    runtime: _ModelRuntime
    live: dict[str, RequestOutputLike] = field(default_factory=dict)


class TensorrtLlmTextBackend:
    """The third concrete Backend Adapter (`tensorrt-llm-text-backend`
    spec). Satisfies `TextGenerationBackend` structurally — no base
    class.

    Residency is vLLM's shape, adopted wholesale (design decision D34):
    a single, lazily-constructed, refcounted Model Runtime (VL2-VL6
    inherited) shared across every acquired session of the engine
    artifact at `engine_path`. `generate()` is not implemented until
    PR 4 — the stub below exists only so pyright accepts this class as
    a `TextGenerationBackend` (VL1 precedent: PR 1 of `vllm-backend`)."""

    def __init__(
        self,
        *,
        engine_path: str,
        engine_factory: LLMFactory = default_engine_factory,
        sampling_params_factory: SamplingParamsFactory = default_sampling_params_factory,
    ) -> None:
        self._engine_path = engine_path
        self._engine_factory = engine_factory
        self._params_factory = sampling_params_factory
        self._lock = asyncio.Lock()
        self._runtime: _ModelRuntime | None = None
        self._sessions: dict[str, _SessionEntry] = {}

    @property
    def backend_id(self) -> BackendId:
        return TENSORRT_LLM_BACKEND_ID

    def supports(self, plan: ServingPlanLike) -> bool:
        # D33/VL4 inherited: identity, not selection — a backend-family
        # check only, exactly LC12's rule.
        return plan.backend == TENSORRT_LLM_BACKEND_ID

    async def acquire(self, plan: ServingPlanLike) -> BackendSession:
        # D34/VL5-VL6 inherited: the entire residency state machine —
        # construct-or-reuse, refcount increment — runs under
        # self._lock, and there is no `await` between the factory
        # returning and the slot assignment, so construction is atomic
        # w.r.t. cancellation.
        async with self._lock:
            runtime = self._runtime
            if runtime is None:
                engine = await self._engine_factory(self._engine_path)
                runtime = _ModelRuntime(engine=engine)
                self._runtime = runtime
            runtime.refcount += 1

        session_id = _new_session_id()
        self._sessions[session_id] = _SessionEntry(runtime=runtime)
        return BackendSession(backend_id=TENSORRT_LLM_BACKEND_ID, session_id=session_id)

    async def release(self, session: BackendSession) -> None:
        # D34/VL13 inherited: pop under the lock and raise if absent —
        # double release, a foreign session, or never-acquired all look
        # identical here (idempotent-by-rejection, LC2 inherited).
        # Popping under the lock makes a negative refcount structurally
        # impossible: the second release() of the same session never
        # reaches the decrement below.
        async with self._lock:
            entry = self._sessions.pop(session.session_id, None)
            if entry is None:
                raise UnknownSessionError(session.session_id)

            runtime = entry.runtime
            runtime.refcount -= 1
            if runtime.refcount == 0:
                # Teardown while still holding the lock (VL13
                # inherited): a concurrent acquire() either completes
                # entirely before this decrement (refcount never
                # reaches zero, no teardown) or entirely after the slot
                # is cleared below (it constructs a fresh engine) — no
                # interleaving in which a session borrows an engine
                # being shut down.
                #
                # `release()` is the deterministic join point (VL13):
                # drain every scheduled-but-not-yet-joined finalize
                # task before shutdown. `pending` is populated starting
                # PR 4, so this is a no-op today.
                if runtime.pending:
                    await asyncio.gather(*list(runtime.pending))
                await asyncio.to_thread(runtime.engine.shutdown)
                self._runtime = None

    async def generate(
        self, session: BackendSession, request: TextRequest
    ) -> AsyncIterator[TextChunk]:
        raise NotImplementedError("generate() lands in PR 4")
        yield  # pragma: no cover - makes this an async generator function


def _new_session_id() -> str:
    return f"tensorrt-llm-{uuid4().hex}"
