"""Tests for `tibios_ray.transport.cancellation` — the transport-minted
`CancellationToken` (design decision D15).

Not `tibios_ray.testing.cancellation.ManualCancellation`: production code
importing a test double would be a layering inversion. This is the
implementation S4b's `Cancel` RPC handler actually drives.
"""

import asyncio

from tibios_ray.transport.cancellation import GrpcCancellationToken


def test_starts_uncancelled() -> None:
    token = GrpcCancellationToken()
    assert token.is_cancelled is False


def test_wait_returns_once_cancel_is_called() -> None:
    async def scenario() -> None:
        token = GrpcCancellationToken()
        waiter = asyncio.create_task(token.wait())
        await asyncio.sleep(0)
        assert not waiter.done()

        token.cancel()
        await waiter

        assert waiter.done()
        assert token.is_cancelled is True

    asyncio.run(scenario())


def test_cancel_called_twice_does_not_raise() -> None:
    token = GrpcCancellationToken()
    token.cancel()
    token.cancel()
    assert token.is_cancelled is True
