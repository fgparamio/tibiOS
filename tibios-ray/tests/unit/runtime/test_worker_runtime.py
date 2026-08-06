"""Tests for `tibios_ray.runtime.worker_runtime` — `WorkerRuntime`
(`worker-runtime` spec: "Worker Runtime Owns the Execution Lifecycle",
"Dispatch Only via Capability Registry"; `design.md` design decision D5:
cooperative cancellation, never raw `asyncio.CancelledError`).

`WorkerRuntime` is the one sanctioned "Worker"-named identifier in this
codebase (`worker-runtime` spec: "'Worker' Naming Is Reserved to the
Contract Entity") — it directly drives the Worker Contract lifecycle.
"""

import asyncio
from dataclasses import dataclass
from datetime import timedelta

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import CapabilityDescriptor, CapabilityFlags, ModelFamily
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.execution.context import AllocationContract, ExecutionContext
from tibios_ray.execution.events import EndOfStream, ExecutionEvent, OutputChunk, Progress, Warning
from tibios_ray.execution.report import ExecutionPhase, ExecutionReport
from tibios_ray.runtime.registry import CapabilityRegistry
from tibios_ray.runtime.worker_runtime import WorkerRuntime


class _RecordingChannel:
    """An in-memory `ExecutionChannel` fake — records every emitted event
    in order, so tests can assert on the full event sequence including
    the terminal `EndOfStream` the Worker Runtime is responsible for."""

    def __init__(self) -> None:
        self.events: list[ExecutionEvent] = []

    async def emit(self, event: ExecutionEvent) -> None:
        self.events.append(event)


@dataclass
class _StaticCancellation:
    """A `CancellationToken` fake whose `is_cancelled` never changes —
    cooperative cancellation is proven here by a Provider observing an
    already-cancelled token, not by racing real `asyncio` tasks."""

    cancelled: bool = False

    @property
    def is_cancelled(self) -> bool:
        return self.cancelled

    async def wait(self) -> None:
        return None


def _execution_context(
    *, capability: str, channel: _RecordingChannel, cancellation: _StaticCancellation | None = None
) -> ExecutionContext:
    return ExecutionContext(
        capability=capability,
        allocation_contract=AllocationContract(
            exclusive=True,
            renewable_lease=False,
            preemptible=False,
            migration_allowed=False,
            checkpoint_required=False,
            max_execution_duration=timedelta(minutes=5),
        ),
        dependencies={},
        channel=channel,
        cancellation=cancellation or _StaticCancellation(),
    )


def _descriptor(capability: str) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        capability=CapabilityName(capability),
        families=frozenset({ModelFamily("deepseek")}),
        backends=frozenset({BackendId("llama_cpp")}),
        flags=CapabilityFlags(streaming=True),
    )


@dataclass(frozen=True, slots=True)
class _SuccessProvider:
    """Emits application output then completes normally."""

    capability: str = "chat.generate"

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return _descriptor(self.capability)

    async def execute(self, context: ExecutionContext) -> ExecutionReport:
        await context.channel.emit(OutputChunk(data=b"hello", sequence=0))
        await context.channel.emit(Progress(fraction_complete=1.0))
        return ExecutionReport(
            phase=ExecutionPhase.COMPLETED,
            duration=timedelta(seconds=1),
            resource_usage={},
            metrics={},
            trace_id="trace-success",
        )


@dataclass(frozen=True, slots=True)
class _CancellingProvider:
    """Observes `context.cancellation.is_cancelled`, performs acknowledge
    -> cleanup, then returns a Failed report — cooperative cancellation
    per design decision D5, entirely inside the Capability Provider."""

    capability: str = "chat.generate"

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return _descriptor(self.capability)

    async def execute(self, context: ExecutionContext) -> ExecutionReport:
        assert context.cancellation.is_cancelled
        await context.channel.emit(Warning(message="cancellation acknowledged", code="cancelled"))
        await context.channel.emit(Progress(fraction_complete=0.5, message="cleaning up"))
        return ExecutionReport(
            phase=ExecutionPhase.FAILED,
            duration=timedelta(milliseconds=1),
            resource_usage={},
            metrics={},
            trace_id="trace-cancelled",
            failure="cancelled",
        )


@dataclass(frozen=True, slots=True)
class _RaisingProvider:
    """A misbehaving Capability Provider that raises instead of returning
    a Report — `WorkerRuntime` must still never let this escape."""

    capability: str = "boom.explode"

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return _descriptor(self.capability)

    async def execute(self, context: ExecutionContext) -> ExecutionReport:
        raise RuntimeError("boom")


def test_execute_success_lifecycle_dispatches_emits_events_and_report() -> None:
    channel = _RecordingChannel()
    registry = CapabilityRegistry([_SuccessProvider()])
    runtime = WorkerRuntime(registry)
    context = _execution_context(capability="chat.generate", channel=channel)

    report = asyncio.run(runtime.execute(context))

    assert report.phase == ExecutionPhase.COMPLETED
    assert report.trace_id == "trace-success"
    assert channel.events == [
        OutputChunk(data=b"hello", sequence=0),
        Progress(fraction_complete=1.0),
        EndOfStream(reason=None),
    ]


def test_execute_unknown_capability_returns_failed_report_without_raising() -> None:
    channel = _RecordingChannel()
    registry = CapabilityRegistry([_SuccessProvider()])
    runtime = WorkerRuntime(registry)
    context = _execution_context(capability="vision.understand", channel=channel)

    report = asyncio.run(runtime.execute(context))

    assert report.phase == ExecutionPhase.FAILED
    assert report.failure is not None
    assert "vision.understand" in report.failure
    assert channel.events == [EndOfStream(reason=report.failure)]


def test_execute_malformed_capability_string_returns_failed_report_without_raising() -> None:
    channel = _RecordingChannel()
    registry = CapabilityRegistry([_SuccessProvider()])
    runtime = WorkerRuntime(registry)
    context = _execution_context(capability="NOT-A-VALID-CAPABILITY!!", channel=channel)

    report = asyncio.run(runtime.execute(context))

    assert report.phase == ExecutionPhase.FAILED
    assert report.failure is not None
    assert channel.events == [EndOfStream(reason=report.failure)]


def test_execute_cancellation_acknowledges_cleans_up_and_emits_final_events() -> None:
    channel = _RecordingChannel()
    registry = CapabilityRegistry([_CancellingProvider()])
    runtime = WorkerRuntime(registry)
    context = _execution_context(
        capability="chat.generate",
        channel=channel,
        cancellation=_StaticCancellation(cancelled=True),
    )

    report = asyncio.run(runtime.execute(context))

    assert report.phase == ExecutionPhase.FAILED
    assert report.failure == "cancelled"
    assert channel.events == [
        Warning(message="cancellation acknowledged", code="cancelled"),
        Progress(fraction_complete=0.5, message="cleaning up"),
        EndOfStream(reason="cancelled"),
    ]


def test_execute_never_lets_a_provider_exception_escape() -> None:
    channel = _RecordingChannel()
    registry = CapabilityRegistry([_RaisingProvider()])
    runtime = WorkerRuntime(registry)
    context = _execution_context(capability="boom.explode", channel=channel)

    report = asyncio.run(runtime.execute(context))

    assert report.phase == ExecutionPhase.FAILED
    assert report.failure is not None
    assert "boom" in report.failure
    assert channel.events[-1] == EndOfStream(reason=report.failure)


def test_worker_runtime_never_holds_a_direct_provider_reference() -> None:
    """Structural guard: the only constructor dependency is the
    registry — dispatch happens exclusively via `registry.resolve()`."""
    import inspect

    signature = inspect.signature(WorkerRuntime.__init__)
    parameters = [p for name, p in signature.parameters.items() if name != "self"]

    assert [p.name for p in parameters] == ["registry"]
