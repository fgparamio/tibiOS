"""Tests for `tibios_ray.execution.channel` — `ExecutionChannel` (write-only)
and `CancellationToken` (cooperative cancellation, design decision D5).

Both are `typing.Protocol`s (structural contracts, no base class per design
decision D1) — tests exercise conforming fakes rather than the Protocol
classes themselves. Fakes come from `tibios_ray.testing` (Phase 6) — this
module is their origin (`RecordingChannel`/`ManualCancellation` were first
hand-rolled here), now deduped to the shared `InMemoryExecutionChannel`/
`ManualCancellation`.
"""

import asyncio

from tibios_ray.execution.channel import CancellationToken, ExecutionChannel
from tibios_ray.execution.events import EndOfStream, OutputChunk
from tibios_ray.testing import InMemoryExecutionChannel, ManualCancellation


def test_recording_channel_satisfies_execution_channel_protocol() -> None:
    channel: ExecutionChannel = InMemoryExecutionChannel()
    assert isinstance(channel, InMemoryExecutionChannel)


def test_manual_cancellation_satisfies_cancellation_token_protocol() -> None:
    token: CancellationToken = ManualCancellation()
    assert isinstance(token, ManualCancellation)


def test_channel_emit_is_write_only_and_records_events() -> None:
    async def scenario() -> InMemoryExecutionChannel:
        channel = InMemoryExecutionChannel()
        await channel.emit(OutputChunk(data=b"hi", sequence=0))
        await channel.emit(EndOfStream())
        return channel

    channel = asyncio.run(scenario())

    assert [event.type for event in channel.emitted] == ["output_chunk", "end_of_stream"]
    # Write-only: ExecutionChannel exposes no read-side method — only `emit`.
    assert not hasattr(ExecutionChannel, "read")
    assert not hasattr(ExecutionChannel, "receive")


def test_cancellation_token_starts_not_cancelled_then_wait_resolves_on_cancel() -> None:
    token = ManualCancellation()
    assert token.is_cancelled is False

    async def scenario() -> None:
        async def cancel_soon() -> None:
            await asyncio.sleep(0)
            token.cancel()

        async with asyncio.TaskGroup() as tg:
            tg.create_task(cancel_soon())
            await token.wait()

    asyncio.run(scenario())

    assert token.is_cancelled is True
