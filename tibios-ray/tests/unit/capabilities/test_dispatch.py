"""Tests for `tibios_ray.capabilities.dispatch` — model-ref selection,
backend resolution, and report builders (design decisions D18/D20/D21).

No pytest-asyncio installed — `asyncio.run(...)` inside sync tests,
matching `test_provider_conformance.py`'s existing convention.
"""

import asyncio

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.dispatch import (
    cancelled_report,
    completed_report,
    resolve_backend,
    resolve_model_ref,
)
from tibios_ray.capabilities.errors import (
    MissingModelDependencyError,
    NoBackendAvailableError,
    UnresolvableBackendError,
)
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.execution.context import ResolvedModelRef
from tibios_ray.execution.events import Warning as WarningEvent
from tibios_ray.execution.ids import ContentHash, ObjectId, ObjectVersion
from tibios_ray.execution.report import ExecutionPhase
from tibios_ray.selection.policy import Quantization, ServingPlan
from tibios_ray.testing import (
    FakeExecutionContext,
    FakeModelSelectionPolicy,
    InMemoryExecutionChannel,
)

_CAPABILITY = CapabilityName("chat.generate")


def _model_ref(suffix: str = "1") -> ResolvedModelRef:
    return ResolvedModelRef(
        object_id=ObjectId(f"model-{suffix}"),
        version=ObjectVersion(1),
        content_hash=ContentHash(f"hash-{suffix}"),
    )


class TestResolveModelRef:
    def test_zero_dependencies_raises_missing_model_dependency_error(self) -> None:
        context = FakeExecutionContext(dependencies=())

        async def scenario() -> None:
            await resolve_model_ref(context, capability=_CAPABILITY)

        try:
            asyncio.run(scenario())
        except MissingModelDependencyError as error:
            assert error.capability == _CAPABILITY
        else:
            raise AssertionError("expected MissingModelDependencyError")

    def test_single_dependency_is_returned(self) -> None:
        ref = _model_ref()
        context = FakeExecutionContext(dependencies=(ref,))

        result = asyncio.run(resolve_model_ref(context, capability=_CAPABILITY))

        assert result is ref

    def test_single_dependency_emits_no_warning(self) -> None:
        ref = _model_ref()
        channel = InMemoryExecutionChannel()
        context = FakeExecutionContext(dependencies=(ref,), channel=channel)

        asyncio.run(resolve_model_ref(context, capability=_CAPABILITY))

        assert channel.emitted == []

    def test_multiple_dependencies_returns_the_first(self) -> None:
        first = _model_ref("1")
        second = _model_ref("2")
        third = _model_ref("3")
        context = FakeExecutionContext(dependencies=(first, second, third))

        result = asyncio.run(resolve_model_ref(context, capability=_CAPABILITY))

        assert result is first

    def test_multiple_dependencies_emits_exactly_one_warning(self) -> None:
        channel = InMemoryExecutionChannel()
        context = FakeExecutionContext(
            dependencies=(_model_ref("1"), _model_ref("2"), _model_ref("3")),
            channel=channel,
        )

        asyncio.run(resolve_model_ref(context, capability=_CAPABILITY))

        warnings = [event for event in channel.emitted if isinstance(event, WarningEvent)]
        assert len(warnings) == 1
        assert warnings[0].code == "extra_dependencies"

    def test_multiple_dependencies_resolves_deterministically_across_calls(self) -> None:
        first = _model_ref("1")
        context_a = FakeExecutionContext(dependencies=(first, _model_ref("2")))
        context_b = FakeExecutionContext(dependencies=(first, _model_ref("2")))

        result_a = asyncio.run(resolve_model_ref(context_a, capability=_CAPABILITY))
        result_b = asyncio.run(resolve_model_ref(context_b, capability=_CAPABILITY))

        assert result_a == result_b == first


class TestResolveBackend:
    def test_empty_mapping_raises_no_backend_available_error(self) -> None:
        policy = FakeModelSelectionPolicy(
            plan=ServingPlan(
                model=_model_ref(),
                backend=BackendId("llama_cpp"),
                quantization=Quantization(scheme="artifact-defined", bits=0),
            )
        )

        try:
            resolve_backend(
                {}, policy, _model_ref(), capability=_CAPABILITY, provider="ChatProvider"
            )
        except NoBackendAvailableError as error:
            assert error.capability == _CAPABILITY
            assert error.provider == "ChatProvider"
        else:
            raise AssertionError("expected NoBackendAvailableError")

    def test_plan_naming_absent_backend_raises_unresolvable_backend_error(self) -> None:
        model = _model_ref()
        plan = ServingPlan(
            model=model,
            backend=BackendId("vllm"),
            quantization=Quantization(scheme="artifact-defined", bits=0),
        )
        policy = FakeModelSelectionPolicy(plan=plan)
        backends = {BackendId("llama_cpp"): object()}

        try:
            resolve_backend(
                backends, policy, model, capability=_CAPABILITY, provider="ChatProvider"
            )
        except UnresolvableBackendError as error:
            assert error.capability == _CAPABILITY
            assert error.backend == BackendId("vllm")
            assert error.available == ("llama_cpp",)
        else:
            raise AssertionError("expected UnresolvableBackendError")

    def test_present_plan_backend_returns_backend_and_plan(self) -> None:
        model = _model_ref()
        plan = ServingPlan(
            model=model,
            backend=BackendId("llama_cpp"),
            quantization=Quantization(scheme="artifact-defined", bits=0),
        )
        policy = FakeModelSelectionPolicy(plan=plan)
        sentinel_backend = object()
        backends = {BackendId("llama_cpp"): sentinel_backend}

        backend, resolved_plan = resolve_backend(
            backends, policy, model, capability=_CAPABILITY, provider="ChatProvider"
        )

        assert backend is sentinel_backend
        assert resolved_plan is plan


class TestReportBuilders:
    def test_completed_report_has_completed_phase(self) -> None:
        report = completed_report(started_at=0.0, trace_id="trace-1")

        assert report.phase == ExecutionPhase.COMPLETED
        assert report.trace_id == "trace-1"

    def test_cancelled_report_has_cancelled_phase(self) -> None:
        report = cancelled_report(started_at=0.0, trace_id="trace-2")

        assert report.phase == ExecutionPhase.CANCELLED
        assert report.trace_id == "trace-2"

    def test_completed_report_carries_no_output(self) -> None:
        report = completed_report(started_at=0.0, trace_id="trace-3")

        assert report.logs == ()
        assert report.failure is None

    def test_cancelled_report_carries_no_output(self) -> None:
        report = cancelled_report(started_at=0.0, trace_id="trace-4")

        assert report.logs == ()
        assert report.failure is None
