"""`WorkerExecutionServicer` — the `WorkerExecution` gRPC service
implementation (`worker-grpc-transport` spec; design decisions D14, D15,
D17; correlation invariants O1-O4).

Together with `transport/server.py`, the only two modules outside
`transport/_generated/` allowed to import `grpc` or a `_pb2` symbol
(design decision D13) — every other module composes against the domain
`ExecutionContext`/`ExecutionReport`/`ExecutionEvent` types only.

`SubmitJob`'s sequence (`design.md`'s sequence diagram):
`convert.execution_context_from_wire` -> `registry.register` (O1, before
the first `await`) -> `asyncio.ensure_future(runtime.execute(...))` ->
drain the channel's wire-shaped queue, yielding one `ExecutionResponse`
per event, until `EndOfStream` is seen -> await the task's `Report` ->
yield it as the terminal, and only, report message. `finally`: no-await
cleanup (`token.cancel()`) and `registry.deregister` on every outcome
(O2). The channel Protocol has no `close()` method (unlike the design's
pseudocode) — `WorkerRuntime.execute()` already emits `EndOfStream`
unconditionally right before returning its `Report`, so draining until
`EndOfStream` is the "last item" signal this servicer needs.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator

import grpc

from tibios_ray.execution.report import ExecutionPulse
from tibios_ray.runtime.worker_runtime import WorkerRuntime
from tibios_ray.transport import convert
from tibios_ray.transport._generated.tibios.worker.v1 import worker_pb2, worker_pb2_grpc
from tibios_ray.transport.cancellation import GrpcCancellationToken
from tibios_ray.transport.channel import GrpcExecutionChannel
from tibios_ray.transport.errors import (
    ConversionError,
    CorrelationError,
    DuplicateWorkloadError,
    UnknownWorkloadError,
)
from tibios_ray.transport.registry import InFlightRegistry

_STATUS_BY_ERROR: tuple[tuple[type[Exception], grpc.StatusCode], ...] = (
    (ConversionError, grpc.StatusCode.INVALID_ARGUMENT),
    (DuplicateWorkloadError, grpc.StatusCode.ALREADY_EXISTS),
    (UnknownWorkloadError, grpc.StatusCode.NOT_FOUND),
)


def _status_code_for(error: ConversionError | CorrelationError) -> grpc.StatusCode:
    """The D17 classified-error -> gRPC status mapping: total (every
    member of both classified-error families is covered here) and fixed
    (one status per error type). Nothing this boundary raises ever falls
    through to `UNKNOWN`."""
    for error_type, status in _STATUS_BY_ERROR:
        if isinstance(error, error_type):
            return status
    raise AssertionError(f"unclassified error reached _status_code_for: {error!r}")


class WorkerExecutionServicer(worker_pb2_grpc.WorkerExecutionServicer):
    """Implements the three `WorkerExecution` RPCs against one
    `WorkerRuntime` and one in-flight `InFlightRegistry` it owns."""

    def __init__(self, runtime: WorkerRuntime) -> None:
        self._runtime = runtime
        self._registry = InFlightRegistry()

    async def SubmitJob(
        self,
        request: worker_pb2.ExecutionContext,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[worker_pb2.ExecutionResponse]:
        channel = GrpcExecutionChannel()
        cancellation = GrpcCancellationToken()
        try:
            domain_context = convert.execution_context_from_wire(
                request, channel=channel, cancellation=cancellation
            )
        except ConversionError as error:
            await context.abort(_status_code_for(error), str(error))
            return

        workload_id = domain_context.workload_id
        task = asyncio.ensure_future(self._runtime.execute(domain_context))
        try:
            self._registry.register(workload_id, cancellation, task)
        except DuplicateWorkloadError as error:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            await context.abort(_status_code_for(error), str(error))
            return

        try:
            self._registry.mark_running(workload_id)
            while True:
                wire_event = await channel.queue.get()
                yield worker_pb2.ExecutionResponse(event=wire_event)
                if wire_event.HasField("end_of_stream"):
                    break
            report = await task
            yield worker_pb2.ExecutionResponse(report=convert.execution_report_to_wire(report))
        finally:
            cancellation.cancel()
            self._registry.deregister(workload_id)

    async def Cancel(
        self, request: worker_pb2.CancelRequest, context: grpc.aio.ServicerContext
    ) -> worker_pb2.CancelAck:
        try:
            workload_id = convert.workload_id_from_cancel_request(request)
            entry = self._registry.lookup(workload_id)
        except (ConversionError, UnknownWorkloadError) as error:
            await context.abort(_status_code_for(error), str(error))
            raise AssertionError("unreachable: context.abort always raises") from None

        assert isinstance(entry.token, GrpcCancellationToken)
        entry.token.cancel()
        return worker_pb2.CancelAck()

    async def Pulse(
        self, request: worker_pb2.PulseRequest, context: grpc.aio.ServicerContext
    ) -> worker_pb2.ExecutionPulse:
        try:
            workload_id = convert.workload_id_from_pulse_request(request)
            entry = self._registry.lookup(workload_id)
        except (ConversionError, UnknownWorkloadError) as error:
            await context.abort(_status_code_for(error), str(error))
            raise AssertionError("unreachable: context.abort always raises") from None

        pulse = ExecutionPulse(phase=entry.phase, healthy=True)
        return convert.execution_pulse_to_wire(pulse)
