"""Tests for `tibios_ray.transport.servicer` — `WorkerExecutionServicer`
(`worker-grpc-transport` spec; design decisions D14, D15, D17;
correlation invariants O1-O4).

Drives the servicer's async-generator/coroutine methods directly against
a fake `grpc.aio.ServicerContext` — no real socket, no real server
(`tests/integration/test_grpc_surface.py` covers the real-server round
trip). `StubProvider` (`testing/provider.py`) stands in for a Capability
Provider so these tests observe the servicer's own behavior, not a real
backend's.
"""

import asyncio
from collections.abc import Sequence
from datetime import timedelta
from typing import cast

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
from tibios_ray.transport._generated.tibios.primitives.v1 import identity_pb2
from tibios_ray.transport._generated.tibios.worker.v1 import worker_pb2
from tibios_ray.transport.errors import ErrorClass
from tibios_ray.transport.servicer import WorkerExecutionServicer

_ULID_A = "01J0000000000000000000000A"
_ULID_B = "01J0000000000000000000000B"
_CAPABILITY = CapabilityName("chat.generate")


class _FakeContext:
    """Fake `grpc.aio.ServicerContext`: records the abort and raises, like
    the real `context.abort()` (typed `-> NoReturn`, always raises). Not a
    structural match for the real (abstract) `ServicerContext` — callers
    narrow it via `_as_context()` at the servicer-call boundary, the
    standard escape hatch for a test double of an `abc.ABC`."""

    def __init__(self) -> None:
        self.aborted: tuple[grpc.StatusCode, str] | None = None

    async def abort(self, code: grpc.StatusCode, details: str = "") -> None:
        self.aborted = (code, details)
        raise grpc.aio.AbortError(details)


def _as_context(fake: _FakeContext) -> grpc.aio.ServicerContext:
    return cast(grpc.aio.ServicerContext, fake)


def _well_formed_execution_context_message(
    workload_id: str = _ULID_A,
) -> worker_pb2.ExecutionContext:
    duration = duration_pb2.Duration()
    duration.FromTimedelta(timedelta(minutes=5))
    return worker_pb2.ExecutionContext(
        workload_id=identity_pb2.WorkloadId(value=workload_id),
        allocation_id=identity_pb2.AllocationId(value=_ULID_B),
        allocation_contract=worker_pb2.AllocationContract(max_execution_duration=duration),
        security_context=worker_pb2.SecurityContext(
            tenant_id="tenant-a", principal_id="principal-a", grant_scope=["read"]
        ),
        observability_context=worker_pb2.ObservabilityContext(
            trace_id="trace-a", span_id="span-a"
        ),
        worker_capability=worker_pb2.WorkerCapability(value=_CAPABILITY.value),
    )


def _report(phase: ExecutionPhase = ExecutionPhase.COMPLETED) -> ExecutionReport:
    return ExecutionReport(
        phase=phase, duration=timedelta(), resource_usage={}, metrics={}, trace_id="trace"
    )


def _servicer(providers: Sequence[StubProvider]) -> WorkerExecutionServicer:
    registry = CapabilityRegistry(providers)
    return WorkerExecutionServicer(WorkerRuntime(registry))


def _descriptor() -> CapabilityDescriptor:
    return CapabilityDescriptor(capability=_CAPABILITY, families=frozenset({ModelFamily("qwen")}))


async def _drain(
    servicer: WorkerExecutionServicer,
    request: worker_pb2.ExecutionContext,
    context: _FakeContext,
) -> list[worker_pb2.ExecutionResponse]:
    return [item async for item in servicer.SubmitJob(request, _as_context(context))]


def test_submit_job_registers_the_workload_id_before_its_first_await() -> None:
    """4b.1 / O1, re-verified at the servicer level, not just the registry
    level: immediately after starting the `SubmitJob` async generator (one
    `asend`/`__anext__` primes it up to its first `await`), the
    `WorkloadId` is already registered — observable via a `Pulse` call
    that finds it, issued before the generator is driven any further."""

    async def scenario() -> None:
        provider = StubProvider(capability_descriptor=_descriptor(), report=_report())
        servicer = _servicer([provider])
        request = _well_formed_execution_context_message()

        generator = servicer.SubmitJob(request, _as_context(_FakeContext()))
        # Prime the generator up to (and including) its first `await`,
        # without letting the drain loop's `await channel.queue.get()`
        # complete — proves registration happened synchronously, before
        # that first await, not merely "eventually".
        first_step = asyncio.ensure_future(generator.__anext__())
        await asyncio.sleep(0)

        pulse = await servicer.Pulse(
            worker_pb2.PulseRequest(workload_id=identity_pb2.WorkloadId(value=_ULID_A)),
            _as_context(_FakeContext()),
        )
        assert pulse.healthy is True

        # Drain the rest so the generator (and its driving task) finish
        # cleanly.
        remaining = [await first_step]
        async for item in generator:
            remaining.append(item)
        assert remaining[-1].HasField("report")

    asyncio.run(scenario())


def test_conversion_error_aborts_invalid_argument_before_the_stream_starts() -> None:
    """4b.2: a `ConversionError` during `SubmitJob` conversion aborts
    `INVALID_ARGUMENT` before any response is yielded."""

    async def scenario() -> None:
        servicer = _servicer([StubProvider(capability_descriptor=_descriptor())])
        malformed_request = worker_pb2.ExecutionContext()  # workload_id unset
        fake = _FakeContext()

        with pytest.raises(grpc.aio.AbortError):
            await _drain(servicer, malformed_request, fake)

        assert fake.aborted is not None
        code, _ = fake.aborted
        assert code is grpc.StatusCode.INVALID_ARGUMENT

    asyncio.run(scenario())


def test_successful_execution_yields_events_then_exactly_one_terminal_report_last() -> None:
    """4b.3 / 4b.4: the response stream carries every emitted event, then
    exactly one terminal report, always last."""

    async def scenario() -> None:
        async def on_execute(context: ExecutionContext) -> ExecutionReport:
            await context.channel.emit(Progress(fraction_complete=0.5, message="halfway"))
            return _report()

        provider = StubProvider(capability_descriptor=_descriptor(), on_execute=on_execute)
        servicer = _servicer([provider])
        request = _well_formed_execution_context_message()

        responses = await _drain(servicer, request, _FakeContext())

        # Progress, then EndOfStream (both wrapped as `event`), then the
        # terminal report last — `WorkerRuntime.execute()` always emits
        # `EndOfStream` immediately before returning its `Report`.
        assert [r.WhichOneof("payload") for r in responses] == ["event", "event", "report"]
        assert responses[0].event.HasField("progress")
        assert responses[1].event.HasField("end_of_stream")
        assert responses[-1].report.final_phase == worker_pb2.EXECUTION_PHASE_COMPLETED
        assert sum(1 for r in responses if r.HasField("report")) == 1

    asyncio.run(scenario())


def test_cancelled_execution_still_ends_with_the_terminal_report_last() -> None:
    """4b.5: a cancelled execution's response stream still ends with
    exactly one terminal report, last."""

    async def scenario() -> None:
        async def on_execute(context: ExecutionContext) -> ExecutionReport:
            await context.cancellation.wait()
            return _report(phase=ExecutionPhase.CANCELLED)

        provider = StubProvider(capability_descriptor=_descriptor(), on_execute=on_execute)
        servicer = _servicer([provider])
        request = _well_formed_execution_context_message()
        fake = _FakeContext()

        generator = servicer.SubmitJob(request, _as_context(fake))
        # Schedule (don't directly await) the first step: the provider
        # emits nothing before observing cancellation, so directly
        # awaiting `__anext__()` here would deadlock on an empty queue.
        # `asyncio.sleep(0)` yields control just long enough for the
        # generator to register the workload and start waiting on the
        # queue, without waiting for an item to arrive on it.
        first_step = asyncio.ensure_future(generator.__anext__())
        await asyncio.sleep(0)

        await servicer.Cancel(
            worker_pb2.CancelRequest(workload_id=identity_pb2.WorkloadId(value=_ULID_A)),
            _as_context(fake),
        )

        responses = [await first_step]
        async for item in generator:
            responses.append(item)

        assert responses[-1].HasField("report")
        assert responses[-1].report.final_phase == worker_pb2.EXECUTION_PHASE_CANCELLED
        assert sum(1 for r in responses if r.HasField("report")) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("phase", "failure"),
    [
        (ExecutionPhase.COMPLETED, None),
        (ExecutionPhase.FAILED, "boom"),
        (ExecutionPhase.CANCELLED, None),
    ],
)
def test_deregisters_the_workload_id_in_every_outcome(
    phase: ExecutionPhase, failure: str | None
) -> None:
    """4b.6: the `finally` block deregisters the `WorkloadId` on success,
    failure, and cancellation alike (O2) — a subsequent `Pulse` for it is
    rejected as unknown in every case."""

    async def scenario() -> None:
        async def on_execute(context: ExecutionContext) -> ExecutionReport:
            return ExecutionReport(
                phase=phase,
                duration=timedelta(),
                resource_usage={},
                metrics={},
                trace_id="trace",
                failure=failure,
            )

        provider = StubProvider(capability_descriptor=_descriptor(), on_execute=on_execute)
        servicer = _servicer([provider])
        request = _well_formed_execution_context_message()

        async for _item in servicer.SubmitJob(request, _as_context(_FakeContext())):
            pass

        fake = _FakeContext()
        with pytest.raises(grpc.aio.AbortError):
            await servicer.Pulse(
                worker_pb2.PulseRequest(workload_id=identity_pb2.WorkloadId(value=_ULID_A)),
                _as_context(fake),
            )
        assert fake.aborted is not None
        assert fake.aborted[0] is grpc.StatusCode.NOT_FOUND

    asyncio.run(scenario())


def test_cancel_of_a_known_workload_returns_cancel_ack_and_signals_the_token() -> None:
    """4b.7: `Cancel` for a known `WorkloadId` returns `CancelAck` and
    signals its cancellation token."""

    async def scenario() -> None:
        cancelled = asyncio.Event()

        async def on_execute(context: ExecutionContext) -> ExecutionReport:
            await context.cancellation.wait()
            cancelled.set()
            return _report(phase=ExecutionPhase.CANCELLED)

        provider = StubProvider(capability_descriptor=_descriptor(), on_execute=on_execute)
        servicer = _servicer([provider])
        request = _well_formed_execution_context_message()
        fake = _FakeContext()

        generator = servicer.SubmitJob(request, _as_context(fake))
        first_step = asyncio.ensure_future(generator.__anext__())
        await asyncio.sleep(0)  # registers the workload without waiting on an empty queue

        ack = await servicer.Cancel(
            worker_pb2.CancelRequest(workload_id=identity_pb2.WorkloadId(value=_ULID_A)),
            _as_context(fake),
        )
        assert isinstance(ack, worker_pb2.CancelAck)

        await first_step
        async for _item in generator:
            pass
        assert cancelled.is_set()

    asyncio.run(scenario())


def test_cancel_of_an_unknown_workload_id_is_rejected_not_found() -> None:
    """4b.7: `Cancel` for an unregistered `WorkloadId` raises a classified
    error mapped to `NOT_FOUND`, never a `CancelAck` (O3)."""

    async def scenario() -> None:
        servicer = _servicer([StubProvider(capability_descriptor=_descriptor())])
        fake = _FakeContext()

        with pytest.raises(grpc.aio.AbortError):
            await servicer.Cancel(
                worker_pb2.CancelRequest(workload_id=identity_pb2.WorkloadId(value=_ULID_A)),
                _as_context(fake),
            )
        assert fake.aborted is not None
        assert fake.aborted[0] is grpc.StatusCode.NOT_FOUND

    asyncio.run(scenario())


def test_pulse_of_a_known_workload_reports_its_phase_and_health() -> None:
    """4b.8: `Pulse` for a known `WorkloadId` reports its transport-
    observable phase and health."""

    async def scenario() -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        async def on_execute(context: ExecutionContext) -> ExecutionReport:
            started.set()
            await release.wait()
            return _report()

        provider = StubProvider(capability_descriptor=_descriptor(), on_execute=on_execute)
        servicer = _servicer([provider])
        request = _well_formed_execution_context_message()
        fake = _FakeContext()

        generator = servicer.SubmitJob(request, _as_context(fake))
        first_step = asyncio.ensure_future(generator.__anext__())
        await started.wait()

        pulse = await servicer.Pulse(
            worker_pb2.PulseRequest(workload_id=identity_pb2.WorkloadId(value=_ULID_A)),
            _as_context(fake),
        )
        assert pulse.phase == worker_pb2.EXECUTION_PHASE_RUNNING
        assert pulse.healthy is True

        release.set()
        responses = [await first_step]
        async for item in generator:
            responses.append(item)
        assert responses[-1].HasField("report")

    asyncio.run(scenario())


def test_pulse_of_an_unknown_workload_id_is_rejected_not_found() -> None:
    """4b.8: `Pulse` for an unregistered `WorkloadId` raises a classified
    error mapped to `NOT_FOUND`, never an `ExecutionPulse` (O3)."""

    async def scenario() -> None:
        servicer = _servicer([StubProvider(capability_descriptor=_descriptor())])
        fake = _FakeContext()

        with pytest.raises(grpc.aio.AbortError):
            await servicer.Pulse(
                worker_pb2.PulseRequest(workload_id=identity_pb2.WorkloadId(value=_ULID_A)),
                _as_context(fake),
            )
        assert fake.aborted is not None
        assert fake.aborted[0] is grpc.StatusCode.NOT_FOUND

    asyncio.run(scenario())


def test_duplicate_submit_job_is_rejected_without_disturbing_the_original() -> None:
    """4b.9 / O4: a second `SubmitJob` for an already in-flight
    `WorkloadId` is rejected `ALREADY_EXISTS`, without starting a second
    execution, and the original proceeds unaffected."""

    async def scenario() -> None:
        execution_count = 0

        async def on_execute(context: ExecutionContext) -> ExecutionReport:
            nonlocal execution_count
            execution_count += 1
            await context.cancellation.wait()
            return _report(phase=ExecutionPhase.CANCELLED)

        provider = StubProvider(capability_descriptor=_descriptor(), on_execute=on_execute)
        servicer = _servicer([provider])
        request = _well_formed_execution_context_message()
        original_fake = _FakeContext()

        original_generator = servicer.SubmitJob(request, _as_context(original_fake))
        first_step = asyncio.ensure_future(original_generator.__anext__())
        await asyncio.sleep(0)  # registers the original without waiting on an empty queue

        duplicate_fake = _FakeContext()
        with pytest.raises(grpc.aio.AbortError):
            await _drain(servicer, request, duplicate_fake)
        assert duplicate_fake.aborted is not None
        assert duplicate_fake.aborted[0] is grpc.StatusCode.ALREADY_EXISTS

        await servicer.Cancel(
            worker_pb2.CancelRequest(workload_id=identity_pb2.WorkloadId(value=_ULID_A)),
            _as_context(original_fake),
        )
        responses = [await first_step]
        async for item in original_generator:
            responses.append(item)
        assert responses[-1].HasField("report")
        assert responses[-1].report.final_phase == worker_pb2.EXECUTION_PHASE_CANCELLED
        # Only the original execution ever ran its body — the duplicate's
        # task was cancelled before it was ever scheduled to run (O4).
        assert execution_count == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("error_type", "expected_status"),
    [
        ("conversion", grpc.StatusCode.INVALID_ARGUMENT),
        ("unknown_workload", grpc.StatusCode.NOT_FOUND),
        ("duplicate_workload", grpc.StatusCode.ALREADY_EXISTS),
    ],
)
def test_status_mapping_is_total_and_fixed_never_unknown(
    error_type: str, expected_status: grpc.StatusCode
) -> None:
    """4b.10: the D17 status-mapping helper is total (every classified
    error family member maps to something) and fixed (each error type
    always maps to the same status) — never `UNKNOWN`."""
    from tibios_ray.transport.errors import (
        ConversionError,
        CorrelationError,
        DuplicateWorkloadError,
        MissingFieldError,
        UnknownWorkloadError,
    )
    from tibios_ray.transport.servicer import _status_code_for

    error: ConversionError | CorrelationError
    if error_type == "conversion":
        error = MissingFieldError("workload_id")
    elif error_type == "unknown_workload":
        error = UnknownWorkloadError("w-1")
    else:
        error = DuplicateWorkloadError("w-1")

    assert error.error_class is ErrorClass.PERMANENT
    status = _status_code_for(error)
    assert status is expected_status
    assert status is not grpc.StatusCode.UNKNOWN
