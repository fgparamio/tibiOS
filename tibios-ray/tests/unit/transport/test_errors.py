"""Tests for `tibios_ray.transport.errors` — the classified error
hierarchy this boundary raises on rejection (design decision D17).

One hierarchy, two families: `ConversionError` (wire malformed/missing —
raised by `transport/convert.py`, this slice) and `CorrelationError`
(unknown/duplicate `WorkloadId` — raised by S4a's registry, defined here
per D17's single-hierarchy decision). Every member classifies
`ErrorClass.PERMANENT`; nothing in this boundary ever surfaces as a bare
exception or an `UNKNOWN` gRPC status.
"""

from tibios_ray.transport.errors import (
    ConversionError,
    DuplicateWorkloadError,
    EmptyCapabilityError,
    ErrorClass,
    InvalidObjectVersionError,
    InvalidUlidError,
    MissingFieldError,
    NegativeDurationError,
    UnknownWorkloadError,
)


class TestErrorClass:
    def test_has_exactly_transient_permanent_fatal_members(self) -> None:
        assert {member.name for member in ErrorClass} == {"TRANSIENT", "PERMANENT", "FATAL"}


class TestConversionErrorFamily:
    def test_conversion_error_itself_classifies_permanent(self) -> None:
        assert ConversionError("boom").error_class is ErrorClass.PERMANENT

    def test_invalid_ulid_error_classifies_permanent(self) -> None:
        assert (
            InvalidUlidError("WorkloadId.value", "not-a-ulid").error_class is ErrorClass.PERMANENT
        )

    def test_invalid_object_version_error_classifies_permanent(self) -> None:
        assert (
            InvalidObjectVersionError("ObjectVersion.value", "abc").error_class
            is ErrorClass.PERMANENT
        )

    def test_missing_field_error_classifies_permanent(self) -> None:
        assert MissingFieldError("ExecutionContext.workload_id").error_class is ErrorClass.PERMANENT

    def test_empty_capability_error_classifies_permanent(self) -> None:
        assert EmptyCapabilityError().error_class is ErrorClass.PERMANENT

    def test_negative_duration_error_classifies_permanent(self) -> None:
        assert (
            NegativeDurationError("AllocationContract.max_execution_duration").error_class
            is ErrorClass.PERMANENT
        )

    def test_all_five_subclasses_are_conversion_errors(self) -> None:
        assert issubclass(InvalidUlidError, ConversionError)
        assert issubclass(InvalidObjectVersionError, ConversionError)
        assert issubclass(MissingFieldError, ConversionError)
        assert issubclass(EmptyCapabilityError, ConversionError)
        assert issubclass(NegativeDurationError, ConversionError)

    def test_missing_field_error_names_the_missing_field(self) -> None:
        error = MissingFieldError("ExecutionContext.allocation_contract")
        assert "ExecutionContext.allocation_contract" in str(error)


class TestCorrelationErrorFamily:
    def test_unknown_workload_error_classifies_permanent(self) -> None:
        assert UnknownWorkloadError("01J0000000000000000000000").error_class is ErrorClass.PERMANENT

    def test_duplicate_workload_error_classifies_permanent(self) -> None:
        assert (
            DuplicateWorkloadError("01J0000000000000000000000").error_class is ErrorClass.PERMANENT
        )

    def test_both_subclasses_are_correlation_errors(self) -> None:
        from tibios_ray.transport.errors import CorrelationError

        assert issubclass(UnknownWorkloadError, CorrelationError)
        assert issubclass(DuplicateWorkloadError, CorrelationError)
