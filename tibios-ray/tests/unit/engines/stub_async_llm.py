"""Hand-written `AsyncLLMLike` double — "the stub is the entire SDK"
(design.md "Testing Strategy"), `stub_llama.py`'s precedent applied to
the vLLM engine seam. Unit tests under `tests/unit/engines/` never
import `vllm`; this class satisfies `AsyncLLMLike` structurally in its
place.

Not a test file itself (no `test_` prefix) — pytest does not collect
it, mirroring `stub_llama.py`.

PR 1 only exercises construction-counting and `shutdown()` (residency
round trip, `test_vllm_residency.py`). PR 2 (streaming, cancellation)
will extend `generate()`/`abort()` with the same knobs `StubLlama`
grew across llamacpp-backend's slices — not needed yet.
"""

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
    """Satisfies `AsyncLLMLike` structurally. `generate()` is not
    exercised until PR 2 — PR 1's tests only construct instances and
    call `shutdown()`/`abort()` for refcount/teardown coverage."""

    def __init__(
        self,
        outputs: Sequence[StubRequestOutput] = (),
        *,
        shutdown_block_event: threading.Event | None = None,
        shutdown_started_event: threading.Event | None = None,
    ) -> None:
        self.outputs = outputs
        self.shutdown_calls = 0
        self.abort_calls: list[str] = []
        self.generate_calls: list[dict[str, Any]] = []
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
        for output in self.outputs:
            yield output

    async def abort(self, request_id: str) -> None:
        self.abort_calls.append(request_id)

    def shutdown(self) -> None:
        if self._shutdown_started_event is not None:
            self._shutdown_started_event.set()
        if self._shutdown_block_event is not None:
            self._shutdown_block_event.wait()
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
