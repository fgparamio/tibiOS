"""`ExecutionContext` test factory (`tibios_ray.execution.context`).

`ExecutionContext` is already a concrete, frozen dataclass — not a
`typing.Protocol` — so "fake" here means removing the boilerplate every
Phase 1-5 test module repeated to build one (`AllocationContract` fields, a
channel, a cancellation token), not substituting a different shape.
`FakeExecutionContext(...)` returns a genuine `ExecutionContext`, defaulting
`channel`/`cancellation` to this package's own `InMemoryExecutionChannel`/
`ManualCancellation` fakes.
"""

from collections.abc import Mapping
from datetime import timedelta

from tibios_ray.execution.channel import CancellationToken, ExecutionChannel
from tibios_ray.execution.context import (
    AllocationContract,
    ExecutionContext,
    ObservabilityContext,
    ResolvedModelRef,
    SecurityContext,
)
from tibios_ray.execution.ids import AllocationId, WorkloadId
from tibios_ray.testing.cancellation import ManualCancellation
from tibios_ray.testing.channel import InMemoryExecutionChannel


def _default_allocation_contract() -> AllocationContract:
    # D9 Consequences — the change's only non-mechanical revert, already
    # anticipated: the six-field contract shrinks to the one field the
    # producer (runtime-allocation) actually owns.
    return AllocationContract(max_execution_duration=timedelta(minutes=5))


def _default_security_context() -> SecurityContext:
    return SecurityContext(tenant_id="test-tenant", principal_id="test-principal", grant_scope=())


def _default_observability_context() -> ObservabilityContext:
    return ObservabilityContext(trace_id="test-trace", span_id="test-span")


class FakeExecutionContext:
    """Factory that builds an `ExecutionContext` with test-friendly defaults.

    Not an `ExecutionContext` subclass — `__new__` returns a genuine
    `ExecutionContext` instance so callers keep the exact static type
    production code expects (`CapabilityProvider.execute(context:
    ExecutionContext)`), while call sites still read like constructing a
    fake: `FakeExecutionContext(capability="embedding.generate")`.
    """

    def __new__(
        cls,
        *,
        workload_id: WorkloadId | None = None,
        allocation_id: AllocationId | None = None,
        capability: str = "chat.generate",
        allocation_contract: AllocationContract | None = None,
        dependencies: tuple[ResolvedModelRef, ...] | None = None,
        security_context: SecurityContext | None = None,
        observability_context: ObservabilityContext | None = None,
        execution_parameters: Mapping[str, str] | None = None,
        channel: ExecutionChannel | None = None,
        cancellation: CancellationToken | None = None,
    ) -> ExecutionContext:
        return ExecutionContext(
            workload_id=workload_id or WorkloadId("test-workload"),
            allocation_id=allocation_id or AllocationId("test-allocation"),
            capability=capability,
            allocation_contract=allocation_contract or _default_allocation_contract(),
            dependencies=dependencies if dependencies is not None else (),
            security_context=security_context or _default_security_context(),
            observability_context=observability_context or _default_observability_context(),
            execution_parameters=(
                execution_parameters if execution_parameters is not None else {}
            ),
            channel=channel if channel is not None else InMemoryExecutionChannel(),
            cancellation=cancellation if cancellation is not None else ManualCancellation(),
        )
