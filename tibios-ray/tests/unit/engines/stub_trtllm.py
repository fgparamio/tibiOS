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

from collections.abc import Sequence
from typing import Any


class StubCompletionOutput:
    """`CompletionOutputLike` double — `text_diff` only (D37; no
    cumulative `.text` field exists on the real SDK type this module
    uses, so none is modeled here either)."""

    def __init__(self, text_diff: str = "") -> None:
        self.text_diff = text_diff


class StubRequestOutput:
    """`RequestOutputLike` double — self-yielding-in-place (see module
    docstring's gotcha). Constructed with the sequence of `text_diff`
    increments `generate_async` will stream; the last increment marks
    `finished=True`."""

    def __init__(self, diffs: Sequence[str] = ()) -> None:
        self._diffs = tuple(diffs)
        self._index = 0
        self.outputs: Sequence[StubCompletionOutput] = (StubCompletionOutput(),)
        self.finished = False
        self.abort_calls = 0

    def __aiter__(self) -> "StubRequestOutput":
        return self

    async def __anext__(self) -> "StubRequestOutput":
        if self._index >= len(self._diffs):
            raise StopAsyncIteration
        diff = self._diffs[self._index]
        self._index += 1
        self.outputs = (StubCompletionOutput(text_diff=diff),)
        self.finished = self._index == len(self._diffs)
        return self

    async def abort(self) -> None:
        # D36: handle-scoped — no engine-level `abort(request_id)` exists
        # on the real SDK, so this is the entire cancellation surface.
        self.abort_calls += 1


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
