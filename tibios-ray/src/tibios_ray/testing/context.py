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
from tibios_ray.execution.context import AllocationContract, ExecutionContext, ResolvedModelRef
from tibios_ray.testing.cancellation import ManualCancellation
from tibios_ray.testing.channel import InMemoryExecutionChannel


def _default_allocation_contract() -> AllocationContract:
    return AllocationContract(
        exclusive=True,
        renewable_lease=False,
        preemptible=False,
        migration_allowed=False,
        checkpoint_required=False,
        max_execution_duration=timedelta(minutes=5),
    )


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
        capability: str = "chat.generate",
        allocation_contract: AllocationContract | None = None,
        dependencies: Mapping[str, ResolvedModelRef] | None = None,
        channel: ExecutionChannel | None = None,
        cancellation: CancellationToken | None = None,
    ) -> ExecutionContext:
        return ExecutionContext(
            capability=capability,
            allocation_contract=allocation_contract or _default_allocation_contract(),
            dependencies=dependencies if dependencies is not None else {},
            channel=channel if channel is not None else InMemoryExecutionChannel(),
            cancellation=cancellation if cancellation is not None else ManualCancellation(),
        )
