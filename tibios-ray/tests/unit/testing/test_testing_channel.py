"""Tests for `tibios_ray.testing.channel` — `InMemoryExecutionChannel`, the
shared `ExecutionChannel` fake consolidating the ad-hoc `RecordingChannel`/
`_RecordingChannel`/`_FakeChannel`/`_NullChannel` doubles hand-rolled across
Phase 1-5's test modules (Phase 6, `testing/`).
"""

import asyncio

from tibios_ray.execution.channel import ExecutionChannel
from tibios_ray.execution.events import EndOfStream, OutputChunk
from tibios_ray.testing.channel import InMemoryExecutionChannel


def test_satisfies_the_execution_channel_protocol() -> None:
    channel: ExecutionChannel = InMemoryExecutionChannel()
    assert isinstance(channel, InMemoryExecutionChannel)


def test_starts_with_no_emitted_events() -> None:
    channel = InMemoryExecutionChannel()
    assert channel.emitted == []


def test_emit_records_every_event_in_order() -> None:
    async def scenario() -> InMemoryExecutionChannel:
        channel = InMemoryExecutionChannel()
        await channel.emit(OutputChunk(data=b"hi", sequence=0))
        await channel.emit(EndOfStream())
        return channel

    channel = asyncio.run(scenario())

    assert channel.emitted == [OutputChunk(data=b"hi", sequence=0), EndOfStream()]
