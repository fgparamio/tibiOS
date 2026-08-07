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
from collections.abc import Iterable, Mapping
from datetime import timedelta

from google.protobuf import duration_pb2
from google.protobuf.message import Message

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
from tibios_ray.transport._generated.tibios.primitives.v1 import identity_pb2
from tibios_ray.transport._generated.tibios.worker.v1 import worker_pb2
from tibios_ray.transport.errors import (
    EmptyCapabilityError,
    InvalidObjectVersionError,
    InvalidUlidError,
    MissingFieldError,
    NegativeDurationError,
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


def duration_from_wire(duration: duration_pb2.Duration, *, field: str) -> timedelta:
    """`google.protobuf.Duration` -> domain `timedelta`; a negative
    duration raises `NegativeDurationError` (D9 — "A negative
    `google.protobuf.Duration` is a `Permanent` rejection"; Python's
    `timedelta` can hold a negative value unlike Rust's duration type,
    so this is an explicit runtime check). Shared between this slice's
    inbound `AllocationContract` conversion and S3b's outbound
    `ExecutionReport.duration` check — the reason this helper is
    module-level, not nested."""

    parsed = duration.ToTimedelta()
    if parsed < timedelta(0):
        raise NegativeDurationError(field)
    return parsed


def allocation_contract_from_wire(message: worker_pb2.ExecutionContext) -> AllocationContract:
    """A wire `ExecutionContext` with `allocation_contract` unset raises
    `MissingFieldError` — reusing the same type as every other unset
    required field, rather than a dedicated variant, since the failure
    mode is identical: a required message field carries no value and
    nothing is defaulted in its place (D9 — "Absent `allocation_contract`
    on the wire is a `Permanent` rejection, never a default";
    `18-worker-model.md:56` requires the Worker to enforce the maximum
    duration, and a Worker with no contract can enforce nothing). A
    negative `max_execution_duration` raises `NegativeDurationError` via
    `duration_from_wire`."""

    _require_field(
        message, "allocation_contract", qualified_name="ExecutionContext.allocation_contract"
    )
    duration = duration_from_wire(
        message.allocation_contract.max_execution_duration,
        field="AllocationContract.max_execution_duration",
    )
    return AllocationContract(max_execution_duration=duration)


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


def security_context_from_wire(message: worker_pb2.SecurityContext) -> SecurityContext:
    """`SecurityContext` conversion is infallible — three opaque strings,
    carried, never interpreted (``18-worker-model.md:136``). Unlike the
    identity-wrapper fields, an unset `security_context` on the wire is
    NOT rejected: `design.md`'s Key Contracts states retyping is
    deferred as one unit until a security domain exists, so this step
    "adds no rejection scenario" — an unset message simply converts to
    three empty strings."""

    return SecurityContext(
        tenant_id=message.tenant_id,
        principal_id=message.principal_id,
        grant_scope=tuple(message.grant_scope),
    )


def observability_context_from_wire(
    message: worker_pb2.ObservabilityContext,
) -> ObservabilityContext:
    """Also infallible, for the same reason as `security_context_from_wire`."""

    return ObservabilityContext(trace_id=message.trace_id, span_id=message.span_id)


def execution_context_from_wire(
    message: worker_pb2.ExecutionContext,
    *,
    channel: ExecutionChannel,
    cancellation: CancellationToken,
) -> ExecutionContext:
    """Composes a full domain `ExecutionContext` from a well-formed wire
    message, or raises the first classified `ConversionError` a
    malformed field produces. `security_context`, `observability_context`,
    and `execution_parameters` are carried verbatim — never interpreted
    (execution-identity's carried-never-interpreted rule, re-verified at
    this boundary). `channel`/`cancellation` are domain-only (D8): the
    wire has no field for either, so the caller supplies them."""

    _require_field(message, "workload_id", qualified_name="ExecutionContext.workload_id")
    _require_field(message, "allocation_id", qualified_name="ExecutionContext.allocation_id")

    return ExecutionContext(
        workload_id=workload_id_from_wire(message.workload_id),
        allocation_id=allocation_id_from_wire(message.allocation_id),
        capability=capability_from_wire(message),
        allocation_contract=allocation_contract_from_wire(message),
        dependencies=dependencies_from_wire(message.dependencies),
        security_context=security_context_from_wire(message.security_context),
        observability_context=observability_context_from_wire(message.observability_context),
        execution_parameters=dict(message.execution_parameters),
        channel=channel,
        cancellation=cancellation,
    )


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


# --- Outbound (domain -> wire): ExecutionPhase, ExecutionReport, ---
# --- ExecutionEvent, ExecutionPulse (S3b, D16's closed lossiness list) ---

_PHASE_TO_WIRE: Mapping[ExecutionPhase, worker_pb2.ExecutionPhase] = {
    ExecutionPhase.RECEIVED: worker_pb2.EXECUTION_PHASE_RECEIVED,
    ExecutionPhase.PREPARED: worker_pb2.EXECUTION_PHASE_PREPARED,
    ExecutionPhase.RUNNING: worker_pb2.EXECUTION_PHASE_RUNNING,
    ExecutionPhase.COMPLETED: worker_pb2.EXECUTION_PHASE_COMPLETED,
    ExecutionPhase.FAILED: worker_pb2.EXECUTION_PHASE_FAILED,
    ExecutionPhase.CANCELLED: worker_pb2.EXECUTION_PHASE_CANCELLED,
}
assert set(_PHASE_TO_WIRE) == set(ExecutionPhase), (
    "_PHASE_TO_WIRE must exhaustively map every domain ExecutionPhase — "
    "worker-wire-conversion: 'Every domain phase maps to a defined wire phase'"
)


def phase_to_wire(phase: ExecutionPhase) -> worker_pb2.ExecutionPhase:
    """Domain `ExecutionPhase` -> wire `ExecutionPhase` enum int,
    exhaustively mapped via `_PHASE_TO_WIRE`; `EXECUTION_PHASE_UNSPECIFIED`
    is never produced (`worker-wire-conversion` — "Every domain phase maps
    to a defined wire phase"). `_PHASE_TO_WIRE`'s key set is asserted equal
    to `set(ExecutionPhase)` at import time, so this lookup can never
    `KeyError` on a value from the real enum."""

    return _PHASE_TO_WIRE[phase]


def duration_to_wire(duration: timedelta, *, field: str) -> duration_pb2.Duration:
    """Domain `timedelta` -> wire `google.protobuf.Duration`; a negative
    duration raises `NegativeDurationError` (D9 Consequences — "Same
    treatment for `ExecutionReport.duration` outbound"). The outbound
    direction of the shared negative-duration check `duration_from_wire`
    applies inbound, reused here for `ExecutionReport.duration`."""

    if duration < timedelta(0):
        raise NegativeDurationError(field)
    result = duration_pb2.Duration()
    result.FromTimedelta(duration)
    return result


def execution_report_to_wire(report: ExecutionReport) -> worker_pb2.ExecutionReport:
    """Domain `ExecutionReport` -> wire `ExecutionReport` — a lossy
    projection, per D16 (``design.md``):

    - `phase` -> `final_phase` via `phase_to_wire` (never
      `EXECUTION_PHASE_UNSPECIFIED`).
    - `duration` -> `duration` via `duration_to_wire`; a negative value
      raises `NegativeDurationError` (D9 Consequences).
    - `trace_id` -> `trace_id` verbatim (D16 row: "Mapped verbatim").
    - `failure`/`phase` -> `summary`: `failure` set folds into `summary`
      verbatim; `failure is None` folds to `summary == ""` (D16 row:
      "Folded... two tests, not a silent default").
    - `resource_usage`/`metrics` are **never** set on the wire message —
      the wire `ExecutionReport` has no such field at all (D16 row:
      "Dropped, by contract design... The transport does not synthesize
      one"). The wire relocated point-in-time metrics to the event
      stream's `MetricsSnapshot` arm instead; this function performs no
      synthesis from a Report's `resource_usage`/`metrics` into that arm.
    - `logs` is **never** carried onto the wire — the wire `ExecutionReport`
      has no `logs` field (D16 row: "Dropped... the correct fix, if ever
      needed, is a `.proto` change").
    """

    return worker_pb2.ExecutionReport(
        final_phase=phase_to_wire(report.phase),
        duration=duration_to_wire(report.duration, field="ExecutionReport.duration"),
        trace_id=report.trace_id,
        summary=report.failure if report.failure is not None else "",
    )
