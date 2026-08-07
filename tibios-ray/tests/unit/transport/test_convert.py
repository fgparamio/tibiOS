"""Tests for `tibios_ray.transport.convert` — the fallible wire<->domain
boundary (`worker-wire-conversion` spec; design decisions D8-D10, D17).

Hand-built `_pb2` messages only — no server, no socket. Every rejection
scenario asserts both the raised type **and** `error_class is
ErrorClass.PERMANENT` (`worker-wire-conversion` — "Every rejection
variant classifies as Permanent").
"""


import pytest

from tibios_ray.execution.context import ResolvedModelRef
from tibios_ray.execution.ids import AllocationId, ContentHash, ObjectId, ObjectVersion, WorkloadId
from tibios_ray.transport._generated.tibios.primitives.v1 import identity_pb2
from tibios_ray.transport._generated.tibios.worker.v1 import worker_pb2
from tibios_ray.transport.errors import (
    EmptyCapabilityError,
    ErrorClass,
    InvalidObjectVersionError,
    InvalidUlidError,
    MissingFieldError,
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
