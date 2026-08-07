"""Tests for `tibios_ray.transport.convert` — the fallible wire<->domain
boundary (`worker-wire-conversion` spec; design decisions D8-D10, D17).

Hand-built `_pb2` messages only — no server, no socket. Every rejection
scenario asserts both the raised type **and** `error_class is
ErrorClass.PERMANENT` (`worker-wire-conversion` — "Every rejection
variant classifies as Permanent").
"""


from collections.abc import Callable
from datetime import timedelta

import pytest
from google.protobuf import duration_pb2

from tibios_ray.execution.context import AllocationContract, ResolvedModelRef
from tibios_ray.execution.events import (
    CheckpointCreated,
    EndOfStream,
    MetricsSnapshot,
    OutputChunk,
    Progress,
    Warning,
)
from tibios_ray.execution.ids import AllocationId, ContentHash, ObjectId, ObjectVersion, WorkloadId
from tibios_ray.execution.report import ExecutionPhase, ExecutionPulse, ExecutionReport
from tibios_ray.testing.cancellation import ManualCancellation
from tibios_ray.testing.channel import InMemoryExecutionChannel
from tibios_ray.transport._generated.tibios.primitives.v1 import identity_pb2
from tibios_ray.transport._generated.tibios.worker.v1 import worker_pb2
from tibios_ray.transport.errors import (
    ConversionError,
    EmptyCapabilityError,
    ErrorClass,
    InvalidObjectVersionError,
    InvalidSequenceError,
    InvalidUlidError,
    MissingFieldError,
    NegativeDurationError,
)

_ULID_A = "01J0000000000000000000000A"
_ULID_B = "01J0000000000000000000000B"
_ULID_C = "01J0000000000000000000000C"


class TestObjectIdFromWire:
    def test_well_formed_object_id_converts_successfully(self) -> None:
        from tibios_ray.transport.convert import object_id_from_wire

        message = identity_pb2.ObjectId(value=_ULID_A)

        assert object_id_from_wire(message) == ObjectId(_ULID_A)

    def test_invalid_ulid_text_is_rejected_not_defaulted(self) -> None:
        from tibios_ray.transport.convert import object_id_from_wire

        message = identity_pb2.ObjectId(value="not-a-ulid")

        with pytest.raises(InvalidUlidError) as excinfo:
            object_id_from_wire(message)
        assert excinfo.value.error_class is ErrorClass.PERMANENT

    def test_empty_string_is_rejected(self) -> None:
        from tibios_ray.transport.convert import object_id_from_wire

        message = identity_pb2.ObjectId(value="")

        with pytest.raises(InvalidUlidError):
            object_id_from_wire(message)


class TestWorkloadIdFromWire:
    def test_well_formed_workload_id_converts_successfully(self) -> None:
        from tibios_ray.transport.convert import workload_id_from_wire

        message = identity_pb2.WorkloadId(value=_ULID_B)

        assert workload_id_from_wire(message) == WorkloadId(_ULID_B)

    def test_invalid_ulid_text_is_rejected_not_defaulted(self) -> None:
        from tibios_ray.transport.convert import workload_id_from_wire

        message = identity_pb2.WorkloadId(value="short")

        with pytest.raises(InvalidUlidError) as excinfo:
            workload_id_from_wire(message)
        assert excinfo.value.error_class is ErrorClass.PERMANENT


class TestAllocationIdFromWire:
    def test_well_formed_allocation_id_converts_successfully(self) -> None:
        from tibios_ray.transport.convert import allocation_id_from_wire

        message = identity_pb2.AllocationId(value=_ULID_C)

        assert allocation_id_from_wire(message) == AllocationId(_ULID_C)

    def test_invalid_ulid_text_is_rejected_not_defaulted(self) -> None:
        from tibios_ray.transport.convert import allocation_id_from_wire

        # Right length, wrong alphabet: 'I', 'L', 'O', 'U' are excluded
        # from Crockford Base32 to avoid visual confusion.
        message = identity_pb2.AllocationId(value="IIIIIIIIIIIIIIIIIIIIIIIIII")

        with pytest.raises(InvalidUlidError) as excinfo:
            allocation_id_from_wire(message)
        assert excinfo.value.error_class is ErrorClass.PERMANENT


class TestObjectVersionFromWire:
    def test_well_formed_object_version_converts_successfully(self) -> None:
        from tibios_ray.transport.convert import object_version_from_wire

        message = identity_pb2.ObjectVersion(value="18")

        assert object_version_from_wire(message) == ObjectVersion(18)

    def test_non_numeric_text_is_rejected_not_defaulted(self) -> None:
        from tibios_ray.transport.convert import object_version_from_wire

        message = identity_pb2.ObjectVersion(value="not-a-number")

        with pytest.raises(InvalidObjectVersionError) as excinfo:
            object_version_from_wire(message)
        assert excinfo.value.error_class is ErrorClass.PERMANENT

    def test_negative_text_is_rejected(self) -> None:
        from tibios_ray.transport.convert import object_version_from_wire

        message = identity_pb2.ObjectVersion(value="-1")

        with pytest.raises(InvalidObjectVersionError):
            object_version_from_wire(message)

    def test_text_exceeding_u64_max_is_rejected(self) -> None:
        from tibios_ray.transport.convert import object_version_from_wire

        message = identity_pb2.ObjectVersion(value=str(2**64))

        with pytest.raises(InvalidObjectVersionError):
            object_version_from_wire(message)


class TestContentHashFromWire:
    def test_well_formed_content_hash_converts_successfully(self) -> None:
        from tibios_ray.transport.convert import content_hash_from_wire

        message = identity_pb2.ContentHash(value="sha256:af2398...")

        assert content_hash_from_wire(message) == ContentHash("sha256:af2398...")


def _well_formed_resolved_model_ref_message() -> worker_pb2.ResolvedModelRef:
    return worker_pb2.ResolvedModelRef(
        object_id=identity_pb2.ObjectId(value=_ULID_A),
        object_version=identity_pb2.ObjectVersion(value="18"),
        content_hash=identity_pb2.ContentHash(value="sha256:af2398..."),
    )


class TestResolvedModelRefFromWire:
    def test_well_formed_message_converts_successfully(self) -> None:
        from tibios_ray.transport.convert import resolved_model_ref_from_wire

        result = resolved_model_ref_from_wire(_well_formed_resolved_model_ref_message())

        assert result == ResolvedModelRef(
            object_id=ObjectId(_ULID_A),
            version=ObjectVersion(18),
            content_hash=ContentHash("sha256:af2398..."),
        )

    def test_missing_object_id_raises_missing_field_error(self) -> None:
        from tibios_ray.transport.convert import resolved_model_ref_from_wire

        message = worker_pb2.ResolvedModelRef(
            object_version=identity_pb2.ObjectVersion(value="18"),
            content_hash=identity_pb2.ContentHash(value="sha256:af2398..."),
        )

        with pytest.raises(MissingFieldError) as excinfo:
            resolved_model_ref_from_wire(message)
        assert "object_id" in str(excinfo.value)
        assert excinfo.value.error_class is ErrorClass.PERMANENT

    def test_missing_object_version_raises_missing_field_error(self) -> None:
        from tibios_ray.transport.convert import resolved_model_ref_from_wire

        message = worker_pb2.ResolvedModelRef(
            object_id=identity_pb2.ObjectId(value=_ULID_A),
            content_hash=identity_pb2.ContentHash(value="sha256:af2398..."),
        )

        with pytest.raises(MissingFieldError) as excinfo:
            resolved_model_ref_from_wire(message)
        assert "object_version" in str(excinfo.value)

    def test_missing_content_hash_raises_missing_field_error(self) -> None:
        from tibios_ray.transport.convert import resolved_model_ref_from_wire

        message = worker_pb2.ResolvedModelRef(
            object_id=identity_pb2.ObjectId(value=_ULID_A),
            object_version=identity_pb2.ObjectVersion(value="18"),
        )

        with pytest.raises(MissingFieldError) as excinfo:
            resolved_model_ref_from_wire(message)
        assert "content_hash" in str(excinfo.value)


class TestDependenciesFromWire:
    def test_preserves_wire_order(self) -> None:
        from tibios_ray.transport.convert import dependencies_from_wire

        first = worker_pb2.ResolvedModelRef(
            object_id=identity_pb2.ObjectId(value=_ULID_A),
            object_version=identity_pb2.ObjectVersion(value="1"),
            content_hash=identity_pb2.ContentHash(value="sha256:first"),
        )
        second = worker_pb2.ResolvedModelRef(
            object_id=identity_pb2.ObjectId(value=_ULID_B),
            object_version=identity_pb2.ObjectVersion(value="2"),
            content_hash=identity_pb2.ContentHash(value="sha256:second"),
        )

        result = dependencies_from_wire([first, second])

        assert result == (
            ResolvedModelRef(
                object_id=ObjectId(_ULID_A),
                version=ObjectVersion(1),
                content_hash=ContentHash("sha256:first"),
            ),
            ResolvedModelRef(
                object_id=ObjectId(_ULID_B),
                version=ObjectVersion(2),
                content_hash=ContentHash("sha256:second"),
            ),
        )

    def test_result_is_a_tuple_with_no_fabricated_key(self) -> None:
        from tibios_ray.transport.convert import dependencies_from_wire

        single = worker_pb2.ResolvedModelRef(
            object_id=identity_pb2.ObjectId(value=_ULID_A),
            object_version=identity_pb2.ObjectVersion(value="1"),
            content_hash=identity_pb2.ContentHash(value="sha256:only"),
        )

        result = dependencies_from_wire([single])

        assert isinstance(result, tuple)
        assert not isinstance(result, dict)

    def test_empty_dependencies_convert_to_empty_tuple(self) -> None:
        from tibios_ray.transport.convert import dependencies_from_wire

        assert dependencies_from_wire([]) == ()


class TestCapabilityFromWire:
    def test_well_formed_capability_converts_successfully(self) -> None:
        from tibios_ray.transport.convert import capability_from_wire

        message = worker_pb2.ExecutionContext(
            worker_capability=worker_pb2.WorkerCapability(value="text-generation")
        )

        assert capability_from_wire(message) == "text-generation"

    def test_missing_worker_capability_raises_missing_field_error(self) -> None:
        from tibios_ray.transport.convert import capability_from_wire

        message = worker_pb2.ExecutionContext()

        with pytest.raises(MissingFieldError) as excinfo:
            capability_from_wire(message)
        assert "worker_capability" in str(excinfo.value)
        assert excinfo.value.error_class is ErrorClass.PERMANENT

    def test_empty_worker_capability_raises_empty_capability_error(self) -> None:
        from tibios_ray.transport.convert import capability_from_wire

        message = worker_pb2.ExecutionContext(
            worker_capability=worker_pb2.WorkerCapability(value="")
        )

        with pytest.raises(EmptyCapabilityError) as excinfo:
            capability_from_wire(message)
        assert excinfo.value.error_class is ErrorClass.PERMANENT


class TestDurationFromWire:
    def test_well_formed_duration_converts_successfully(self) -> None:
        from tibios_ray.transport.convert import duration_from_wire

        duration = duration_pb2.Duration()
        duration.FromTimedelta(timedelta(minutes=5))

        assert duration_from_wire(duration, field="test") == timedelta(minutes=5)

    def test_negative_duration_raises_negative_duration_error(self) -> None:
        from tibios_ray.transport.convert import duration_from_wire

        duration = duration_pb2.Duration(seconds=-1)

        with pytest.raises(NegativeDurationError) as excinfo:
            duration_from_wire(duration, field="AllocationContract.max_execution_duration")
        assert excinfo.value.error_class is ErrorClass.PERMANENT
        assert "AllocationContract.max_execution_duration" in str(excinfo.value)

    def test_zero_duration_is_accepted(self) -> None:
        from tibios_ray.transport.convert import duration_from_wire

        assert duration_from_wire(duration_pb2.Duration(), field="test") == timedelta()


class TestAllocationContractFromWire:
    def test_well_formed_allocation_contract_converts_successfully(self) -> None:
        from tibios_ray.transport.convert import allocation_contract_from_wire

        duration = duration_pb2.Duration()
        duration.FromTimedelta(timedelta(minutes=5))
        message = worker_pb2.ExecutionContext(
            allocation_contract=worker_pb2.AllocationContract(max_execution_duration=duration)
        )

        result = allocation_contract_from_wire(message)

        assert result == AllocationContract(max_execution_duration=timedelta(minutes=5))

    def test_missing_allocation_contract_raises_classified_rejection(self) -> None:
        from tibios_ray.transport.convert import allocation_contract_from_wire

        message = worker_pb2.ExecutionContext()

        with pytest.raises(MissingFieldError) as excinfo:
            allocation_contract_from_wire(message)
        assert "allocation_contract" in str(excinfo.value)
        assert excinfo.value.error_class is ErrorClass.PERMANENT

    def test_negative_max_execution_duration_raises_negative_duration_error(self) -> None:
        from tibios_ray.transport.convert import allocation_contract_from_wire

        message = worker_pb2.ExecutionContext(
            allocation_contract=worker_pb2.AllocationContract(
                max_execution_duration=duration_pb2.Duration(seconds=-1)
            )
        )

        with pytest.raises(NegativeDurationError) as excinfo:
            allocation_contract_from_wire(message)
        assert excinfo.value.error_class is ErrorClass.PERMANENT


def _well_formed_execution_context_message() -> worker_pb2.ExecutionContext:
    duration = duration_pb2.Duration()
    duration.FromTimedelta(timedelta(minutes=5))
    return worker_pb2.ExecutionContext(
        workload_id=identity_pb2.WorkloadId(value=_ULID_A),
        allocation_id=identity_pb2.AllocationId(value=_ULID_B),
        allocation_contract=worker_pb2.AllocationContract(max_execution_duration=duration),
        dependencies=[
            worker_pb2.ResolvedModelRef(
                object_id=identity_pb2.ObjectId(value=_ULID_C),
                object_version=identity_pb2.ObjectVersion(value="1"),
                content_hash=identity_pb2.ContentHash(value="sha256:dep"),
            )
        ],
        security_context=worker_pb2.SecurityContext(
            tenant_id="tenant-a", principal_id="principal-a", grant_scope=["read", "write"]
        ),
        observability_context=worker_pb2.ObservabilityContext(
            trace_id="trace-a", span_id="span-a"
        ),
        execution_parameters={"temperature": "0.7"},
        worker_capability=worker_pb2.WorkerCapability(value="chat.generate"),
    )


class TestExecutionContextFromWire:
    def test_composes_full_domain_execution_context(self) -> None:
        from tibios_ray.transport.convert import execution_context_from_wire

        channel = InMemoryExecutionChannel()
        cancellation = ManualCancellation()

        result = execution_context_from_wire(
            _well_formed_execution_context_message(), channel=channel, cancellation=cancellation
        )

        assert result.workload_id == WorkloadId(_ULID_A)
        assert result.allocation_id == AllocationId(_ULID_B)
        assert result.capability == "chat.generate"
        assert result.allocation_contract == AllocationContract(
            max_execution_duration=timedelta(minutes=5)
        )
        assert result.dependencies == (
            ResolvedModelRef(
                object_id=ObjectId(_ULID_C),
                version=ObjectVersion(1),
                content_hash=ContentHash("sha256:dep"),
            ),
        )
        assert result.security_context.tenant_id == "tenant-a"
        assert result.security_context.principal_id == "principal-a"
        assert result.security_context.grant_scope == ("read", "write")
        assert result.observability_context.trace_id == "trace-a"
        assert result.observability_context.span_id == "span-a"
        assert dict(result.execution_parameters) == {"temperature": "0.7"}
        assert result.channel is channel
        assert result.cancellation is cancellation

    def test_missing_workload_id_raises_missing_field_error(self) -> None:
        from tibios_ray.transport.convert import execution_context_from_wire

        message = _well_formed_execution_context_message()
        message.ClearField("workload_id")

        with pytest.raises(MissingFieldError) as excinfo:
            execution_context_from_wire(
                message, channel=InMemoryExecutionChannel(), cancellation=ManualCancellation()
            )
        assert "workload_id" in str(excinfo.value)

    def test_missing_allocation_id_raises_missing_field_error(self) -> None:
        from tibios_ray.transport.convert import execution_context_from_wire

        message = _well_formed_execution_context_message()
        message.ClearField("allocation_id")

        with pytest.raises(MissingFieldError) as excinfo:
            execution_context_from_wire(
                message, channel=InMemoryExecutionChannel(), cancellation=ManualCancellation()
            )
        assert "allocation_id" in str(excinfo.value)

    def test_security_and_observability_context_conversion_is_infallible_when_unset(self) -> None:
        # design.md: "SecurityContext stays three opaque strings... The
        # wire->domain step for it is therefore infallible and adds no
        # rejection scenario." Leaving security_context/observability_context
        # unset on the wire must not raise — it converts to empty strings.
        from tibios_ray.transport.convert import execution_context_from_wire

        message = _well_formed_execution_context_message()
        message.ClearField("security_context")
        message.ClearField("observability_context")

        result = execution_context_from_wire(
            message, channel=InMemoryExecutionChannel(), cancellation=ManualCancellation()
        )

        assert result.security_context.tenant_id == ""
        assert result.observability_context.trace_id == ""


class TestWorkloadIdFromCancelRequest:
    def test_well_formed_request_converts_successfully(self) -> None:
        from tibios_ray.transport.convert import workload_id_from_cancel_request

        message = worker_pb2.CancelRequest(workload_id=identity_pb2.WorkloadId(value=_ULID_B))

        assert workload_id_from_cancel_request(message) == WorkloadId(_ULID_B)

    def test_missing_workload_id_raises_missing_field_error(self) -> None:
        from tibios_ray.transport.convert import workload_id_from_cancel_request

        message = worker_pb2.CancelRequest()

        with pytest.raises(MissingFieldError) as excinfo:
            workload_id_from_cancel_request(message)
        assert "workload_id" in str(excinfo.value)
        assert excinfo.value.error_class is ErrorClass.PERMANENT


class TestWorkloadIdFromPulseRequest:
    def test_well_formed_request_converts_successfully(self) -> None:
        from tibios_ray.transport.convert import workload_id_from_pulse_request

        message = worker_pb2.PulseRequest(workload_id=identity_pb2.WorkloadId(value=_ULID_B))

        assert workload_id_from_pulse_request(message) == WorkloadId(_ULID_B)

    def test_missing_workload_id_raises_missing_field_error(self) -> None:
        from tibios_ray.transport.convert import workload_id_from_pulse_request

        message = worker_pb2.PulseRequest()

        with pytest.raises(MissingFieldError) as excinfo:
            workload_id_from_pulse_request(message)
        assert "workload_id" in str(excinfo.value)
        assert excinfo.value.error_class is ErrorClass.PERMANENT


def _rejection_scenarios() -> list[tuple[str, Callable[[], object]]]:
    """Every rejection variant introduced by this slice (3a.4-3a.12), one
    entry per distinct malformed-input shape. Shared by 3a.14 (classifies
    `ErrorClass.PERMANENT`) and 3a.15 (never a bare/unguarded exception)
    so both cross-cutting assertions run over the same scenario set."""

    from tibios_ray.transport.convert import (
        allocation_contract_from_wire,
        allocation_id_from_wire,
        capability_from_wire,
        duration_from_wire,
        object_id_from_wire,
        object_version_from_wire,
        resolved_model_ref_from_wire,
        workload_id_from_wire,
    )

    return [
        (
            "invalid_ulid_object_id",
            lambda: object_id_from_wire(identity_pb2.ObjectId(value="not-a-ulid")),
        ),
        (
            "invalid_ulid_workload_id",
            lambda: workload_id_from_wire(identity_pb2.WorkloadId(value="not-a-ulid")),
        ),
        (
            "invalid_ulid_allocation_id",
            lambda: allocation_id_from_wire(identity_pb2.AllocationId(value="not-a-ulid")),
        ),
        (
            "non_numeric_object_version",
            lambda: object_version_from_wire(identity_pb2.ObjectVersion(value="not-a-number")),
        ),
        (
            "unset_required_identity_field",
            lambda: resolved_model_ref_from_wire(worker_pb2.ResolvedModelRef()),
        ),
        (
            "unset_worker_capability",
            lambda: capability_from_wire(worker_pb2.ExecutionContext()),
        ),
        (
            "empty_worker_capability",
            lambda: capability_from_wire(
                worker_pb2.ExecutionContext(
                    worker_capability=worker_pb2.WorkerCapability(value="")
                )
            ),
        ),
        (
            "missing_allocation_contract",
            lambda: allocation_contract_from_wire(worker_pb2.ExecutionContext()),
        ),
        (
            "negative_duration",
            lambda: duration_from_wire(duration_pb2.Duration(seconds=-1), field="test"),
        ),
    ]


class TestEveryRejectionClassifiesPermanent:
    """3a.14 — `worker-wire-conversion`: "Every rejection variant
    classifies as Permanent"."""

    @pytest.mark.parametrize(
        "convert", [scenario for _, scenario in _rejection_scenarios()],
        ids=[label for label, _ in _rejection_scenarios()],
    )
    def test_rejection_classifies_permanent(self, convert: Callable[[], object]) -> None:
        with pytest.raises(ConversionError) as excinfo:
            convert()
        assert excinfo.value.error_class is ErrorClass.PERMANENT


class TestNoConversionPathPanics:
    """3a.15 — `worker-wire-conversion`: "No conversion path panics on
    malformed input". Every rejection scenario must raise a
    `ConversionError` subclass specifically, never a bare/unguarded
    exception (`KeyError`, `ValueError`, `AttributeError`, ...)."""

    @pytest.mark.parametrize(
        "convert", [scenario for _, scenario in _rejection_scenarios()],
        ids=[label for label, _ in _rejection_scenarios()],
    )
    def test_rejection_raises_conversion_error_not_a_bare_exception(
        self, convert: Callable[[], object]
    ) -> None:
        try:
            convert()
        except ConversionError:
            return
        except Exception as unguarded:  # noqa: BLE001 - this is the assertion itself
            pytest.fail(
                f"conversion path panicked with a bare {type(unguarded).__name__} "
                "instead of raising a ConversionError subclass"
            )
        else:
            pytest.fail("expected conversion to raise ConversionError, but it succeeded")


# --- S3b — Outbound Conversion (Event/Report/Pulse) + D16 Lossiness ---


class TestPhaseToWire:
    """3b.1 — `worker-wire-conversion`: "Every domain phase maps to a
    defined wire phase"."""

    @pytest.mark.parametrize(
        ("phase", "expected"),
        [
            (ExecutionPhase.RECEIVED, worker_pb2.EXECUTION_PHASE_RECEIVED),
            (ExecutionPhase.PREPARED, worker_pb2.EXECUTION_PHASE_PREPARED),
            (ExecutionPhase.RUNNING, worker_pb2.EXECUTION_PHASE_RUNNING),
            (ExecutionPhase.COMPLETED, worker_pb2.EXECUTION_PHASE_COMPLETED),
            (ExecutionPhase.FAILED, worker_pb2.EXECUTION_PHASE_FAILED),
            (ExecutionPhase.CANCELLED, worker_pb2.EXECUTION_PHASE_CANCELLED),
        ],
    )
    def test_every_domain_phase_maps_to_a_defined_wire_phase(
        self, phase: ExecutionPhase, expected: int
    ) -> None:
        from tibios_ray.transport.convert import phase_to_wire

        result = phase_to_wire(phase)

        assert result == expected
        assert result != worker_pb2.EXECUTION_PHASE_UNSPECIFIED

    def test_phase_to_wire_key_set_equals_every_domain_phase(self) -> None:
        from tibios_ray.transport.convert import _PHASE_TO_WIRE

        assert set(_PHASE_TO_WIRE) == set(ExecutionPhase)


class TestDurationToWire:
    """3b.2 — outbound direction of D9's negative-`Duration` rejection
    (D9 Consequences — "Same treatment for `ExecutionReport.duration`
    outbound")."""

    def test_positive_timedelta_converts_successfully(self) -> None:
        from tibios_ray.transport.convert import duration_to_wire

        result = duration_to_wire(timedelta(seconds=5), field="test")

        assert result.ToTimedelta() == timedelta(seconds=5)

    def test_negative_timedelta_raises_negative_duration_error(self) -> None:
        from tibios_ray.transport.convert import duration_to_wire

        with pytest.raises(NegativeDurationError) as excinfo:
            duration_to_wire(timedelta(seconds=-1), field="ExecutionReport.duration")
        assert excinfo.value.error_class is ErrorClass.PERMANENT
        assert "ExecutionReport.duration" in str(excinfo.value)


def _report(**overrides: object) -> ExecutionReport:
    defaults: dict[str, object] = {
        "phase": ExecutionPhase.COMPLETED,
        "duration": timedelta(seconds=2),
        "resource_usage": {"cpu_seconds": 1.5},
        "metrics": {"tokens": 42.0},
        "trace_id": "trace-1",
        "logs": ("line one", "line two"),
        "failure": None,
    }
    defaults.update(overrides)
    return ExecutionReport(**defaults)  # type: ignore[arg-type]


class TestExecutionReportToWire:
    """3b.2-3b.6 — `execution_report_to_wire`'s outbound fields plus D16's
    closed lossiness list for `ExecutionReport`."""

    def test_negative_duration_raises_negative_duration_error(self) -> None:
        from tibios_ray.transport.convert import execution_report_to_wire

        report = _report(duration=timedelta(seconds=-1))

        with pytest.raises(NegativeDurationError) as excinfo:
            execution_report_to_wire(report)
        assert excinfo.value.error_class is ErrorClass.PERMANENT

    def test_trace_id_maps_verbatim(self) -> None:
        from tibios_ray.transport.convert import execution_report_to_wire

        report = _report(trace_id="trace-verbatim")

        result = execution_report_to_wire(report)

        assert result.trace_id == "trace-verbatim"

    def test_failed_report_sets_summary_to_failure_verbatim(self) -> None:
        from tibios_ray.transport.convert import execution_report_to_wire

        report = _report(phase=ExecutionPhase.FAILED, failure="something broke")

        result = execution_report_to_wire(report)

        assert result.summary == "something broke"

    def test_successful_report_sets_summary_to_empty_string(self) -> None:
        from tibios_ray.transport.convert import execution_report_to_wire

        report = _report(phase=ExecutionPhase.COMPLETED, failure=None)

        result = execution_report_to_wire(report)

        assert result.summary == ""

    def test_final_phase_and_duration_map_correctly(self) -> None:
        from tibios_ray.transport.convert import execution_report_to_wire

        report = _report(phase=ExecutionPhase.CANCELLED, duration=timedelta(seconds=3))

        result = execution_report_to_wire(report)

        assert result.final_phase == worker_pb2.EXECUTION_PHASE_CANCELLED
        assert result.duration.ToTimedelta() == timedelta(seconds=3)

    def test_wire_report_never_carries_resource_usage_or_metrics(self) -> None:
        """D16 row: `resource_usage`/`metrics` — "Dropped, by contract
        design... The transport does not synthesize one." The wire
        `ExecutionReport` message structurally has no such field
        (`__slots__ = ("final_phase", "duration", "trace_id", "summary")`),
        so this asserts the wire type itself carries no such field rather
        than merely checking a value."""
        from tibios_ray.transport.convert import execution_report_to_wire

        report = _report(resource_usage={"cpu_seconds": 99.0}, metrics={"tokens": 100.0})

        result = execution_report_to_wire(report)

        assert not hasattr(result, "resource_usage")
        assert not hasattr(result, "metrics")

    def test_wire_report_never_carries_logs(self) -> None:
        """D16 row: `logs` — "Dropped... the correct fix, if ever needed,
        is a `.proto` change." The wire `ExecutionReport` message
        structurally has no `logs` field."""
        from tibios_ray.transport.convert import execution_report_to_wire

        report = _report(logs=("a log line",))

        result = execution_report_to_wire(report)

        assert not hasattr(result, "logs")


class TestExecutionPulseToWire:
    """3b.9 — `execution_pulse_to_wire`'s phase/health-only mapping; D16
    row: `ExecutionPulse.detail` — "Dropped. Set by nothing, anywhere
    (verified)"."""

    def test_phase_and_healthy_map_correctly(self) -> None:
        from tibios_ray.transport.convert import execution_pulse_to_wire

        pulse = ExecutionPulse(phase=ExecutionPhase.RUNNING, healthy=True)

        result = execution_pulse_to_wire(pulse)

        assert result.phase == worker_pb2.EXECUTION_PHASE_RUNNING
        assert result.healthy is True

    def test_unhealthy_pulse_maps_healthy_false(self) -> None:
        from tibios_ray.transport.convert import execution_pulse_to_wire

        pulse = ExecutionPulse(phase=ExecutionPhase.RECEIVED, healthy=False)

        result = execution_pulse_to_wire(pulse)

        assert result.healthy is False

    def test_wire_pulse_never_carries_detail(self) -> None:
        """The wire `ExecutionPulse` message structurally has no `detail`
        field (`__slots__ = ("phase", "healthy")`)."""
        from tibios_ray.transport.convert import execution_pulse_to_wire

        pulse = ExecutionPulse(phase=ExecutionPhase.RUNNING, healthy=True, detail="some detail")

        result = execution_pulse_to_wire(pulse)

        assert not hasattr(result, "detail")

    def test_nothing_in_src_constructs_execution_pulse_with_detail_set(self) -> None:
        """D16 row: "Set by nothing, anywhere (verified)" — a recursive
        source search confirms no production code constructs an
        `ExecutionPulse` with `detail` set to a non-None value."""
        import ast
        from pathlib import Path

        src_root = Path(__file__).resolve().parents[3] / "src" / "tibios_ray"
        offenders: list[str] = []
        for path in src_root.rglob("*.py"):
            if "_generated" in path.parts:
                continue
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                if name != "ExecutionPulse":
                    continue
                for keyword in node.keywords:
                    if keyword.arg == "detail" and not (
                        isinstance(keyword.value, ast.Constant) and keyword.value.value is None
                    ):
                        offenders.append(str(path))

        assert offenders == []


class TestExecutionEventToWireWarning:
    """3b.7 — D16 row: `Warning.code` — "Dropped... inventing a `[code]
    msg` parse format on a frozen contract creates an unversioned
    side-channel"."""

    def test_message_maps_verbatim(self) -> None:
        from tibios_ray.transport.convert import execution_event_to_wire

        event = Warning(message="disk space low", code="LOW_DISK")

        result = execution_event_to_wire(event)

        assert result.warning.message == "disk space low"

    def test_code_is_dropped_and_never_prefixed_into_message(self) -> None:
        from tibios_ray.transport.convert import execution_event_to_wire

        event = Warning(message="disk space low", code="LOW_DISK")

        result = execution_event_to_wire(event)

        assert not hasattr(result.warning, "code")
        assert "LOW_DISK" not in result.warning.message
        assert result.warning.message == "disk space low"


class TestExecutionEventToWireProgress:
    """3b.10 — D16 row: `Progress.message` — "proto3 has no absent
    scalar; documented"."""

    def test_message_present_maps_verbatim(self) -> None:
        from tibios_ray.transport.convert import execution_event_to_wire

        event = Progress(fraction_complete=0.25, message="halfway there")

        result = execution_event_to_wire(event)

        assert result.progress.fraction_complete == 0.25
        assert result.progress.message == "halfway there"

    def test_none_message_maps_to_empty_string(self) -> None:
        from tibios_ray.transport.convert import execution_event_to_wire

        event = Progress(fraction_complete=0.5, message=None)

        result = execution_event_to_wire(event)

        assert result.progress.message == ""


class TestExecutionEventToWireOutputChunk:
    """3b.11 — D16 row: `OutputChunk.sequence` — "a Worker bug, surfaced
    rather than truncated"."""

    def test_well_formed_chunk_converts_successfully(self) -> None:
        from tibios_ray.transport.convert import execution_event_to_wire

        event = OutputChunk(data=b"hello", sequence=7)

        result = execution_event_to_wire(event)

        assert result.output_chunk.data == b"hello"
        assert result.output_chunk.sequence == 7

    def test_negative_sequence_raises_invalid_sequence_error(self) -> None:
        from tibios_ray.transport.convert import execution_event_to_wire

        event = OutputChunk(data=b"hello", sequence=-1)

        with pytest.raises(InvalidSequenceError) as excinfo:
            execution_event_to_wire(event)
        assert excinfo.value.error_class is ErrorClass.PERMANENT

    def test_sequence_at_or_above_2_pow_64_raises_invalid_sequence_error(self) -> None:
        from tibios_ray.transport.convert import execution_event_to_wire

        event = OutputChunk(data=b"hello", sequence=2**64)

        with pytest.raises(InvalidSequenceError) as excinfo:
            execution_event_to_wire(event)
        assert excinfo.value.error_class is ErrorClass.PERMANENT

    def test_max_valid_sequence_converts_successfully_not_truncated(self) -> None:
        from tibios_ray.transport.convert import execution_event_to_wire

        event = OutputChunk(data=b"hello", sequence=2**64 - 1)

        result = execution_event_to_wire(event)

        assert result.output_chunk.sequence == 2**64 - 1


class TestExecutionEventToWireCheckpointCreated:
    """3b.12 — D16 row: `CheckpointCreated.checkpoint_id` — "the owning
    domain defines validity and the adapter does not second-guess,"
    mirroring `ContentHash`'s treatment."""

    def test_checkpoint_id_wraps_verbatim_into_checkpoint_object_id(self) -> None:
        from tibios_ray.transport.convert import execution_event_to_wire

        event = CheckpointCreated(checkpoint_id="not-a-ulid-at-all")

        result = execution_event_to_wire(event)

        assert result.checkpoint_created.checkpoint_object_id.value == "not-a-ulid-at-all"

    def test_no_ulid_validation_performed_at_this_boundary(self) -> None:
        """A well-formed ULID converts too, proving the same code path
        handles both — no branch performs ULID validation here."""
        from tibios_ray.transport.convert import execution_event_to_wire

        event = CheckpointCreated(checkpoint_id=_ULID_A)

        result = execution_event_to_wire(event)

        assert result.checkpoint_created.checkpoint_object_id.value == _ULID_A


class TestExecutionEventToWireMetricsSnapshot:
    """`MetricsSnapshot` — a trivial pass-through arm with a direct wire
    home (the relocation target D16 names for `ExecutionReport.resource_usage`/
    `metrics`, which have no wire home of their own)."""

    def test_metrics_map_directly_onto_the_wire(self) -> None:
        from tibios_ray.transport.convert import execution_event_to_wire

        event = MetricsSnapshot(metrics={"tokens_per_second": 42.0, "vram_gb": 3.5})

        result = execution_event_to_wire(event)

        assert dict(result.metrics_snapshot.metrics) == {
            "tokens_per_second": 42.0,
            "vram_gb": 3.5,
        }

    def test_empty_metrics_map_converts_to_an_empty_wire_map(self) -> None:
        from tibios_ray.transport.convert import execution_event_to_wire

        event = MetricsSnapshot(metrics={})

        result = execution_event_to_wire(event)

        assert dict(result.metrics_snapshot.metrics) == {}


class TestExecutionEventToWireEndOfStream:
    """3b.8 — D16 row: `EndOfStream.reason` — "Dropped, and demonstrably
    non-lossy on the only path that sets it"."""

    def test_reason_never_reaches_the_wire(self) -> None:
        """The wire `EndOfStream` message is structurally empty
        (`__slots__ = ()`)."""
        from tibios_ray.transport.convert import execution_event_to_wire

        event = EndOfStream(reason="something failed")

        result = execution_event_to_wire(event)

        assert result.HasField("end_of_stream")
        assert not hasattr(worker_pb2.EndOfStream(), "reason")

    def test_end_of_stream_reason_is_demonstrably_non_lossy_via_worker_runtime(self) -> None:
        """Drives a real `WorkerRuntime.execute` against a failing
        fixture Provider (never a hand-rolled `EndOfStream` in
        isolation): `EndOfStream.reason` is dropped by
        `execution_event_to_wire`, but the same information reaches the
        wire via `report.failure` -> `execution_report_to_wire`'s
        `summary` fold (3b.4) — proving the drop is non-lossy on the
        only path (`worker_runtime.py`'s `execute()`) that ever sets
        `reason`."""
        import asyncio

        from tibios_ray.backends.adapter import BackendId
        from tibios_ray.capabilities.descriptor import (
            CapabilityDescriptor,
            CapabilityFlags,
            ModelFamily,
        )
        from tibios_ray.capabilities.names import CapabilityName
        from tibios_ray.execution.context import ExecutionContext
        from tibios_ray.runtime.registry import CapabilityRegistry
        from tibios_ray.runtime.worker_runtime import WorkerRuntime
        from tibios_ray.testing import FakeExecutionContext, InMemoryExecutionChannel, StubProvider
        from tibios_ray.transport.convert import execution_event_to_wire, execution_report_to_wire

        async def _raising_execute(context: ExecutionContext) -> ExecutionReport:
            raise RuntimeError("provider exploded")

        descriptor = CapabilityDescriptor(
            capability=CapabilityName("boom.explode"),
            families=frozenset({ModelFamily("deepseek")}),
            backends=frozenset({BackendId("llama_cpp")}),
            flags=CapabilityFlags(streaming=True),
        )
        provider = StubProvider(capability_descriptor=descriptor, on_execute=_raising_execute)
        channel = InMemoryExecutionChannel()
        registry = CapabilityRegistry([provider])
        runtime = WorkerRuntime(registry)
        context = FakeExecutionContext(capability="boom.explode", channel=channel)

        report = asyncio.run(runtime.execute(context))

        assert report.failure is not None
        assert "provider exploded" in report.failure
        end_of_stream_event = channel.emitted[-1]
        assert isinstance(end_of_stream_event, EndOfStream)
        assert end_of_stream_event.reason == report.failure

        wire_event = execution_event_to_wire(end_of_stream_event)
        assert not hasattr(worker_pb2.EndOfStream(), "reason")
        assert wire_event.HasField("end_of_stream")

        wire_report = execution_report_to_wire(report)
        assert wire_report.summary == report.failure == end_of_stream_event.reason
