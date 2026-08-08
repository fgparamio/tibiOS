"""Hand-written `LLMLike` double — "the stub is the entire SDK"
(design.md "Testing Strategy"), `stub_async_llm.py`'s precedent applied
to the TensorRT-LLM engine seam. Unit tests under `tests/unit/engines/`
never import `tensorrt_llm`; this class satisfies `LLMLike` structurally
in its place.

Not a test file itself (no `test_` prefix) — pytest does not collect it,
mirroring `stub_async_llm.py`/`stub_llama.py`.

PR 2 only needs `LLMLike`/`RequestOutputLike`/`CompletionOutputLike`'s
shape to exist so PR 3 (residency: `_ModelRuntime`, `acquire`, `release`)
and PR 4 (`generate()`, cancellation) can build against a stable double
without re-touching this file's public surface.

Gotcha this stub deliberately encodes (design.md "Key Contracts"): the
real SDK's `RequestOutput` handle is the SAME object mutated in place
across `async for` iterations — unlike vLLM's `StubAsyncLLM`, which
yields a fresh `StubRequestOutput` per step. `StubRequestOutput` here is
therefore its own `__aiter__`/`__anext__` implementation: it returns
`self` and mutates `self.outputs`/`self.finished` before each yield, so
a test that (incorrectly) retained a reference to an earlier "chunk"
would see it mutate underneath it — proving the adapter must read
fields per-iteration and never retain the object.
"""

import asyncio
from collections.abc import Sequence
from typing import Any


class StubCompletionOutput:
    """`CompletionOutputLike` double — `text_diff` is the only field the
    Protocol declares (D37). `text` is an *extra* attribute this stub
    carries on top of the Protocol, set to the growing cumulative prefix
    — the "cumulative-`.text` stub" design.md's Testing Strategy calls
    for: if `generate()` ever read `.text` instead of `text_diff`, a
    test comparing emitted output against the diffs would see the
    (wrong, quadratically duplicated) cumulative value instead and
    fail — CompletionOutputLike itself never promises `.text` exists."""

    def __init__(self, text_diff: str = "", text: str = "") -> None:
        self.text_diff = text_diff
        self.text = text


class StubRequestOutput:
    """`RequestOutputLike` double — self-yielding-in-place (see module
    docstring's gotcha). Constructed with the sequence of `text_diff`
    increments `generate_async` will stream; the last increment marks
    `finished=True` unless `finished_at_exhaustion=False`, which lets a
    test exhaust the stream without ever setting `finished=True` (VL10's
    defensive-synthetic-terminator case, D34/D37 inherited)."""

    def __init__(
        self,
        diffs: Sequence[str] = (),
        *,
        finished_at_exhaustion: bool = True,
        pause_before_index: int | None = None,
        pause_event: "asyncio.Event | None" = None,
        abort_error: Exception | None = None,
    ) -> None:
        self._diffs = tuple(diffs)
        self._index = 0
        self._cumulative = ""
        self._finished_at_exhaustion = finished_at_exhaustion
        self.outputs: Sequence[StubCompletionOutput] = (StubCompletionOutput(),)
        self.finished = False
        self.abort_calls = 0
        # Async twin of `StubLlama.parked` / `stub_async_llm.py`'s
        # `paused` — lets a cancellation test wait until the stream is
        # genuinely mid-flight (parked in `__anext__`) before
        # abandoning/cancelling it, with zero timing dependence.
        self.paused = asyncio.Event()
        # Set on every `abort()` call — a test can
        # `await asyncio.wait_for(handle.abort_called.wait(), 1.0)` to
        # observe the background finalize task (D36) actually running,
        # with zero sleeps (`stub_async_llm.py`'s `abort_called` twin).
        self.abort_called = asyncio.Event()
        self._pause_before_index = pause_before_index
        self._pause_event = pause_event
        self._abort_error = abort_error

    def __aiter__(self) -> "StubRequestOutput":
        return self

    async def __anext__(self) -> "StubRequestOutput":
        if self._index >= len(self._diffs):
            raise StopAsyncIteration
        if self._pause_before_index == self._index:
            self.paused.set()
            assert self._pause_event is not None, (
                "pause_before_index set without a pause_event"
            )
            await self._pause_event.wait()
        diff = self._diffs[self._index]
        self._index += 1
        self._cumulative += diff
        self.outputs = (StubCompletionOutput(text_diff=diff, text=self._cumulative),)
        at_exhaustion = self._index == len(self._diffs)
        self.finished = self._finished_at_exhaustion and at_exhaustion
        return self

    async def abort(self) -> None:
        # D36: handle-scoped — no engine-level `abort(request_id)` exists
        # on the real SDK, so this is the entire cancellation surface.
        self.abort_calls += 1
        self.abort_called.set()
        if self._abort_error is not None:
            raise self._abort_error


class StubLLM:
    """Satisfies `LLMLike` structurally. Records `generate_async`/
    `shutdown` calls and a construction count (via
    `make_stub_engine_factory` below), mirroring `StubAsyncLLM`."""

    def __init__(self, *, model: str = "") -> None:
        self.model = model
        self.generate_calls: list[dict[str, Any]] = []
        self.shutdown_calls = 0
        # Pre-registered per-call outputs (`queue_output`), consumed in
        # FIFO order by `generate_async` — lets a test control exactly
        # what each call streams without subclassing this stub.
        self._queued_outputs: list[StubRequestOutput] = []

    def queue_output(self, output: StubRequestOutput) -> None:
        self._queued_outputs.append(output)

    def generate_async(
        self, prompt: str, sampling_params: Any, streaming: bool
    ) -> StubRequestOutput:
        self.generate_calls.append(
            {"prompt": prompt, "sampling_params": sampling_params, "streaming": streaming}
        )
        if self._queued_outputs:
            return self._queued_outputs.pop(0)
        return StubRequestOutput()

    def shutdown(self) -> None:
        self.shutdown_calls += 1


def make_stub_engine_factory(
    *, engines_made: list[StubLLM] | None = None
) -> tuple[Any, list[StubLLM]]:
    """Recording async factory (`stub_async_llm.py`'s
    `make_stub_engine_factory` precedent): each call constructs and
    records a fresh `StubLLM`, so a test can assert exactly how many
    engines were built (D34's single-flight residency, exercised
    starting PR 3)."""
    made: list[StubLLM] = engines_made if engines_made is not None else []

    async def factory(engine_path: str) -> StubLLM:
        stub = StubLLM(model=engine_path)
        made.append(stub)
        return stub

    return factory, made
