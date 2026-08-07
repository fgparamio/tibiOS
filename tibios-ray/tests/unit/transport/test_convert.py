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
from tibios_ray.execution.ids import AllocationId, ContentHash, ObjectId, ObjectVersion, WorkloadId
from tibios_ray.testing.cancellation import ManualCancellation
from tibios_ray.testing.channel import InMemoryExecutionChannel
from tibios_ray.transport._generated.tibios.primitives.v1 import identity_pb2
from tibios_ray.transport._generated.tibios.worker.v1 import worker_pb2
from tibios_ray.transport.errors import (
    ConversionError,
    EmptyCapabilityError,
    ErrorClass,
    InvalidObjectVersionError,
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
