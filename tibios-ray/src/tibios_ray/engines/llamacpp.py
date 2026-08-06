"""The llama.cpp text-generation Engine (`llamacpp-text-backend` spec) —
the concrete, SDK-bound half of boundary ③→④ in `design.md`'s canonical
data flow: `ResolvedModelRef -> LlamaCpp Engine -> Token Iterator`.

`backends/` is the contract; this module is the wiring. One class,
`LlamaCppTextBackend`, satisfies `TextGenerationBackend` structurally (no
base class, design decision D1) and turns llama.cpp's blocking sync
token generator into a non-blocking async `AsyncIterator[TextChunk]`.

Slice 1 built the residency seam: `backend_id`, `supports`, `acquire`,
`release`. Slice 2 (this file's current state) adds the real streaming
implementation: `generate()` is a thread-bridge async generator —
`_pump`/`_put` run the blocking SDK generator on a dedicated `Thread`
and hand tokens across a bounded `asyncio.Queue`, with terminal-chunk
detection by one-token lookahead on stream exhaustion (LC8), not the
SDK's `finish_reason` (design.md "Slice Plan", "Key Contracts").

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


@dataclass(slots=True)
class _Residency:
    """Per-session residency (design decision LC2): the value that never
    crosses boundary ④ — kept in a side table on the adapter, keyed by
    `session_id`, rather than as extra fields on the frozen
    `BackendSession` handle. `lock` and `thread` are mutable state,
    which is exactly why this is not `frozen=True` like `BackendSession`.
    `thread` stays `None` until `generate()` starts a pump thread for
    this session; `release()` joins it before `close()` (LC9)."""

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
    Satisfies `TextGenerationBackend` structurally — no base class."""

    def __init__(self, *, model_path: str, factory: LlamaFactory = default_llama_factory) -> None:
        self._model_path = model_path
        self._factory = factory
        self._sessions: dict[str, _Residency] = {}

    @property
    def backend_id(self) -> BackendId:
        return LLAMA_CPP_BACKEND_ID

    def supports(self, plan: ServingPlanLike) -> bool:
        # LC12: a backend-family check only, never a model check — an
        # Engine never performs model selection (llamacpp-text-backend
        # spec, Requirement "An Engine Never Performs Model Selection").
        return plan.backend == LLAMA_CPP_BACKEND_ID

    async def acquire(self, plan: ServingPlanLike) -> BackendSession:
        # LC3: loading GGUF weights is seconds-to-minutes of blocking
        # I/O, so construction runs off the event loop, and one `Llama`
        # is built per call — that per-call independence is what makes
        # LC4's per-session (not per-process) locking claim real.
        llama = await asyncio.to_thread(self._factory, self._model_path)
        session_id = f"llamacpp-{uuid4().hex}"
        self._sessions[session_id] = _Residency(llama=llama)
        return BackendSession(backend_id=LLAMA_CPP_BACKEND_ID, session_id=session_id)

    async def release(self, session: BackendSession) -> None:
        residency = self._sessions.pop(session.session_id, None)
        if residency is None:
            raise UnknownSessionError(session.session_id)

        def _stop_join_close() -> None:
            # LC9: `generate()`'s pump thread is joined before
            # `close()`, off-loop, in this single `to_thread` call.
            # `residency.thread` is `None` until the first `generate()`
            # call populates it (or if `generate()` was never called on
            # this session), in which case this is a no-op.
            if residency.thread is not None:
                residency.thread.join()
            residency.llama.close()

        await asyncio.to_thread(_stop_join_close)

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
