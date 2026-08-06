"""Execution Channel and cooperative cancellation vocabulary.

The Channel is write-only: "Workers write to it; they never own it"
(``18-worker-model.md``). Modeled as ``typing.Protocol`` (design decision
D1) — a Capability Provider needs no base class to satisfy it, and a fake
channel for tests needs no import from this package.

Cancellation is cooperative (design decision D5) — a Capability Provider
polls/awaits a `CancellationToken` and itself performs acknowledge ->
cleanup -> final events -> Report. Raw `asyncio.CancelledError` would
unwind the stack and skip all four, which the Worker Contract forbids.
"""

from typing import Protocol

from tibios_ray.execution.events import ExecutionEvent


class ExecutionChannel(Protocol):
    """Write-only sink for `ExecutionEvent`s. Bounded; backpressure per
    ``05-async-concurrency.md``. Exposes no read-side method."""

    async def emit(self, event: ExecutionEvent) -> None: ...


class CancellationToken(Protocol):
    """Cooperative cancellation signal — never raised as an exception."""

    @property
    def is_cancelled(self) -> bool: ...

    async def wait(self) -> None: ...
