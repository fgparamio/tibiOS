"""Integration test: a real `grpc.aio.server()` on an ephemeral loopback
port, driven by a real client stub (`design.md` Testing Strategy —
Integration row; task 4b.15).

Unlike `test_llamacpp_smoke.py`, this test needs no external SDK or
hardware boundary — a loopback socket and a stub Capability Provider are
enough to prove the whole wire round trip (`transport.serve` +
`WorkerExecutionServicer` + real `grpc.aio` client) that
`tests/unit/transport/test_servicer.py` only exercises through a fake
`ServicerContext`. It runs unconditionally, in the default `uv run
pytest` invocation, not gated behind an environment variable.
"""

import asyncio
import contextlib
import socket
from datetime import timedelta

import grpc
import pytest
from google.protobuf import duration_pb2

from tibios_ray.capabilities.descriptor import CapabilityDescriptor, ModelFamily
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.execution.context import ExecutionContext
from tibios_ray.execution.events import Progress
from tibios_ray.execution.report import ExecutionPhase, ExecutionReport
from tibios_ray.runtime.registry import CapabilityRegistry
from tibios_ray.runtime.worker_runtime import WorkerRuntime
from tibios_ray.testing.provider import StubProvider
from tibios_ray.transport import serve
from tibios_ray.transport._generated.tibios.primitives.v1 import identity_pb2
from tibios_ray.transport._generated.tibios.worker.v1 import worker_pb2, worker_pb2_grpc

_ULID_WORKLOAD = "01J0000000000000000000000A"
_ULID_ALLOCATION = "01J0000000000000000000000B"
_CAPABILITY = CapabilityName("chat.generate")


def _free_port() -> int:
    """Binds to an OS-assigned ephemeral port, then releases it — the
    standard "steal a free port" trick, since `transport.serve()` itself
    reports no port back to its caller (it only accepts an address)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _well_formed_execution_context_message() -> worker_pb2.ExecutionContext:
    duration = duration_pb2.Duration()
    duration.FromTimedelta(timedelta(minutes=5))
    return worker_pb2.ExecutionContext(
        workload_id=identity_pb2.WorkloadId(value=_ULID_WORKLOAD),
        allocation_id=identity_pb2.AllocationId(value=_ULID_ALLOCATION),
        allocation_contract=worker_pb2.AllocationContract(max_execution_duration=duration),
        security_context=worker_pb2.SecurityContext(
            tenant_id="tenant-a", principal_id="principal-a", grant_scope=["read"]
        ),
        observability_context=worker_pb2.ObservabilityContext(
            trace_id="trace-a", span_id="span-a"
        ),
        worker_capability=worker_pb2.WorkerCapability(value=_CAPABILITY.value),
    )


def _descriptor() -> CapabilityDescriptor:
    return CapabilityDescriptor(capability=_CAPABILITY, families=frozenset({ModelFamily("qwen")}))


def test_submit_job_cancel_and_pulse_round_trip_over_a_real_socket() -> None:
    """4b.15: `SubmitJob` yields a `Progress` event then, once cancelled,
    exactly one terminal `ExecutionReport` last on the stream; `Cancel`
    returns `CancelAck` and reaches the Provider's own `CancellationToken`
    (proven by the Provider observing it and returning `CANCELLED`);
    `Pulse` reports the in-flight phase and health while running."""

    async def scenario() -> None:
        reached_cancellation = asyncio.Event()

        async def on_execute(context: ExecutionContext) -> ExecutionReport:
            await context.channel.emit(Progress(fraction_complete=0.0, message="working"))
            await context.cancellation.wait()
            reached_cancellation.set()
            return ExecutionReport(
                phase=ExecutionPhase.CANCELLED,
                duration=timedelta(),
                resource_usage={},
                metrics={},
                trace_id="trace",
            )

        provider = StubProvider(capability_descriptor=_descriptor(), on_execute=on_execute)
        runtime = WorkerRuntime(CapabilityRegistry([provider]))
        address = f"127.0.0.1:{_free_port()}"

        server_task = asyncio.ensure_future(serve(runtime, address))
        await asyncio.sleep(0.05)  # let start() complete before a client connects

        try:
            async with grpc.aio.insecure_channel(address) as channel:
                stub = worker_pb2_grpc.WorkerExecutionStub(channel)
                request = _well_formed_execution_context_message()

                call = stub.SubmitJob(request)
                message_iter = call.__aiter__()
                first_response = await message_iter.__anext__()
                assert first_response.WhichOneof("payload") == "event"
                assert first_response.event.HasField("progress")

                pulse = await stub.Pulse(
                    worker_pb2.PulseRequest(workload_id=request.workload_id)
                )
                assert pulse.phase == worker_pb2.EXECUTION_PHASE_RUNNING
                assert pulse.healthy is True

                ack = await stub.Cancel(
                    worker_pb2.CancelRequest(workload_id=request.workload_id)
                )
                assert isinstance(ack, worker_pb2.CancelAck)
                await reached_cancellation.wait()

                remaining = [response async for response in message_iter]

                assert [r.WhichOneof("payload") for r in remaining] == ["event", "report"]
                assert remaining[0].event.HasField("end_of_stream")
                assert remaining[1].report.final_phase == worker_pb2.EXECUTION_PHASE_CANCELLED

                # Deregistered on every outcome (O2) — a Pulse issued after
                # the stream has fully drained finds nothing.
                with pytest.raises(grpc.aio.AioRpcError) as exc_info:
                    await stub.Pulse(worker_pb2.PulseRequest(workload_id=request.workload_id))
                assert exc_info.value.code() == grpc.StatusCode.NOT_FOUND
        finally:
            server_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await server_task

    asyncio.run(scenario())
