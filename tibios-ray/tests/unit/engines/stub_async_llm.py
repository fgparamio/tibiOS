"""Hand-written `AsyncLLMLike` double — "the stub is the entire SDK"
(design.md "Testing Strategy"), `stub_llama.py`'s precedent applied to
the vLLM engine seam. Unit tests under `tests/unit/engines/` never
import `vllm`; this class satisfies `AsyncLLMLike` structurally in its
place.

Not a test file itself (no `test_` prefix) — pytest does not collect
it, mirroring `stub_llama.py`.

PR 1 only exercised construction-counting and `shutdown()` (residency
round trip, `test_vllm_residency.py`). PR 2 extends `generate()`/
`abort()` with pause/abort/close instrumentation, the async-native
analog of `StubLlama`'s `block_before_index`/`block_event` knobs
(`stub_llama.py`'s precedent) — `asyncio.Event`, not `threading.Event`,
because vLLM's `generate()` is a native async generator with no thread
boundary to cross (design.md "Technical Approach": LC2-LC9 discarded).
"""

import asyncio
import threading
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class StubCompletionOutput:
    text: str = ""


@dataclass(frozen=True, slots=True)
class StubRequestOutput:
    outputs: Sequence[StubCompletionOutput] = field(default_factory=tuple)
    finished: bool = False


class StubAsyncLLM:
    """Satisfies `AsyncLLMLike` structurally."""

    def __init__(
        self,
        outputs: Sequence[StubRequestOutput] = (),
        *,
        shutdown_block_event: threading.Event | None = None,
        shutdown_started_event: threading.Event | None = None,
        pause_before_index: int | None = None,
        pause_event: "asyncio.Event | None" = None,
        abort_error: Exception | None = None,
    ) -> None:
        self.outputs = outputs
        self.shutdown_calls = 0
        self.abort_calls: list[str] = []
        self.generate_calls: list[dict[str, Any]] = []
        # Ordered, cross-method call log (design.md VL13's deterministic
        # join) — lets a test assert "abort happened before shutdown"
        # without depending on wall-clock timing.
        self.call_log: list[str] = []
        # Set inside `abort()` on every call — a test can
        # `await asyncio.wait_for(stub.abort_called.wait(), 1.0)` to
        # observe the background finalize task (VL11) actually running,
        # with zero sleeps.
        self.abort_called = asyncio.Event()
        # Populated in `generate()`'s own `finally` — proves the SDK
        # stream's body actually unwound (exhaustion or `aclose()`),
        # not merely that the consumer stopped iterating it. Mirrors
        # `StubLlama.closed`.
        self.closed_request_ids: list[str] = []
        # Set once `generate()` reaches `pause_before_index` and is
        # about to park on `pause_event` — lets a test wait until the
        # stub is genuinely mid-stream before cancelling/abandoning it,
        # with zero timing dependence (`StubLlama.parked`'s async twin).
        self.paused = asyncio.Event()
        self._pause_before_index = pause_before_index
        self._pause_event = pause_event
        self._abort_error = abort_error
        # `shutdown()` runs on a worker thread (`asyncio.to_thread`, VL13
        # teardown), so this is a `threading.Event`, not `asyncio.Event`
        # — lets a test park `shutdown()` mid-call and observe ordering
        # against a concurrent `acquire()` (`test_vllm_teardown_race.py`).
        self._shutdown_block_event = shutdown_block_event
        self._shutdown_started_event = shutdown_started_event

    async def generate(
        self, prompt: str, sampling_params: Any, request_id: str
    ) -> AsyncIterator[StubRequestOutput]:
        self.generate_calls.append(
            {"prompt": prompt, "sampling_params": sampling_params, "request_id": request_id}
        )
        try:
            for index, output in enumerate(self.outputs):
                if self._pause_before_index == index:
                    self.paused.set()
                    assert self._pause_event is not None, (
                        "pause_before_index set without a pause_event"
                    )
                    await self._pause_event.wait()
                yield output
        finally:
            self.closed_request_ids.append(request_id)

    async def abort(self, request_id: str) -> None:
        self.abort_calls.append(request_id)
        self.call_log.append("abort")
        self.abort_called.set()
        if self._abort_error is not None:
            raise self._abort_error

    def shutdown(self) -> None:
        if self._shutdown_started_event is not None:
            self._shutdown_started_event.set()
        if self._shutdown_block_event is not None:
            self._shutdown_block_event.wait()
        self.call_log.append("shutdown")
        self.shutdown_calls += 1


def make_stub_engine_factory(
    *, engines_made: list[StubAsyncLLM] | None = None
) -> tuple[Any, list[StubAsyncLLM]]:
    """Recording async factory (`stub_llama.py`'s `_backend_with_stubs`
    precedent): each call constructs and records a fresh `StubAsyncLLM`,
    so a test can assert exactly how many engines were built."""
    made: list[StubAsyncLLM] = engines_made if engines_made is not None else []

    async def factory(model: str) -> StubAsyncLLM:
        stub = StubAsyncLLM()
        made.append(stub)
        return stub

    return factory, made
