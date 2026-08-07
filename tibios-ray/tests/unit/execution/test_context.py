"""Tests for `tibios_ray.execution.context` — `ExecutionContext`,
`AllocationContract`, and `ResolvedModelRef`.

`ResolvedModelRef` is the proof-carrying centerpiece of Phase 1: it must
be structurally incapable of being built from an arbitrary string (e.g.
a model-family name like `"deepseek"`) — only from already-typed
`ObjectId`/`ObjectVersion`/`ContentHash` values, the shape the Runtime
hands a Capability Provider via `ExecutionContext.dependencies`
(`18-worker-model.md`: "Dependency References already resolved").
"""

import asyncio
import dataclasses
from datetime import timedelta

import pytest

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import CapabilityDescriptor, CapabilityFlags, ModelFamily
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.execution.channel import CancellationToken, ExecutionChannel
from tibios_ray.execution.context import (
    AllocationContract,
    ExecutionContext,
    ObservabilityContext,
    ResolvedModelRef,
    SecurityContext,
)
from tibios_ray.execution.ids import AllocationId, ContentHash, ObjectId, ObjectVersion, WorkloadId
from tibios_ray.execution.report import ExecutionPhase, ExecutionReport
from tibios_ray.runtime.registry import CapabilityRegistry
from tibios_ray.runtime.worker_runtime import WorkerRuntime
from tibios_ray.testing import (
    FakeExecutionContext,
    InMemoryExecutionChannel,
    ManualCancellation,
    StubProvider,
)


def _resolved_model_ref() -> ResolvedModelRef:
    return ResolvedModelRef(
        object_id=ObjectId("01J0000000000000000000000"),
        version=ObjectVersion(18),
        content_hash=ContentHash("sha256:af2398..."),
    )


def _allocation_contract() -> AllocationContract:
    return AllocationContract(max_execution_duration=timedelta(minutes=30))


def _descriptor(capability: str) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        capability=CapabilityName(capability),
        families=frozenset({ModelFamily("deepseek")}),
        backends=frozenset({BackendId("llama_cpp")}),
        flags=CapabilityFlags(streaming=True),
    )


def _success_report() -> ExecutionReport:
    return ExecutionReport(
        phase=ExecutionPhase.COMPLETED,
        duration=timedelta(seconds=1),
        resource_usage={},
        metrics={},
        trace_id="trace-fixed",
    )


def _success_provider(capability: str = "chat.generate") -> StubProvider:
    return StubProvider(capability_descriptor=_descriptor(capability), report=_success_report())


def _default_security_context() -> SecurityContext:
    return SecurityContext(tenant_id="tenant", principal_id="principal", grant_scope=())


def _default_observability_context() -> ObservabilityContext:
    return ObservabilityContext(trace_id="trace", span_id="span")


def _context(
    *,
    capability: str = "chat.generate",
    workload_id: WorkloadId | None = None,
    allocation_id: AllocationId | None = None,
    security_context: SecurityContext | None = None,
    observability_context: ObservabilityContext | None = None,
    execution_parameters: dict[str, str] | None = None,
    dependencies: tuple[ResolvedModelRef, ...] = (),
    channel: InMemoryExecutionChannel | None = None,
) -> ExecutionContext:
    return ExecutionContext(
        workload_id=workload_id or WorkloadId("01J0000000000000000000010"),
        allocation_id=allocation_id or AllocationId("01J0000000000000000000011"),
        capability=capability,
        allocation_contract=_allocation_contract(),
        dependencies=dependencies,
        security_context=security_context or _default_security_context(),
        observability_context=observability_context or _default_observability_context(),
        execution_parameters=execution_parameters if execution_parameters is not None else {},
        channel=channel if channel is not None else InMemoryExecutionChannel(),
        cancellation=ManualCancellation(),
    )


class TestSecurityContextDispatchIndependence:
    def test_dispatch_outcome_is_independent_of_security_context_content(self) -> None:
        registry = CapabilityRegistry([_success_provider()])
        runtime = WorkerRuntime(registry)

        first = _context(
            security_context=SecurityContext(
                tenant_id="tenant-a", principal_id="principal-a", grant_scope=("read",)
            )
        )
        second = _context(
            security_context=SecurityContext(tenant_id="", principal_id="", grant_scope=())
        )

        first_report = asyncio.run(runtime.execute(first))
        second_report = asyncio.run(runtime.execute(second))

        assert first_report.phase == second_report.phase == ExecutionPhase.COMPLETED
        assert first_report.trace_id == second_report.trace_id


class TestObservabilityContextPassThrough:
    def test_observability_values_pass_through_without_altering_execution(self) -> None:
        registry = CapabilityRegistry([_success_provider()])
        runtime = WorkerRuntime(registry)

        first = _context(
            observability_context=ObservabilityContext(trace_id="trace-1", span_id="span-1")
        )
        second = _context(
            observability_context=ObservabilityContext(trace_id="trace-2", span_id="span-2")
        )

        first_report = asyncio.run(runtime.execute(first))
        second_report = asyncio.run(runtime.execute(second))

        assert first_report.phase == second_report.phase == ExecutionPhase.COMPLETED
        assert first.observability_context.trace_id == "trace-1"
        assert second.observability_context.trace_id == "trace-2"


class TestExecutionParametersDispatchIndependence:
    def test_dispatch_target_is_unaffected_by_execution_parameters_content(self) -> None:
        registry = CapabilityRegistry([_success_provider()])
        runtime = WorkerRuntime(registry)

        first = _context(execution_parameters={})
        second = _context(execution_parameters={"temperature": "0.7", "top_p": "0.9"})

        first_report = asyncio.run(runtime.execute(first))
        second_report = asyncio.run(runtime.execute(second))

        assert first_report.phase == second_report.phase == ExecutionPhase.COMPLETED
        assert first_report.trace_id == second_report.trace_id
        assert first.execution_parameters == {}
        assert second.execution_parameters == {"temperature": "0.7", "top_p": "0.9"}


class TestDependenciesIsOrderedAndUnkeyed:
    def test_accepts_a_tuple_and_preserves_construction_order(self) -> None:
        # D10: dependencies is ordered, unkeyed — the wire is `repeated
        # ResolvedModelRef` with no key, and fabricating one is exactly
        # what worker-wire-conversion's reject-don't-guess rule forbids.
        first_ref = ResolvedModelRef(
            object_id=ObjectId("01J0000000000000000000000"),
            version=ObjectVersion(1),
            content_hash=ContentHash("sha256:first"),
        )
        second_ref = ResolvedModelRef(
            object_id=ObjectId("01J0000000000000000000001"),
            version=ObjectVersion(1),
            content_hash=ContentHash("sha256:second"),
        )

        ctx = _context(dependencies=(first_ref, second_ref))

        assert ctx.dependencies == (first_ref, second_ref)
        assert ctx.dependencies[0] is first_ref
        assert ctx.dependencies[1] is second_ref


class TestExecutionContextTenFields:
    def test_constructs_with_all_ten_keyword_only_fields(self) -> None:
        # D8: ExecutionContext grows to ten fields, no envelope. kw_only
        # is already set, so widening the constructor breaks no
        # positional call site.
        ctx = ExecutionContext(
            workload_id=WorkloadId("01J0000000000000000000010"),
            allocation_id=AllocationId("01J0000000000000000000011"),
            capability="chat.generate",
            allocation_contract=_allocation_contract(),
            dependencies=(),
            security_context=_default_security_context(),
            observability_context=_default_observability_context(),
            execution_parameters={},
            channel=InMemoryExecutionChannel(),
            cancellation=ManualCancellation(),
        )

        assert ctx.workload_id == WorkloadId("01J0000000000000000000010")
        assert ctx.allocation_id == AllocationId("01J0000000000000000000011")


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
        assert contract.max_execution_duration == timedelta(minutes=30)

    def test_is_frozen(self) -> None:
        contract = _allocation_contract()
        with pytest.raises(dataclasses.FrozenInstanceError):
            contract.max_execution_duration = timedelta(minutes=1)  # type: ignore[misc]

    def test_carries_exactly_max_execution_duration(self) -> None:
        # D9: AllocationContract narrows to exactly one field — the producer
        # (runtime-allocation) owns the contract; tibios-ray never redefines
        # its shape (`execution-identity` — "AllocationContract has no
        # fields beyond max_execution_duration").
        field_names = {f.name for f in dataclasses.fields(AllocationContract)}
        assert field_names == {"max_execution_duration"}

    def test_rejects_the_five_removed_fields_as_unexpected_keyword_arguments(self) -> None:
        removed = {
            "exclusive": True,
            "renewable_lease": False,
            "preemptible": False,
            "migration_allowed": False,
            "checkpoint_required": False,
        }
        for field_name, value in removed.items():
            with pytest.raises(TypeError):
                AllocationContract(
                    max_execution_duration=timedelta(minutes=5),
                    **{field_name: value},
                )


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
