"""Tests for `tibios_ray.runtime.worker_runtime` — `WorkerRuntime`
(`worker-runtime` spec: "Worker Runtime Owns the Execution Lifecycle",
"Dispatch Only via Capability Registry"; `design.md` design decision D5:
cooperative cancellation, never raw `asyncio.CancelledError`).

`WorkerRuntime` is the one sanctioned "Worker"-named identifier in this
codebase (`worker-runtime` spec: "'Worker' Naming Is Reserved to the
Contract Entity") — it directly drives the Worker Contract lifecycle.
"""

import asyncio
from datetime import timedelta

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import CapabilityDescriptor, CapabilityFlags, ModelFamily
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.execution.context import ExecutionContext
from tibios_ray.execution.events import EndOfStream, OutputChunk, Progress, Warning
from tibios_ray.execution.report import ExecutionPhase, ExecutionReport
from tibios_ray.runtime.registry import CapabilityRegistry
from tibios_ray.runtime.worker_runtime import WorkerRuntime
from tibios_ray.testing import (
    FakeExecutionContext,
    InMemoryExecutionChannel,
    ManualCancellation,
    StubProvider,
)


def _cancellation(*, cancelled: bool) -> ManualCancellation:
    """A `ManualCancellation` fixed at a given state — cooperative
    cancellation is proven here by a Provider observing an
    already-cancelled token, not by racing real `asyncio` tasks."""
    token = ManualCancellation()
    if cancelled:
        token.cancel()
    return token


def _descriptor(capability: str) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        capability=CapabilityName(capability),
        families=frozenset({ModelFamily("deepseek")}),
        backends=frozenset({BackendId("llama_cpp")}),
        flags=CapabilityFlags(streaming=True),
    )


async def _success_execute(context: ExecutionContext) -> ExecutionReport:
    """Emits application output then completes normally."""
    await context.channel.emit(OutputChunk(data=b"hello", sequence=0))
    await context.channel.emit(Progress(fraction_complete=1.0))
    return ExecutionReport(
        phase=ExecutionPhase.COMPLETED,
        duration=timedelta(seconds=1),
        resource_usage={},
        metrics={},
        trace_id="trace-success",
    )


def _success_provider(capability: str = "chat.generate") -> StubProvider:
    return StubProvider(capability_descriptor=_descriptor(capability), on_execute=_success_execute)


async def _cancelling_execute(context: ExecutionContext) -> ExecutionReport:
    """Observes `context.cancellation.is_cancelled`, performs acknowledge ->
    cleanup, then returns a Failed report — cooperative cancellation per
    design decision D5, entirely inside the Capability Provider."""
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


def _cancelling_provider(capability: str = "chat.generate") -> StubProvider:
    return StubProvider(
        capability_descriptor=_descriptor(capability), on_execute=_cancelling_execute
    )


async def _raising_execute(context: ExecutionContext) -> ExecutionReport:
    """A misbehaving Capability Provider that raises instead of returning a
    Report — `WorkerRuntime` must still never let this escape."""
    raise RuntimeError("boom")


def _raising_provider(capability: str = "boom.explode") -> StubProvider:
    return StubProvider(capability_descriptor=_descriptor(capability), on_execute=_raising_execute)


def test_execute_success_lifecycle_dispatches_emits_events_and_report() -> None:
    channel = InMemoryExecutionChannel()
    registry = CapabilityRegistry([_success_provider()])
    runtime = WorkerRuntime(registry)
    context = FakeExecutionContext(capability="chat.generate", channel=channel)

    report = asyncio.run(runtime.execute(context))

    assert report.phase == ExecutionPhase.COMPLETED
    assert report.trace_id == "trace-success"
    assert channel.emitted == [
        OutputChunk(data=b"hello", sequence=0),
        Progress(fraction_complete=1.0),
        EndOfStream(reason=None),
    ]


def test_execute_unknown_capability_returns_failed_report_without_raising() -> None:
    channel = InMemoryExecutionChannel()
    registry = CapabilityRegistry([_success_provider()])
    runtime = WorkerRuntime(registry)
    context = FakeExecutionContext(capability="vision.understand", channel=channel)

    report = asyncio.run(runtime.execute(context))

    assert report.phase == ExecutionPhase.FAILED
    assert report.failure is not None
    assert "vision.understand" in report.failure
    assert channel.emitted == [EndOfStream(reason=report.failure)]


def test_execute_malformed_capability_string_returns_failed_report_without_raising() -> None:
    channel = InMemoryExecutionChannel()
    registry = CapabilityRegistry([_success_provider()])
    runtime = WorkerRuntime(registry)
    context = FakeExecutionContext(capability="NOT-A-VALID-CAPABILITY!!", channel=channel)

    report = asyncio.run(runtime.execute(context))

    assert report.phase == ExecutionPhase.FAILED
    assert report.failure is not None
    assert channel.emitted == [EndOfStream(reason=report.failure)]


def test_execute_cancellation_acknowledges_cleans_up_and_emits_final_events() -> None:
    channel = InMemoryExecutionChannel()
    registry = CapabilityRegistry([_cancelling_provider()])
    runtime = WorkerRuntime(registry)
    context = FakeExecutionContext(
        capability="chat.generate",
        channel=channel,
        cancellation=_cancellation(cancelled=True),
    )

    report = asyncio.run(runtime.execute(context))

    assert report.phase == ExecutionPhase.FAILED
    assert report.failure == "cancelled"
    assert channel.emitted == [
        Warning(message="cancellation acknowledged", code="cancelled"),
        Progress(fraction_complete=0.5, message="cleaning up"),
        EndOfStream(reason="cancelled"),
    ]


def test_execute_never_lets_a_provider_exception_escape() -> None:
    channel = InMemoryExecutionChannel()
    registry = CapabilityRegistry([_raising_provider()])
    runtime = WorkerRuntime(registry)
    context = FakeExecutionContext(capability="boom.explode", channel=channel)

    report = asyncio.run(runtime.execute(context))

    assert report.phase == ExecutionPhase.FAILED
    assert report.failure is not None
    assert "boom" in report.failure
    assert channel.emitted[-1] == EndOfStream(reason=report.failure)


def test_worker_runtime_never_holds_a_direct_provider_reference() -> None:
    """Structural guard: the only constructor dependency is the
    registry — dispatch happens exclusively via `registry.resolve()`."""
    import inspect

    signature = inspect.signature(WorkerRuntime.__init__)
    parameters = [p for name, p in signature.parameters.items() if name != "self"]

    assert [p.name for p in parameters] == ["registry"]
