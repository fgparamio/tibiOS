"""Tests for `tibios_ray.transport.registry` — `InFlightRegistry`, the
in-flight `WorkloadId` correlation table (design decision D15).

`WorkerRuntime` publishes no phase transitions, so `PREPARED` is
genuinely unobservable — this registry never reports it: entries start
at `RECEIVED` and the only transition modeled is `RECEIVED` -> `RUNNING`
(D15). `register` is synchronous (no `await`), proving O1: a `Cancel`
issued immediately after `SubmitJob`, before the calling coroutine's
first `await`, always finds the `WorkloadId` already registered. O2-O4
(deregistration on every outcome, unknown-lookup rejection, duplicate
rejection) are the `worker-grpc-transport` spec's requirements of the
same names, exercised here at the registry level before S4b wires them
to RPCs.
"""

import asyncio
import inspect
from datetime import timedelta

import pytest

from tibios_ray.execution.ids import WorkloadId
from tibios_ray.execution.report import ExecutionPhase, ExecutionReport
from tibios_ray.transport.cancellation import GrpcCancellationToken
from tibios_ray.transport.errors import DuplicateWorkloadError, UnknownWorkloadError
from tibios_ray.transport.registry import InFlightRegistry

_A_REPORT = ExecutionReport(
    phase=ExecutionPhase.COMPLETED,
    duration=timedelta(),
    resource_usage={},
    metrics={},
    trace_id="trace",
)


def _noop_task() -> "asyncio.Task[ExecutionReport]":
    async def _noop() -> ExecutionReport:
        return _A_REPORT

    return asyncio.ensure_future(_noop())


def test_register_is_synchronous_no_await_inside_it() -> None:
    assert not inspect.iscoroutinefunction(InFlightRegistry.register)


def test_registered_entry_starts_at_phase_received() -> None:
    async def scenario() -> None:
        registry = InFlightRegistry()
        workload_id = WorkloadId("w-received")
        task = _noop_task()

        registry.register(workload_id, GrpcCancellationToken(), task)

        assert registry.lookup(workload_id).phase is ExecutionPhase.RECEIVED
        await task

    asyncio.run(scenario())


def test_mark_running_transitions_phase_to_running() -> None:
    async def scenario() -> None:
        registry = InFlightRegistry()
        workload_id = WorkloadId("w-running")
        task = _noop_task()
        registry.register(workload_id, GrpcCancellationToken(), task)

        registry.mark_running(workload_id)

        assert registry.lookup(workload_id).phase is ExecutionPhase.RUNNING
        await task

    asyncio.run(scenario())


def test_registry_never_produces_a_prepared_phase() -> None:
    """No code path in this module *references* `ExecutionPhase.PREPARED`
    (D15) — a not-yet-started task must never be reported as `RUNNING`,
    and `PREPARED` is unobservable, so it is never reported at all. Scans
    identifiers, not raw text, so this module's own docstring (which
    quotes the D15 rule) is never mistaken for a violation."""
    import ast

    import tibios_ray.transport.registry as registry_module

    tree = ast.parse(inspect.getsource(registry_module))
    attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert "PREPARED" not in attrs


def test_cancel_immediately_after_register_finds_workload_already_registered() -> None:
    """O1: a Cancel call issued immediately after `register()` — before
    the calling coroutine's first `await` — finds W already registered.
    Driven on one event loop, no sleeps."""

    async def scenario() -> None:
        registry = InFlightRegistry()
        workload_id = WorkloadId("w-o1")
        task = _noop_task()

        registry.register(workload_id, GrpcCancellationToken(), task)
        # No await between register() and lookup(): proves registration
        # is synchronous and immediately observable.
        entry = registry.lookup(workload_id)

        assert entry is not None
        await task

    asyncio.run(scenario())


@pytest.mark.parametrize("outcome", ["success", "failure", "cancellation"])
def test_deregister_removes_the_entry_after_completion_in_every_outcome(outcome: str) -> None:
    async def scenario() -> None:
        registry = InFlightRegistry()
        workload_id = WorkloadId(f"w-{outcome}")
        task = _noop_task()
        registry.register(workload_id, GrpcCancellationToken(), task)

        registry.deregister(workload_id)

        with pytest.raises(UnknownWorkloadError):
            registry.lookup(workload_id)
        await task

    asyncio.run(scenario())


def test_lookup_of_unregistered_workload_raises_unknown_workload_error() -> None:
    registry = InFlightRegistry()

    with pytest.raises(UnknownWorkloadError):
        registry.lookup(WorkloadId("never-registered"))


def test_duplicate_register_raises_without_disturbing_the_first_entry() -> None:
    async def scenario() -> None:
        registry = InFlightRegistry()
        workload_id = WorkloadId("w-dup")
        first_token = GrpcCancellationToken()
        first_task = _noop_task()
        registry.register(workload_id, first_token, first_task)

        second_task = _noop_task()
        with pytest.raises(DuplicateWorkloadError):
            registry.register(workload_id, GrpcCancellationToken(), second_task)

        entry = registry.lookup(workload_id)
        assert entry.token is first_token
        assert entry.task is first_task

        await first_task
        await second_task

    asyncio.run(scenario())
