"""Tests for `tibios_ray.execution.context` — `ExecutionContext`,
`AllocationContract`, and `ResolvedModelRef`.

`ResolvedModelRef` is the proof-carrying centerpiece of Phase 1: it must
be structurally incapable of being built from an arbitrary string (e.g.
a model-family name like `"deepseek"`) — only from already-typed
`ObjectId`/`ObjectVersion`/`ContentHash` values, the shape the Runtime
hands a Capability Provider via `ExecutionContext.dependencies`
(`18-worker-model.md`: "Dependency References already resolved").
"""

import dataclasses
from datetime import timedelta

import pytest

from tibios_ray.execution.channel import CancellationToken, ExecutionChannel
from tibios_ray.execution.context import AllocationContract, ResolvedModelRef
from tibios_ray.execution.ids import ContentHash, ObjectId, ObjectVersion
from tibios_ray.testing import FakeExecutionContext


def _resolved_model_ref() -> ResolvedModelRef:
    return ResolvedModelRef(
        object_id=ObjectId("01J0000000000000000000000"),
        version=ObjectVersion(18),
        content_hash=ContentHash("sha256:af2398..."),
    )


def _allocation_contract() -> AllocationContract:
    return AllocationContract(
        exclusive=True,
        renewable_lease=False,
        preemptible=False,
        migration_allowed=True,
        checkpoint_required=False,
        max_execution_duration=timedelta(minutes=30),
    )


class TestResolvedModelRef:
    def test_constructs_from_typed_dependency_reference_fields(self) -> None:
        ref = _resolved_model_ref()
        assert ref.object_id == ObjectId("01J0000000000000000000000")
        assert ref.version == ObjectVersion(18)
        assert ref.content_hash == ContentHash("sha256:af2398...")

    def test_is_frozen(self) -> None:
        ref = _resolved_model_ref()
        with pytest.raises(dataclasses.FrozenInstanceError):
            ref.object_id = ObjectId("other")  # type: ignore[misc]

    def test_cannot_be_constructed_from_a_single_raw_string(self) -> None:
        # A "deepseek"-style family string has no way to satisfy the three
        # required typed fields — this is the structural guarantee, not
        # merely a naming convention.
        with pytest.raises(TypeError):
            ResolvedModelRef("deepseek")  # type: ignore[call-arg]

    def test_cannot_be_constructed_with_raw_strings_in_place_of_typed_ids(self) -> None:
        # Even supplying all three positions, raw strings are rejected at
        # runtime — an ObjectId/ObjectVersion/ContentHash is required, not
        # merely "something string-shaped".
        with pytest.raises(TypeError):
            ResolvedModelRef(
                object_id="deepseek",  # type: ignore[arg-type]
                version=ObjectVersion(18),
                content_hash=ContentHash("sha256:af2398..."),
            )

    def test_only_legitimate_source_is_execution_context_dependencies(self) -> None:
        ref = _resolved_model_ref()
        ctx = FakeExecutionContext(
            capability="chat.generate",
            allocation_contract=_allocation_contract(),
            dependencies={"model": ref},
        )
        assert ctx.dependencies["model"] is ref
        assert isinstance(ctx.dependencies["model"], ResolvedModelRef)


class TestAllocationContract:
    def test_holds_its_fields(self) -> None:
        contract = _allocation_contract()
        assert contract.exclusive is True
        assert contract.max_execution_duration == timedelta(minutes=30)

    def test_is_frozen(self) -> None:
        contract = _allocation_contract()
        with pytest.raises(dataclasses.FrozenInstanceError):
            contract.exclusive = False  # type: ignore[misc]


class TestExecutionContext:
    def test_holds_capability_and_dependencies(self) -> None:
        ref = _resolved_model_ref()
        ctx = FakeExecutionContext(
            capability="chat.generate",
            allocation_contract=_allocation_contract(),
            dependencies={"model": ref},
        )
        assert ctx.capability == "chat.generate"
        assert ctx.dependencies == {"model": ref}

    def test_is_frozen(self) -> None:
        ctx = FakeExecutionContext(
            capability="chat.generate",
            allocation_contract=_allocation_contract(),
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            ctx.capability = "embed"  # type: ignore[misc]

    def test_channel_and_cancellation_satisfy_their_protocols(self) -> None:
        ctx = FakeExecutionContext(
            capability="chat.generate",
            allocation_contract=_allocation_contract(),
        )
        channel: ExecutionChannel = ctx.channel
        cancellation: CancellationToken = ctx.cancellation
        assert channel is ctx.channel
        assert cancellation.is_cancelled is False
