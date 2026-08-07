"""The llama.cpp text-generation Engine (`llamacpp-text-backend` spec) —
the concrete, SDK-bound half of boundary ③→④ in `design.md`'s canonical
data flow: `ResolvedModelRef -> LlamaCpp Engine -> Token Iterator`.

`backends/` is the contract; this module is the wiring. One class,
`LlamaCppTextBackend`, satisfies `TextGenerationBackend` structurally (no
base class, design decision D1) and turns llama.cpp's blocking sync
token generator into a non-blocking async `AsyncIterator[TextChunk]`.

Slice 1 built the residency seam: `backend_id`, `supports`, `acquire`,
`release`. Slice 2 added the real streaming implementation: `generate()`
is a thread-bridge async generator — `_pump`/`_put` run the blocking SDK
generator on a dedicated `Thread` and hand tokens across a bounded
`asyncio.Queue`, with terminal-chunk detection by one-token lookahead on
stream exhaustion (LC8), not the SDK's `finish_reason` (design.md "Slice
Plan", "Key Contracts"). Slice 6 (this file's current state) replaces
per-call `Llama` construction with a pool of `pool_size` pre-warmed
instances, built eagerly in `__init__` (ADR-0003, D26/D27,
`llamacpp-text-backend` spec "Residency Is Backend-Owned, Not
Request-Owned") — `acquire()` checks an instance out of an
`asyncio.Queue`-backed pool and never constructs one; `release()` returns
it for reuse and never closes it; exhaustion waits up to a configured
timeout then raises `PoolExhaustedError`.

Accepted, explicit limitations (design.md):
- GGUF resolution is out of band: `model_path` is supplied at
  construction, not derived from `ResolvedModelRef`. `supports()` cannot
  verify this adapter actually serves `plan.model` (deferred debt,
  precedent: `ray-worker-runtime`'s deferred `ExecutionContext`
  enrichment).
- `supports()` checks backend family only (LC12) — an Engine never
  performs model selection; that is Model Selection Policy's job,
  strictly upstream of this module (boundary ②, not ③).
"""

import asyncio
import importlib
import os
import threading
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from concurrent.futures import CancelledError
from dataclasses import dataclass, field
from threading import Thread
from typing import Any, Protocol
from uuid import uuid4

from tibios_ray.backends.adapter import BackendId, BackendSession, ServingPlanLike
from tibios_ray.backends.text import TextChunk, TextRequest

LLAMA_CPP_BACKEND_ID = BackendId("llama_cpp")

# LC6/LC7: bounded so "streamed, never buffered" is true across the
# thread boundary; poll interval for the pump thread's backpressure
# loop to notice abandonment (`stop_event`). Both are judgment calls,
# not measurements (design.md "Open Questions").
_QUEUE_MAXSIZE = 8
_PUT_POLL_SECONDS = 0.05

# D26: how long `acquire()` waits for a pool instance to free up before
# raising `PoolExhaustedError`. A documented default, not a measurement
# (design.md "Open Questions") — env-var wiring
# (`TIBIOS_RAY_LLAMACPP_ACQUIRE_TIMEOUT_SECONDS`) is deferred to whichever
# future change adds it to `config.py`; this slice exposes it as a plain
# constructor keyword.
_DEFAULT_ACQUIRE_TIMEOUT_SECONDS = 30.0


class LlamaLike(Protocol):
    """Structural shape of `llama_cpp.Llama` — the only SDK surface this
    module uses (design.md "Key Contracts"). Keyword-only parameters here
    are satisfied by the SDK's positional-or-keyword ones; extra
    defaulted SDK parameters are irrelevant to structural conformance."""

    def create_completion(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        stop: list[str],
        stream: bool,
    ) -> Iterator[Mapping[str, Any]]: ...

    def close(self) -> None: ...


type LlamaFactory = Callable[[str], LlamaLike]


def default_llama_factory(model_path: str) -> LlamaLike:
    """Constructs the real `llama_cpp.Llama`, importing the SDK lazily
    and only when this function runs (design decision LC11) — never at
    module import time. `importlib.import_module`, not a top-level
    `import llama_cpp`: `typeCheckingMode = "standard"` makes
    `reportMissingImports` an error when the optional `llamacpp` extra is
    absent, but `reportUnnecessaryTypeIgnoreComment = true` would then
    make a suppression comment itself an error once the extra *is*
    installed. `importlib.import_module` resolves that pincer — typeshed
    types `ModuleType.__getattr__ -> Any`, so pyright is green in both
    worlds with no suppression, and importing this module never touches
    the SDK."""

    try:
        llama_cpp = importlib.import_module("llama_cpp")
    except ModuleNotFoundError as error:
        raise ModuleNotFoundError(
            "llama-cpp-python is required to construct the default llama.cpp "
            "engine but is not installed. Install it with the optional extra: "
            "`uv add tibios-ray[llamacpp]` (or `pip install tibios-ray[llamacpp]`)."
        ) from error
    return llama_cpp.Llama(model_path=model_path, verbose=False)


class UnknownSessionError(LookupError):
    """Raised by `release()` for a `session_id` absent from the
    residency side table — either never acquired on this adapter
    instance, or already released (design decision LC2 makes
    `release()` authoritative and idempotent-by-rejection, not
    silently-idempotent)."""

    def __init__(self, session_id: str) -> None:
        super().__init__(f"unknown or already-released llama.cpp session: {session_id!r}")
        self.session_id = session_id


class PoolExhaustedError(Exception):
    """Raised by `acquire()` when every pooled `Llama` instance is
    checked out and none is `release()`d before `acquire_timeout`
    elapses (design decisions D26/D27; `llamacpp-text-backend` spec
    "Residency Is Backend-Owned, Not Request-Owned", scenario
    "Exhaustion waits, then fails explicitly"). The timeout bounds the
    wait for a free residency, not the duration of any inference. Since
    the timeout fires *inside* `acquire()`, no session is ever handed
    out for that attempt — `release()` is correctly never called."""

    def __init__(self, *, pool_size: int, timeout_seconds: float) -> None:
        super().__init__(
            f"llama.cpp pool exhausted: all {pool_size} instance(s) are "
            f"checked out and none was released within {timeout_seconds}s"
        )
        self.pool_size = pool_size
        self.timeout_seconds = timeout_seconds


@dataclass(slots=True)
class _Residency:
    """Per-session residency (design decision LC2): the value that never
    crosses boundary ④ — kept in a side table on the adapter, keyed by
    `session_id`, rather than as extra fields on the frozen
    `BackendSession` handle. `lock` and `thread` are mutable state,
    which is exactly why this is not `frozen=True` like `BackendSession`.
    `thread` stays `None` until `generate()` starts a pump thread for
    this session; `release()` joins it before returning the instance to
    the pool (LC9; D26 — no `close()`, the pool reuses it)."""

    llama: LlamaLike
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    thread: Thread | None = None


@dataclass(frozen=True, slots=True)
class _Token:
    """One real, non-empty raw token (design decision LC10)."""

    text: str


@dataclass(frozen=True, slots=True)
class _Failure:
    """`create_completion` raised mid-stream. Carries the **original**
    exception object so the consumer's `async for` re-raises it
    unmodified, traceback intact (LC10)."""

    error: Exception


@dataclass(frozen=True, slots=True)
class _Done:
    """The pump thread's blocking generator is exhausted. Terminal
    state is derived from this — never from the SDK's `finish_reason`
    (LC8)."""


type _QueueItem = _Token | _Failure | _Done


def _put(
    loop: asyncio.AbstractEventLoop,
    queue: asyncio.Queue[_QueueItem],
    item: _QueueItem,
    stop_event: threading.Event,
) -> bool:
    """Runs on the pump thread (design.md "Key Contracts"). Schedules
    `queue.put(item)` onto the event loop via `run_coroutine_threadsafe`
    and blocks *this* thread — the one thread allowed to block — polling
    for completion so it can notice `stop_event` (LC7 abandonment)
    instead of waiting forever on a full, undrained queue. Returns
    `False` if the put did not happen (loop closed, abandoned, or
    cancelled) — the caller must stop producing when that happens."""
    try:
        future = asyncio.run_coroutine_threadsafe(queue.put(item), loop)
    except RuntimeError:  # loop already closed
        return False
    while True:
        if stop_event.is_set():  # consumer abandoned the stream
            future.cancel()
            return False
        try:
            future.result(timeout=_PUT_POLL_SECONDS)
            return True
        except TimeoutError:
            continue
        except (CancelledError, RuntimeError):
            return False


def _pump(
    llama: LlamaLike,
    request: TextRequest,
    loop: asyncio.AbstractEventLoop,
    queue: asyncio.Queue[_QueueItem],
    stop_event: threading.Event,
) -> None:
    """Runs entirely off the event loop (LC9): drives the blocking
    `create_completion(stream=True)` generator on a dedicated `Thread`
    and hands items across the thread boundary via `_put` (LC6)."""
    try:
        stream = llama.create_completion(
            request.prompt,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            stop=list(request.stop),
            stream=True,
        )
    except Exception as error:
        _put(loop, queue, _Failure(error), stop_event)
        return

    try:
        for raw in stream:
            if stop_event.is_set():
                return
            text = raw["choices"][0]["text"]
            if text == "":  # LC8: empty-text raw chunks are dropped
                continue
            if not _put(loop, queue, _Token(text), stop_event):
                return
    except Exception as error:
        _put(loop, queue, _Failure(error), stop_event)
        return
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            close()

    _put(loop, queue, _Done(), stop_event)


class LlamaCppTextBackend:
    """The first concrete Backend Adapter (`llamacpp-text-backend` spec).
    Satisfies `TextGenerationBackend` structurally — no base class.

    Owns a pool of `pool_size` pre-warmed `Llama` instances, built
    eagerly during `__init__` (ADR-0003, D26/D27) — never lazily, never
    per-request. `acquire()` checks an instance out of the pool without
    ever constructing one; `release()` returns it for reuse."""

    def __init__(
        self,
        *,
        model_path: str,
        factory: LlamaFactory = default_llama_factory,
        pool_size: int = 1,
        acquire_timeout: float = _DEFAULT_ACQUIRE_TIMEOUT_SECONDS,
    ) -> None:
        # D27: two cheap, deterministic pre-checks, in this order, before
        # any (expensive) construction happens — a typo'd path or a
        # nonsensical pool size must never trigger even the first
        # eager `Llama` construction.
        if pool_size < 1:
            raise ValueError(f"llama.cpp pool_size must be >= 1, got {pool_size!r}")
        if not os.path.isfile(model_path):
            raise FileNotFoundError(
                f"llama.cpp model_path does not exist or is not a file: {model_path!r}"
            )
        if not os.access(model_path, os.R_OK):
            raise PermissionError(f"llama.cpp model_path is not readable: {model_path!r}")

        self._model_path = model_path
        self._factory = factory
        self._pool_size = pool_size
        self._acquire_timeout = acquire_timeout
        self._sessions: dict[str, _Residency] = {}
        # D26/D27: eager, synchronous construction of all `pool_size`
        # instances at Backend-construction time — this *is* the
        # startup viability check (a failure here propagates out of
        # `__init__`, hence out of `build_runtime()`). `asyncio.Queue`
        # does not need a running event loop to be constructed or
        # `put_nowait`-filled; only `get()`/`put()` (awaited in
        # `acquire()`/`release()`) do.
        self._pool: asyncio.Queue[LlamaLike] = asyncio.Queue(maxsize=pool_size)
        for _ in range(pool_size):
            self._pool.put_nowait(self._factory(self._model_path))

    @property
    def backend_id(self) -> BackendId:
        return LLAMA_CPP_BACKEND_ID

    def supports(self, plan: ServingPlanLike) -> bool:
        # LC12: a backend-family check only, never a model check — an
        # Engine never performs model selection (llamacpp-text-backend
        # spec, Requirement "An Engine Never Performs Model Selection").
        return plan.backend == LLAMA_CPP_BACKEND_ID

    async def acquire(self, plan: ServingPlanLike) -> BackendSession:
        # D26: no construction here — only checking an already-warm
        # instance out of the pool. Bounded wait, then an explicit
        # failure; never blocks forever (`llamacpp-text-backend` spec,
        # "Exhaustion waits, then fails explicitly").
        try:
            async with asyncio.timeout(self._acquire_timeout):
                llama = await self._pool.get()
        except TimeoutError:
            raise PoolExhaustedError(
                pool_size=self._pool_size, timeout_seconds=self._acquire_timeout
            ) from None
        session_id = f"llamacpp-{uuid4().hex}"
        self._sessions[session_id] = _Residency(llama=llama)
        return BackendSession(backend_id=LLAMA_CPP_BACKEND_ID, session_id=session_id)

    async def release(self, session: BackendSession) -> None:
        residency = self._sessions.pop(session.session_id, None)
        if residency is None:
            raise UnknownSessionError(session.session_id)

        def _stop_join() -> None:
            # LC9: `generate()`'s pump thread is joined off-loop before
            # the instance goes back to the pool. `residency.thread` is
            # `None` until the first `generate()` call populates it (or
            # if `generate()` was never called on this session), in
            # which case this is a no-op.
            if residency.thread is not None:
                residency.thread.join()

        await asyncio.to_thread(_stop_join)
        # D26: returned for reuse, never closed — instances are
        # process-scoped (ADR-0001); closing here would defeat the pool.
        self._pool.put_nowait(residency.llama)

    def _residency_for(self, session: BackendSession) -> _Residency:
        residency = self._sessions.get(session.session_id)
        if residency is None:
            raise UnknownSessionError(session.session_id)
        return residency

    async def generate(
        self, session: BackendSession, request: TextRequest
    ) -> AsyncIterator[TextChunk]:
        residency = self._residency_for(session)
        # LC4: the whole `generate()` lifetime holds the per-session
        # lock. An async generator runs no body until the first
        # `__anext__`, so *calling* generate() does not take the lock —
        # serialization begins at first iteration and ends at
        # exhaustion, `aclose()`, or cancellation.
        async with residency.lock:
            loop = asyncio.get_running_loop()
            queue: asyncio.Queue[_QueueItem] = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
            stop_event = threading.Event()
            thread = Thread(
                target=_pump,
                args=(residency.llama, request, loop, queue, stop_event),
                daemon=True,
            )
            residency.thread = thread
            try:
                thread.start()
                # LC8: one-token lookahead. `pending` is the most
                # recently dequeued real token, held back until either
                # another token arrives (not last: emit finished=False)
                # or the stream is exhausted (last: emit finished=True).
                pending: _Token | None = None
                while True:
                    item = await queue.get()
                    if isinstance(item, _Failure):
                        raise item.error
                    if isinstance(item, _Done):
                        if pending is not None:
                            yield TextChunk(text=pending.text, finished=True)
                        else:
                            yield TextChunk(text="", finished=True)
                        return
                    if pending is not None:
                        yield TextChunk(text=pending.text, finished=False)
                    pending = item
            finally:
                # LC5: no `await` here. `stop_event.set()` is
                # synchronous and infallible, so this runs on every
                # exit path (exhaustion, `aclose()`, `break`,
                # `CancelledError`, GC) without ever skipping the
                # (synchronous) lock release `async with` performs on
                # its way out. The pump thread is *not* joined here
                # (LC7) — that happens off-loop in `release()`.
                stop_event.set()
