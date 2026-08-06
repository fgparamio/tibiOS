"""Hand-written `LlamaLike` double — "the stub is the entire SDK"
(design.md "Testing Strategy"), the `RecordingBackend`/`FakeTextBackend`
precedent (`tibios_ray.testing.backend`, `tests/unit/backends/test_text.py`)
applied to the llama.cpp engine seam. Unit tests under `tests/unit/engines/`
never import `llama_cpp`; this class satisfies `LlamaLike` structurally
in its place.

Not a test file itself (no `test_` prefix) — pytest does not collect it,
mirroring `tests/unit/*/pyright_fixtures/` non-collected support modules.
"""

import threading
from collections.abc import Iterator, Mapping, Sequence
from typing import Any


class StubLlama:
    """Slice 1 only exercised `close()` (residency round trip, `test_
    llamacpp_residency.py`). Slice 2 (streaming, `test_llamacpp_
    streaming.py`) needs `create_completion` to actually drive a
    real, pausable, sometimes-failing token stream — hence
    `block_before_index`/`block_event` (proving the pump thread runs
    off the event loop, and that the queue backpressure/lookahead is
    genuinely incremental, not "wait for the whole thing") and
    `error`/`error_before_index` (proving `_Failure` propagation,
    llamacpp-text-backend spec "Non-Blocking Thread-Bridge Streaming").

    Slice 3 (concurrency, `test_llamacpp_concurrency.py` /
    `test_llamacpp_abandonment.py`) adds three more knobs, all
    structural (no sleeps):
    - `marker`/`activity_log`/`max_active_count`: every
      `create_completion()` call logs `(marker, "enter")` on first
      execution and `(marker, "exit")` in its `finally` (so it covers
      normal exhaustion *and* `GeneratorExit` from `.close()`/
      `aclose()` alike), under a `threading.Lock`, with a live
      reentrancy counter — proving the per-session `asyncio.Lock`
      (design decision LC4) actually serializes concurrent calls on
      one stub instance instead of merely happening to not race.
    - `barrier`: when set, every call waits on it (`threading.Barrier`,
      shared across two distinct `StubLlama` instances backing two
      distinct sessions) before its first token — the mechanism that
      proves LC4's lock is per-session, not global: a global lock
      would prevent the second session's stub from ever reaching the
      barrier, timing it out.
    - `closed`: set in the same `finally` as the exit marker —
      lets a test confirm the underlying (stub) generator actually
      unwound after abandonment, not just that the consumer's async
      generator returned control (LC5/LC7).

    `block_before_index` / `error_before_index` may equal
    `len(tokens)` to pause/raise *after* the last real token, i.e.
    while the SDK generator is being asked "is there more?" — the
    point `_pump`'s `for raw in stream:` loop is parked on the third
    real-world `next()` call in a 2-token stream, not on producing a
    token itself.
    """

    def __init__(
        self,
        tokens: Sequence[str] = (),
        *,
        block_before_index: int | None = None,
        block_event: threading.Event | None = None,
        error: Exception | None = None,
        error_before_index: int | None = None,
        barrier: threading.Barrier | None = None,
        marker: str = "stub",
    ) -> None:
        self.tokens = tokens
        self.block_before_index = block_before_index
        self.block_event = block_event
        self.error = error
        self.error_before_index = error_before_index
        self.barrier = barrier
        self.marker = marker
        # Set right before parking on `block_event.wait()` — lets a test
        # deterministically wait until the pump thread has actually
        # reached the pause point, with zero timing dependence (no
        # sleeps; see design.md "Testing Strategy").
        self.parked = threading.Event()
        # Set in create_completion()'s `finally` — proves the stub's own
        # generator body actually unwound (exhaustion or GeneratorExit),
        # not merely that the consumer stopped iterating it.
        self.closed = threading.Event()
        self.close_calls = 0
        self.create_completion_calls: list[dict[str, Any]] = []
        self._activity_lock = threading.Lock()
        self.activity_log: list[tuple[str, str]] = []
        self._active_count = 0
        self.max_active_count = 0

    def create_completion(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        stop: list[str],
        stream: bool,
    ) -> Iterator[Mapping[str, Any]]:
        self.create_completion_calls.append(
            {
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stop": stop,
                "stream": stream,
            }
        )
        self._mark("enter")
        try:
            if self.barrier is not None:
                self.barrier.wait()
            for index, token in enumerate(self.tokens):
                self._maybe_raise(index)
                self._maybe_block(index)
                yield {"choices": [{"text": token}]}
            self._maybe_raise(len(self.tokens))
            self._maybe_block(len(self.tokens))
        finally:
            # Runs on exhaustion *and* on GeneratorExit (`.close()`),
            # i.e. always — including mid-stream abandonment.
            self._mark("exit")
            self.closed.set()

    def close(self) -> None:
        self.close_calls += 1

    def _maybe_raise(self, index: int) -> None:
        if self.error is not None and self.error_before_index == index:
            raise self.error

    def _maybe_block(self, index: int) -> None:
        if self.block_event is not None and self.block_before_index == index:
            self.parked.set()
            self.block_event.wait()

    def _mark(self, phase: str) -> None:
        with self._activity_lock:
            if phase == "enter":
                self._active_count += 1
                self.max_active_count = max(self.max_active_count, self._active_count)
            self.activity_log.append((self.marker, phase))
            if phase == "exit":
                self._active_count -= 1
