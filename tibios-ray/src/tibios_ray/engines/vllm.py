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
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, Protocol, cast
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
    """Constructs the real `vllm.SamplingParams`, importing the SDK
    lazily (LC11/VL8 inherited) — the ~6-line quarantine VL8's
    rationale describes: the only place an SDK *type* (not just a
    factory function) gets constructed, so `generate()` itself never
    imports `vllm`."""

    try:
        sampling_params_module = importlib.import_module("vllm.sampling_params")
    except ModuleNotFoundError as error:
        raise ModuleNotFoundError(
            "vllm is required to construct the default vLLM sampling params but "
            "is not installed. Install it with the optional extra: "
            "`uv add tibios-ray[vllm]` (or `pip install tibios-ray[vllm]`)."
        ) from error
    SamplingParams = sampling_params_module.SamplingParams
    RequestOutputKind = sampling_params_module.RequestOutputKind
    return SamplingParams(
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        stop=list(request.stop),
        n=1,  # TextRequest has no `n` field; generate() only reads outputs[0]
        # VL9: not a tuning knob — a correctness requirement. Under the
        # SDK's default CUMULATIVE, every RequestOutput.outputs[0].text
        # is the *full* text so far, so emitting it as a TextChunk would
        # make the Provider concatenate the whole completion O(n) times.
        output_kind=RequestOutputKind.DELTA,  # DELTA, not CUMULATIVE — see VL9
    )


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
    pending: set[asyncio.Task[None]] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class _SessionEntry:
    """One acquired session's borrow of the shared `_ModelRuntime`
    (VL2's `_sessions: dict[session_id, _SessionEntry]`). `live` tracks
    this session's in-flight `generate()` streams, keyed by
    `request_id` (VL14) — consulted by `release()` to abort any
    stranded stream before tearing down a zero-refcount engine."""

    runtime: _ModelRuntime
    live: dict[str, AsyncGenerator[RequestOutputLike, None]] = field(default_factory=dict)


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
        # VL13: pop under the lock and raise if absent — double release,
        # a foreign session, or never-acquired all look identical here
        # (idempotent-by-rejection, LC2 inherited). Popping under the
        # lock makes a negative refcount structurally impossible: the
        # second release() of the same session never reaches the
        # decrement below.
        async with self._lock:
            entry = self._sessions.pop(session.session_id, None)
            if entry is None:
                raise UnknownSessionError(session.session_id)

            runtime = entry.runtime
            # VL13/VL14: any stream this session never drained to
            # completion is stranded — finalize (abort) it explicitly
            # rather than leaving it to the engine's GC.
            for live_request_id, live_stream in list(entry.live.items()):
                _schedule_finalize(runtime, live_stream, live_request_id, abort=True)

            runtime.refcount -= 1
            if runtime.refcount == 0:
                # Teardown while still holding the lock (VL13): a
                # concurrent acquire() either completes entirely before
                # this decrement (refcount never reaches zero, no
                # teardown) or entirely after the slot is cleared below
                # (it constructs a fresh engine) — no interleaving in
                # which a session borrows an engine being shut down.
                #
                # `release()` is the deterministic join point (VL13):
                # drain every scheduled-but-not-yet-joined finalize
                # task (this session's own, plus any left over from
                # earlier sessions of the same engine) before shutdown.
                if runtime.pending:
                    await asyncio.gather(*list(runtime.pending))
                await asyncio.to_thread(runtime.engine.shutdown)
                self._runtime = None

    async def generate(
        self, session: BackendSession, request: TextRequest
    ) -> AsyncIterator[TextChunk]:
        entry = self._session_for(session)
        request_id = f"{session.session_id}:{uuid4().hex}"
        stream = cast(
            "AsyncGenerator[RequestOutputLike, None]",
            entry.runtime.engine.generate(
                prompt=request.prompt,
                sampling_params=self._params_factory(request),
                request_id=request_id,
            ),
        )
        entry.live[request_id] = stream
        completed = False
        try:
            # VL5: no lock — concurrent multiplexed requests across
            # sessions of the same engine is the entire reason to run
            # vLLM. This async-for is the entire call path: no bridge
            # thread, no bounded queue, nothing bridging it to the loop.
            async for output in stream:
                text = output.outputs[0].text if output.outputs else ""
                if output.finished:
                    # VL10: the terminal chunk is sourced straight from
                    # the SDK's own `finished` field — no lookahead.
                    completed = True
                    yield TextChunk(text=text, finished=True)
                    return
                if text:  # drop empty non-terminal deltas
                    yield TextChunk(text=text, finished=False)
            # VL10: defensive synthetic terminator — the SDK generator
            # exhausted without ever setting finished=True.
            completed = True
            yield TextChunk(text="", finished=True)
        finally:
            # VL11: await-free — abandonment (aclose()) and task
            # cancellation both resume execution here, and a direct
            # `await` would be immediately re-cancelled under the
            # latter, silently skipping the abort. Schedule a
            # background task instead and let it be joined elsewhere
            # (release(), VL13).
            entry.live.pop(request_id, None)
            _schedule_finalize(entry.runtime, stream, request_id, abort=not completed)

    def _session_for(self, session: BackendSession) -> _SessionEntry:
        entry = self._sessions.get(session.session_id)
        if entry is None:
            raise UnknownSessionError(session.session_id)
        return entry


def _schedule_finalize(
    runtime: _ModelRuntime,
    stream: AsyncGenerator[RequestOutputLike, None],
    request_id: str,
    *,
    abort: bool,
) -> None:
    """Schedules `_finalize` as a background task and registers it in
    `runtime.pending` (VL11/VL13) — never awaited directly from
    `generate()`'s `finally`. A missing/closed loop (e.g. interpreter
    shutdown) is swallowed: there is nothing left to join it against."""

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(_finalize(runtime.engine, stream, request_id, abort=abort))
    runtime.pending.add(task)
    task.add_done_callback(runtime.pending.discard)


async def _finalize(
    engine: AsyncLLMLike,
    stream: AsyncGenerator[RequestOutputLike, None],
    request_id: str,
    *,
    abort: bool,
) -> None:
    # VL12: always issue both calls, exception-suppressed — never rely
    # on engine-side propagation across v0/v1 SDK versions.
    if abort:
        with suppress(Exception):
            await engine.abort(request_id)
    with suppress(Exception):
        await stream.aclose()


def _new_session_id() -> str:
    return f"vllm-{uuid4().hex}"
