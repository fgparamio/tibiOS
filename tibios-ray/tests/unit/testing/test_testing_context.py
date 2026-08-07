"""Tests for `tibios_ray.testing.context` — `FakeExecutionContext`, a
factory that builds a genuine `ExecutionContext` with test-friendly
defaults, consolidating the `_execution_context()`-style helpers duplicated
across Phase 1-5's test modules (Phase 6, `testing/`).
"""

from datetime import timedelta

from tibios_ray.execution.context import (
    AllocationContract,
    ExecutionContext,
    ObservabilityContext,
    ResolvedModelRef,
    SecurityContext,
)
from tibios_ray.execution.ids import AllocationId, ContentHash, ObjectId, ObjectVersion, WorkloadId
from tibios_ray.testing.cancellation import ManualCancellation
from tibios_ray.testing.channel import InMemoryExecutionChannel
from tibios_ray.testing.context import FakeExecutionContext


def test_returns_a_genuine_execution_context() -> None:
    context = FakeExecutionContext()
    # `FakeExecutionContext` is a factory, not an `ExecutionContext` subclass
    # or substitute — production code (`CapabilityProvider.execute(context:
    # ExecutionContext)`) receives a real `ExecutionContext` instance.
    assert isinstance(context, ExecutionContext)
    assert type(context) is ExecutionContext


def test_defaults_capability_and_empty_dependencies() -> None:
    context = FakeExecutionContext()
    assert context.capability == "chat.generate"
    assert context.dependencies == ()


def test_defaults_channel_and_cancellation_to_shared_fakes() -> None:
    context = FakeExecutionContext()
    assert isinstance(context.channel, InMemoryExecutionChannel)
    assert isinstance(context.cancellation, ManualCancellation)
    assert context.cancellation.is_cancelled is False


def test_defaults_a_sensible_allocation_contract() -> None:
    context = FakeExecutionContext()
    assert isinstance(context.allocation_contract, AllocationContract)
    assert context.allocation_contract.max_execution_duration == timedelta(minutes=5)


def test_defaults_identity_security_observability_and_execution_parameters() -> None:
    context = FakeExecutionContext()
    assert isinstance(context.workload_id, WorkloadId)
    assert isinstance(context.allocation_id, AllocationId)
    assert isinstance(context.security_context, SecurityContext)
    assert isinstance(context.observability_context, ObservabilityContext)
    assert context.execution_parameters == {}


def test_overrides_are_honored() -> None:
    ref = ResolvedModelRef(
        object_id=ObjectId("01J0000000000000000000000"),
        version=ObjectVersion(1),
        content_hash=ContentHash("sha256:abc"),
    )
    channel = InMemoryExecutionChannel()
    cancellation = ManualCancellation()
    cancellation.cancel()
    workload_id = WorkloadId("01J0000000000000000000099")
    allocation_id = AllocationId("01J0000000000000000000098")
    security_context = SecurityContext(
        tenant_id="tenant-x", principal_id="principal-x", grant_scope=("read",)
    )
    observability_context = ObservabilityContext(trace_id="trace-x", span_id="span-x")

    context = FakeExecutionContext(
        workload_id=workload_id,
        allocation_id=allocation_id,
        capability="embedding.generate",
        dependencies=(ref,),
        security_context=security_context,
        observability_context=observability_context,
        execution_parameters={"temperature": "0.7"},
        channel=channel,
        cancellation=cancellation,
    )

    assert context.workload_id is workload_id
    assert context.allocation_id is allocation_id
    assert context.capability == "embedding.generate"
    assert context.dependencies == (ref,)
    assert context.security_context is security_context
    assert context.observability_context is observability_context
    assert context.execution_parameters == {"temperature": "0.7"}
    assert context.channel is channel
    assert context.cancellation is cancellation
    assert context.cancellation.is_cancelled is True
