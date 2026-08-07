"""Tests for `tibios_ray.transport.channel` — `GrpcExecutionChannel`
(design decision D14: bounded `asyncio.Queue(maxsize=8)`, backpressure
rather than rejection).

Each emitted domain `ExecutionEvent` is wire-converted via S3b's
`execution_event_to_wire` before being enqueued — the SubmitJob response
stream (S4b) drains the wire-shaped queue directly.
"""

import asyncio

from tibios_ray.execution.events import Progress
from tibios_ray.transport.channel import GrpcExecutionChannel
from tibios_ray.transport.convert import execution_event_to_wire


def test_emit_puts_the_wire_converted_event_onto_the_queue() -> None:
    async def scenario() -> None:
        channel = GrpcExecutionChannel()
        event = Progress(fraction_complete=0.5, message="halfway")

        await channel.emit(event)

        wire_event = await channel.queue.get()
        assert wire_event == execution_event_to_wire(event)

    asyncio.run(scenario())


def test_queue_is_bounded_at_maxsize_eight() -> None:
    channel = GrpcExecutionChannel()
    assert channel.queue.maxsize == 8


def test_emit_backpressures_rather_than_raising_when_the_queue_is_full() -> None:
    async def scenario() -> None:
        channel = GrpcExecutionChannel()
        for i in range(8):
            await channel.emit(Progress(fraction_complete=i / 8))
        assert channel.queue.full()

        blocked = asyncio.create_task(channel.emit(Progress(fraction_complete=1.0)))
        await asyncio.sleep(0)
        assert not blocked.done(), "emit must await, not raise, when the queue is full"

        await channel.queue.get()
        await blocked

        assert blocked.done()
        assert blocked.exception() is None

    asyncio.run(scenario())
