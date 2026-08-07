"""`GrpcExecutionChannel` — the transport's `ExecutionChannel`
implementation (design decision D14).

Each emitted domain `ExecutionEvent` is wire-converted via S3b's
`execution_event_to_wire`, then put onto a bounded `asyncio.Queue`
(`maxsize=8`) — the SubmitJob response stream (S4b) drains it. `emit`
backpressures rather than rejects when the queue is full: it uses plain
`asyncio.Queue.put` (awaited), never `put_nowait`, mirroring the
engine-hop precedent (``05-async-concurrency.md``'s backpressure rule,
LC6).
"""

import asyncio

from tibios_ray.execution.events import ExecutionEvent
from tibios_ray.transport._generated.tibios.worker.v1 import worker_pb2
from tibios_ray.transport.convert import execution_event_to_wire

_QUEUE_MAXSIZE = 8


class GrpcExecutionChannel:
    """A conforming `ExecutionChannel` (Protocol, design decision D1)
    that wire-converts and enqueues every emitted event."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[worker_pb2.ExecutionEvent] = asyncio.Queue(
            maxsize=_QUEUE_MAXSIZE
        )

    async def emit(self, event: ExecutionEvent) -> None:
        await self.queue.put(execution_event_to_wire(event))
