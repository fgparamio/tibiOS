"""The classified error hierarchy for the `transport` boundary (design
decision D17): one `ErrorClass` enum, two exception families.

**The Worker classifies the nature of the failure; the Runtime decides
what to do about it** (``18-worker-model.md:122``) — `error_class` is not
a retry instruction, it is a classification.

- `ConversionError` — raised by `transport/convert.py` (this slice) when
  a wire message cannot be turned into its domain counterpart: an
  invalid ULID, an unparseable `ObjectVersion`, an unset required field,
  a missing/empty `worker_capability`, a missing `allocation_contract`,
  or a negative `Duration`.
- `CorrelationError` — raised by S4a's in-flight registry when a
  `WorkloadId` is unknown (O3) or duplicated (O4). Defined here, not in
  S4a, per D17's single-hierarchy decision: both families live in one
  module so the servicer (S4b) has one place to look up the fixed
  gRPC status mapping (conversion rejection -> `INVALID_ARGUMENT`;
  unknown `WorkloadId` -> `NOT_FOUND`; duplicate `WorkloadId` ->
  `ALREADY_EXISTS`).

Every member of both families classifies `ErrorClass.PERMANENT` — three
enum members exist so that assertion is meaningful rather than a
tautology. Nothing at this boundary ever surfaces as `UNKNOWN`.
"""

from enum import Enum


class ErrorClass(Enum):
    """Mirrors tibios-core's `ErrorClass` (``04-error-handling.md``)."""

    TRANSIENT = "transient"
    PERMANENT = "permanent"
    FATAL = "fatal"


class ConversionError(Exception):
    """Base of the wire-to-domain conversion rejection family. Every
    member classifies `ErrorClass.PERMANENT` — a malformed or missing
    wire value is never retryable by resending the same bytes."""

    error_class: ErrorClass = ErrorClass.PERMANENT


class InvalidUlidError(ConversionError):
    """A wire `ObjectId`/`WorkloadId`/`AllocationId` payload is not a
    syntactically valid ULID (wrong length, invalid character set, or
    empty) — never defaulted, never substituted."""

    def __init__(self, field: str, value: str) -> None:
        self.field = field
        self.value = value
        super().__init__(f"{field} is not a valid ULID: {value!r}")


class InvalidObjectVersionError(ConversionError):
    """A wire `ObjectVersion.value` is not a valid unsigned 64-bit
    integer in text form — never defaulted to `0` or any other value."""

    def __init__(self, field: str, value: str) -> None:
        self.field = field
        self.value = value
        super().__init__(f"{field} is not a valid unsigned 64-bit integer: {value!r}")


class MissingFieldError(ConversionError):
    """A required wire message field is unset. Names the missing field
    so the caller (and the eventual gRPC status detail) is specific —
    never a placeholder identity or contract is fabricated in its
    place."""

    def __init__(self, field: str) -> None:
        self.field = field
        super().__init__(f"required field is unset: {field}")


class EmptyCapabilityError(ConversionError):
    """A wire `ExecutionContext.worker_capability` is present but wraps
    an empty string. Distinct from `MissingFieldError` (the field is
    set, its value is merely empty) because the wire distinguishes
    "unset message" from "message with an empty scalar" and this
    boundary preserves that distinction rather than collapsing both
    into one rejection type."""

    def __init__(self) -> None:
        super().__init__("worker_capability.value is empty")


class NegativeDurationError(ConversionError):
    """A `google.protobuf.Duration` (inbound) or a domain `timedelta`
    (outbound, S3b) represents a negative value. Python's `timedelta`
    can hold a negative value unlike Rust's duration type, so this is an
    explicit runtime check, not a type-level guarantee."""

    def __init__(self, field: str) -> None:
        self.field = field
        super().__init__(f"{field} is negative")


class CorrelationError(Exception):
    """Base of the in-flight-`WorkloadId` correlation rejection family
    (consumed by S4a's registry and S4b's servicer). Every member
    classifies `ErrorClass.PERMANENT`."""

    error_class: ErrorClass = ErrorClass.PERMANENT


class UnknownWorkloadError(CorrelationError):
    """`Cancel`/`Pulse` named a `WorkloadId` the registry has no record
    of (O3)."""

    def __init__(self, workload_id: str) -> None:
        self.workload_id = workload_id
        super().__init__(f"unknown WorkloadId: {workload_id}")


class DuplicateWorkloadError(CorrelationError):
    """`SubmitJob` named a `WorkloadId` already registered as in-flight
    (O4). The original registration is unaffected."""

    def __init__(self, workload_id: str) -> None:
        self.workload_id = workload_id
        super().__init__(f"duplicate WorkloadId: {workload_id}")
