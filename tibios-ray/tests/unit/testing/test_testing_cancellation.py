"""Tests for `tibios_ray.testing.cancellation` — `ManualCancellation`, the
shared `CancellationToken` fake consolidating the ad-hoc `ManualCancellation`/
`_FakeCancellation`/`_NeverCancelled`/`_StaticCancellation` doubles hand-rolled
across Phase 1-5's test modules (Phase 6, `testing/`).
"""

import asyncio

from tibios_ray.execution.channel import CancellationToken
from tibios_ray.testing.cancellation import ManualCancellation


def test_satisfies_the_cancellation_token_protocol() -> None:
    token: CancellationToken = ManualCancellation()
    assert isinstance(token, ManualCancellation)


def test_starts_not_cancelled() -> None:
    token = ManualCancellation()
    assert token.is_cancelled is False


def test_cancel_flips_is_cancelled_and_is_idempotent() -> None:
    token = ManualCancellation()
    token.cancel()
    assert token.is_cancelled is True
    token.cancel()
    assert token.is_cancelled is True


def test_wait_resolves_once_cancel_is_called() -> None:
    token = ManualCancellation()

    async def scenario() -> None:
        async def cancel_soon() -> None:
            await asyncio.sleep(0)
            token.cancel()

        async with asyncio.TaskGroup() as tg:
            tg.create_task(cancel_soon())
            await token.wait()

    asyncio.run(scenario())

    assert token.is_cancelled is True


def test_wait_returns_immediately_when_already_cancelled() -> None:
    token = ManualCancellation()
    token.cancel()

    # `asyncio.Event.wait()` checks `is_set()` before ever suspending, so an
    # already-cancelled token's `wait()` completes without needing anything
    # else to run — no timeout/race needed to prove it.
    asyncio.run(token.wait())
