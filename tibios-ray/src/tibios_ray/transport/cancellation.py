"""Transport-minted `CancellationToken` (design decision D15).

The token must be minted by the transport itself, never imported from
`testing/` — production code importing a test double is a layering
inversion (`tibios_ray.testing.cancellation.ManualCancellation` is the
test-only equivalent, driven manually by test code). `cancel()` is
idempotent: calling it twice, or on an already-cancelled but still
registered token, never raises (D15 — "`Cancel` is idempotent while
registered", tibios-core D11).
"""

import asyncio


class GrpcCancellationToken:
    """A conforming `CancellationToken` (Protocol, design decision D1)
    driven by the transport's `Cancel` RPC handler (S4b)."""

    def __init__(self) -> None:
        self._event = asyncio.Event()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    async def wait(self) -> None:
        await self._event.wait()

    def cancel(self) -> None:
        self._event.set()
