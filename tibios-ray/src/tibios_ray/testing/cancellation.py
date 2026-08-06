"""Manual `CancellationToken` fake (`tibios_ray.execution.channel`).

Consolidates the ad-hoc `ManualCancellation`/`_FakeCancellation`/
`_NeverCancelled`/`_StaticCancellation` doubles hand-rolled across Phase 1-5's
test modules into one shared, stateful shape. Starts not-cancelled; call
`.cancel()` to flip it (and unblock any in-flight `.wait()`) — a single fake
covers both the "never cancelled" fixture (never call `.cancel()`) and the
"already cancelled" fixture (call `.cancel()` before use) that Phase 1-5's
ad-hoc doubles each modeled separately.
"""

import asyncio


class ManualCancellation:
    """A conforming `CancellationToken` (Protocol, design decision D1) whose
    cancellation is driven manually by test code rather than any real
    infrastructure."""

    def __init__(self) -> None:
        self._event = asyncio.Event()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    async def wait(self) -> None:
        await self._event.wait()

    def cancel(self) -> None:
        self._event.set()
