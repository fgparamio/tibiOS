"""The fallible wire<->domain boundary (`worker-wire-conversion` spec).

Pure — imports `_pb2` generated types, **never** `grpc` (D13; this
module's isolation is a spot check, task 3a.16, since S2's isolation
guard only covers `transport/` from the outside).

**Reject-don't-guess**: every conversion here either succeeds and
reproduces the wire value, or raises a classified `ConversionError`
subclass from `transport/errors.py`. Nothing is ever defaulted,
guessed, or silently fabricated.
"""

import re
from collections.abc import Iterable

from google.protobuf.message import Message

from tibios_ray.execution.context import ResolvedModelRef
from tibios_ray.execution.ids import AllocationId, ContentHash, ObjectId, ObjectVersion, WorkloadId
from tibios_ray.transport._generated.tibios.primitives.v1 import identity_pb2
from tibios_ray.transport._generated.tibios.worker.v1 import worker_pb2
from tibios_ray.transport.errors import (
    EmptyCapabilityError,
    InvalidObjectVersionError,
    InvalidUlidError,
    MissingFieldError,
)

# Crockford Base32 — the ULID alphabet; excludes I, L, O, U to avoid
# visual confusion. A ULID is exactly 26 characters of this alphabet.
_ULID_ALPHABET = frozenset("0123456789ABCDEFGHJKMNPQRSTVWXYZ")
_ULID_LENGTH = 26

_U64_MAX = (1 << 64) - 1
_UNSIGNED_INTEGER_TEXT = re.compile(r"^[0-9]+$")


def _is_valid_ulid(value: str) -> bool:
    if len(value) != _ULID_LENGTH:
        return False
    return all(char in _ULID_ALPHABET for char in value.upper())


def _require_ulid(value: str, *, field: str) -> str:
    if not _is_valid_ulid(value):
        raise InvalidUlidError(field, value)
    return value


def object_id_from_wire(message: identity_pb2.ObjectId) -> ObjectId:
    """Well-formed `ObjectId` -> domain; malformed `value` raises
    `InvalidUlidError` (`worker-wire-conversion` — "Invalid ULID text is
    rejected, not defaulted")."""

    _require_ulid(message.value, field="ObjectId.value")
    return ObjectId(message.value)


def workload_id_from_wire(message: identity_pb2.WorkloadId) -> WorkloadId:
    """Well-formed `WorkloadId` -> domain; malformed `value` raises
    `InvalidUlidError`."""

    _require_ulid(message.value, field="WorkloadId.value")
    return WorkloadId(message.value)


def allocation_id_from_wire(message: identity_pb2.AllocationId) -> AllocationId:
    """Well-formed `AllocationId` -> domain; malformed `value` raises
    `InvalidUlidError`."""

    _require_ulid(message.value, field="AllocationId.value")
    return AllocationId(message.value)


def object_version_from_wire(message: identity_pb2.ObjectVersion) -> ObjectVersion:
    """Well-formed `ObjectVersion` -> domain `int`; text that is not a
    valid unsigned 64-bit integer raises `InvalidObjectVersionError`
    (`worker-wire-conversion` — "Non-numeric ObjectVersion text is
    rejected, not defaulted")."""

    text = message.value
    if not _UNSIGNED_INTEGER_TEXT.match(text):
        raise InvalidObjectVersionError("ObjectVersion.value", text)
    parsed = int(text)
    if parsed > _U64_MAX:
        raise InvalidObjectVersionError("ObjectVersion.value", text)
    return ObjectVersion(parsed)


def content_hash_from_wire(message: identity_pb2.ContentHash) -> ContentHash:
    """`ContentHash` wraps an arbitrary string with no invalid-content
    case of its own (mirrors tibios-core's `worker-wire-adapter`
    treatment, `design.md` Key Contracts) — wrapped verbatim, never
    validated as a ULID."""

    return ContentHash(message.value)


def _require_field(message: Message, field: str, *, qualified_name: str) -> None:
    if not message.HasField(field):
        raise MissingFieldError(qualified_name)


def resolved_model_ref_from_wire(message: worker_pb2.ResolvedModelRef) -> ResolvedModelRef:
    """A wire `ResolvedModelRef` with any of its three required identity
    fields unset raises `MissingFieldError` naming the missing field, no
    placeholder identity fabricated (`worker-wire-conversion` — "Missing
    required identity field fails conversion")."""

    _require_field(message, "object_id", qualified_name="ResolvedModelRef.object_id")
    _require_field(message, "object_version", qualified_name="ResolvedModelRef.object_version")
    _require_field(message, "content_hash", qualified_name="ResolvedModelRef.content_hash")
    return ResolvedModelRef(
        object_id=object_id_from_wire(message.object_id),
        version=object_version_from_wire(message.object_version),
        content_hash=content_hash_from_wire(message.content_hash),
    )


def capability_from_wire(message: worker_pb2.ExecutionContext) -> str:
    """A wire `ExecutionContext.worker_capability` that is unset raises
    `MissingFieldError`; one that wraps an empty string raises
    `EmptyCapabilityError` — neither is defaulted to an empty capability
    string (`worker-wire-conversion` — "Missing worker_capability is
    rejected" / "Empty worker_capability is rejected"). The boundary
    line: an unset/empty capability means the sender sent nothing
    (`INVALID_ARGUMENT`, the stream never starts); a well-formed
    capability nobody serves is the Runtime's `UnknownCapabilityError`
    problem, not this boundary's (`design.md` Key Contracts)."""

    _require_field(
        message, "worker_capability", qualified_name="ExecutionContext.worker_capability"
    )
    value = message.worker_capability.value
    if value == "":
        raise EmptyCapabilityError()
    return value


def dependencies_from_wire(
    messages: Iterable[worker_pb2.ResolvedModelRef],
) -> tuple[ResolvedModelRef, ...]:
    """Wire `repeated ResolvedModelRef` -> an ordered domain sequence
    preserving wire order (D10). No key of any kind — positional,
    derived from `object_id`, or otherwise — is fabricated: the result
    is a plain `tuple`, never a `Mapping` (`worker-wire-conversion` —
    "Dependencies preserve wire order" / "No key is fabricated for a
    dependency")."""

    return tuple(resolved_model_ref_from_wire(message) for message in messages)


def workload_id_from_cancel_request(message: worker_pb2.CancelRequest) -> WorkloadId:
    """A wire `CancelRequest` with `workload_id` unset raises
    `MissingFieldError`."""

    _require_field(message, "workload_id", qualified_name="CancelRequest.workload_id")
    return workload_id_from_wire(message.workload_id)


def workload_id_from_pulse_request(message: worker_pb2.PulseRequest) -> WorkloadId:
    """A wire `PulseRequest` with `workload_id` unset raises
    `MissingFieldError`."""

    _require_field(message, "workload_id", qualified_name="PulseRequest.workload_id")
    return workload_id_from_wire(message.workload_id)
