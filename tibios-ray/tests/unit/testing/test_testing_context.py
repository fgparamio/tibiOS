"""Tests for `tibios_ray.testing.context` — `FakeExecutionContext`, a
factory that builds a genuine `ExecutionContext` with test-friendly
defaults, consolidating the `_execution_context()`-style helpers duplicated
across Phase 1-5's test modules (Phase 6, `testing/`).
"""

from tibios_ray.execution.context import AllocationContract, ExecutionContext, ResolvedModelRef
from tibios_ray.execution.ids import ContentHash, ObjectId, ObjectVersion
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
    assert context.dependencies == {}


def test_defaults_channel_and_cancellation_to_shared_fakes() -> None:
    context = FakeExecutionContext()
    assert isinstance(context.channel, InMemoryExecutionChannel)
    assert isinstance(context.cancellation, ManualCancellation)
    assert context.cancellation.is_cancelled is False


def test_defaults_a_sensible_allocation_contract() -> None:
    context = FakeExecutionContext()
    assert isinstance(context.allocation_contract, AllocationContract)
    assert context.allocation_contract.exclusive is True


def test_overrides_are_honored() -> None:
    ref = ResolvedModelRef(
        object_id=ObjectId("01J0000000000000000000000"),
        version=ObjectVersion(1),
        content_hash=ContentHash("sha256:abc"),
    )
    channel = InMemoryExecutionChannel()
    cancellation = ManualCancellation()
    cancellation.cancel()

    context = FakeExecutionContext(
        capability="embedding.generate",
        dependencies={"model": ref},
        channel=channel,
        cancellation=cancellation,
    )

    assert context.capability == "embedding.generate"
    assert context.dependencies == {"model": ref}
    assert context.channel is channel
    assert context.cancellation is cancellation
    assert context.cancellation.is_cancelled is True
