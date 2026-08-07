//! Fallible wire <-> domain conversion for the Worker gRPC contract.
//!
//! Implements `worker-wire-adapter/spec.md`: the boundary between the
//! generated `tonic`/`prost` wire types (`super::tibios::{primitives,
//! worker}::v1`) and their `runtime-primitives`/`runtime-allocation`/
//! `runtime-worker` domain counterparts. Covers the five identity-wrapper
//! messages (`ObjectId`, `ObjectVersion`, `ContentHash`, `WorkloadId`,
//! `AllocationId`), the two oneofs (`ExecutionEvent`'s six arms,
//! `ExecutionResponse`'s two arms), and — now that the Worker domain types
//! exist (`worker-inbound-port`) — `ExecutionContext`, `ExecutionReport`,
//! `ExecutionPulse`, and `AllocationContract`. Every `TryFrom`/`From` impl
//! in this file targets a real domain type; it defines no local mirror
//! type for any of them (`worker-wire-adapter/spec.md` — "Conversions
//! Target Real Domain Types, No Local Mirror Remains"). The one
//! adapter-local type this file still defines, `ResponseFrame`, is not a
//! mirror: the domain has no `ExecutionResponse`-shaped type to mirror —
//! the terminal Report travels as `execute`'s return value, never as a
//! frame on a channel (design.md D10 Consequences) — so `ResponseFrame` is
//! this boundary's own routing type distinguishing "this frame is an
//! event" from "this frame is the terminal report". A routing enum (this
//! shape) was chosen over two independent `TryFrom` impls because it keeps
//! every existing rejection scenario's test shape unchanged (`tasks.md`
//! 5a.3's flagged implementation choice). `ConversionError` implements the
//! public `runtime_primitives::Classify` trait directly; no private copy
//! of that trait is defined in this crate.

use runtime_primitives::Classify;

use super::tibios::{primitives::v1 as identity_proto, worker::v1 as worker_proto};

/// The wire's `google.protobuf.Duration`, compiled locally
/// (`build.rs`'s `compile_well_known_types(true)`) rather than pulled in
/// via the `prost-types` crate.
type WireDuration = super::google::protobuf::Duration;

/// Every rejection this boundary can produce. Every variant classifies
/// `Permanent` (`04-error-handling.md:119`) — invalid wire content is
/// never retried and never silently defaulted.
// `pub` here is required by `#![deny(private_interfaces)]`: this type is
// the `Error` associated type on `TryFrom<identity_proto::X> for
// runtime_primitives::X` impls, and `runtime_primitives::X` is a genuinely
// public (cross-crate) type, so the associated type's visibility must
// match. This does not widen this boundary's real external surface: every
// enclosing module (`convert`, `grpc`, `adapters`) stays non-`pub`, so
// nothing outside this crate can name `ConversionError`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ConversionError {
    /// A wire identity-wrapper message's text field was not a valid ULID.
    /// The `&'static str` names which identity type was being parsed.
    InvalidUlid(&'static str, runtime_primitives::IdentityParseError),
    /// A wire `ObjectVersion` message's text field was not a valid
    /// unsigned 64-bit integer.
    InvalidObjectVersion(core::num::ParseIntError),
    /// A required message-typed field was left unset (`None`) at the wire
    /// level, with no meaningful empty/absent domain variant to
    /// substitute. Names the missing field.
    MissingField(&'static str),
    /// `ExecutionEvent.arm` was unset at the wire level.
    UnsetExecutionEventOneof,
    /// `ExecutionResponse.payload` was unset at the wire level.
    UnsetExecutionResponseOneof,
    /// A wire `ExecutionPhase` was `EXECUTION_PHASE_UNSPECIFIED` (proto
    /// tag zero) or an unrecognized discriminant — neither is a domain
    /// `ExecutionPhase` value (`runtime-primitives/spec.md` — "An unset
    /// wire ExecutionPhase classifies Permanent").
    UnspecifiedExecutionPhase,
    /// A wire `google.protobuf.Duration` carried a negative `seconds` or
    /// `nanos` field. `core::time::Duration` cannot represent a negative
    /// span, so it is rejected rather than silently made positive.
    NegativeDuration,
}

impl core::fmt::Display for ConversionError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::InvalidUlid(type_name, source) => {
                write!(f, "invalid {type_name} on the wire: {source}")
            }
            Self::InvalidObjectVersion(source) => {
                write!(f, "invalid ObjectVersion text on the wire: {source}")
            }
            Self::MissingField(field) => {
                write!(f, "required field {field:?} was unset on the wire")
            }
            Self::UnsetExecutionEventOneof => {
                write!(f, "ExecutionEvent.arm was unset on the wire")
            }
            Self::UnsetExecutionResponseOneof => {
                write!(f, "ExecutionResponse.payload was unset on the wire")
            }
            Self::UnspecifiedExecutionPhase => {
                write!(f, "wire ExecutionPhase was EXECUTION_PHASE_UNSPECIFIED")
            }
            Self::NegativeDuration => {
                write!(f, "wire Duration had a negative seconds or nanos field")
            }
        }
    }
}

impl runtime_primitives::Classify for ConversionError {
    fn classify(&self) -> runtime_primitives::ErrorClass {
        match self {
            Self::InvalidUlid(..)
            | Self::InvalidObjectVersion(_)
            | Self::MissingField(_)
            | Self::UnsetExecutionEventOneof
            | Self::UnsetExecutionResponseOneof
            | Self::UnspecifiedExecutionPhase
            | Self::NegativeDuration => runtime_primitives::ErrorClass::Permanent,
        }
    }
}

/// A `ConversionError` (rejected wire content, e.g. mid-stream on
/// `SubmitJob`'s response) is itself a `WorkerError::Transport` — the
/// classification `Classify` already assigns it (`Permanent`, every
/// variant) becomes the `Transport` variant's `kind`, and `Display`'s
/// output becomes the carried `message`. `RayWorker::execute` relies on
/// this to turn a malformed `ExecutionResponse` frame into the same error
/// shape every other transport failure produces.
impl From<ConversionError> for crate::error::WorkerError {
    fn from(error: ConversionError) -> Self {
        Self::Transport {
            kind: error.classify(),
            message: error.to_string(),
        }
    }
}

impl From<runtime_primitives::ObjectId> for identity_proto::ObjectId {
    fn from(value: runtime_primitives::ObjectId) -> Self {
        Self {
            value: value.to_string(),
        }
    }
}

impl TryFrom<identity_proto::ObjectId> for runtime_primitives::ObjectId {
    type Error = ConversionError;

    fn try_from(value: identity_proto::ObjectId) -> Result<Self, Self::Error> {
        Self::parse(&value.value).map_err(|source| ConversionError::InvalidUlid("ObjectId", source))
    }
}

impl From<runtime_primitives::ObjectVersion> for identity_proto::ObjectVersion {
    fn from(value: runtime_primitives::ObjectVersion) -> Self {
        Self {
            value: value.as_u64().to_string(),
        }
    }
}

impl TryFrom<identity_proto::ObjectVersion> for runtime_primitives::ObjectVersion {
    type Error = ConversionError;

    fn try_from(value: identity_proto::ObjectVersion) -> Result<Self, Self::Error> {
        value
            .value
            .parse::<u64>()
            .map(Self::from_u64)
            .map_err(ConversionError::InvalidObjectVersion)
    }
}

impl From<runtime_primitives::ContentHash> for identity_proto::ContentHash {
    fn from(value: runtime_primitives::ContentHash) -> Self {
        Self {
            value: value.digest().to_string(),
        }
    }
}

impl TryFrom<identity_proto::ContentHash> for runtime_primitives::ContentHash {
    type Error = ConversionError;

    fn try_from(value: identity_proto::ContentHash) -> Result<Self, Self::Error> {
        Ok(Self::new(value.value))
    }
}

impl From<runtime_primitives::WorkloadId> for identity_proto::WorkloadId {
    fn from(value: runtime_primitives::WorkloadId) -> Self {
        Self {
            value: value.to_string(),
        }
    }
}

impl TryFrom<identity_proto::WorkloadId> for runtime_primitives::WorkloadId {
    type Error = ConversionError;

    fn try_from(value: identity_proto::WorkloadId) -> Result<Self, Self::Error> {
        Self::parse(&value.value)
            .map_err(|source| ConversionError::InvalidUlid("WorkloadId", source))
    }
}

impl From<runtime_primitives::AllocationId> for identity_proto::AllocationId {
    fn from(value: runtime_primitives::AllocationId) -> Self {
        Self {
            value: value.to_string(),
        }
    }
}

impl TryFrom<identity_proto::AllocationId> for runtime_primitives::AllocationId {
    type Error = ConversionError;

    fn try_from(value: identity_proto::AllocationId) -> Result<Self, Self::Error> {
        Self::parse(&value.value)
            .map_err(|source| ConversionError::InvalidUlid("AllocationId", source))
    }
}

/// Converts a wire `google.protobuf.Duration` into `core::time::Duration`.
/// `google.protobuf.Duration` permits a negative `seconds`/`nanos` pair;
/// `core::time::Duration` cannot represent a negative span, so either
/// field being negative is rejected rather than silently made positive
/// (`tasks.md` 5a.5). Shared by both `AllocationContract.max_execution_duration`
/// and `ExecutionReport.duration`.
fn duration_from_proto(value: WireDuration) -> Result<core::time::Duration, ConversionError> {
    if value.seconds < 0 || value.nanos < 0 {
        return Err(ConversionError::NegativeDuration);
    }
    Ok(core::time::Duration::new(
        value.seconds as u64,
        value.nanos as u32,
    ))
}

impl TryFrom<worker_proto::ExecutionPhase> for crate::execution::report::ExecutionPhase {
    type Error = ConversionError;

    fn try_from(value: worker_proto::ExecutionPhase) -> Result<Self, Self::Error> {
        match value {
            worker_proto::ExecutionPhase::Unspecified => {
                Err(ConversionError::UnspecifiedExecutionPhase)
            }
            worker_proto::ExecutionPhase::Received => Ok(Self::Received),
            worker_proto::ExecutionPhase::Prepared => Ok(Self::Prepared),
            worker_proto::ExecutionPhase::Running => Ok(Self::Running),
            worker_proto::ExecutionPhase::Completed => Ok(Self::Completed),
            worker_proto::ExecutionPhase::Failed => Ok(Self::Failed),
            worker_proto::ExecutionPhase::Cancelled => Ok(Self::Cancelled),
        }
    }
}

/// Resolves an `ExecutionReport`/`ExecutionPulse` phase tag — stored as a
/// raw `i32` at the wire level because proto3 enum fields must tolerate an
/// unrecognized discriminant — into the domain `ExecutionPhase`. An
/// unrecognized `i32` collapses to `Unspecified` and is rejected the same
/// way the wire's own tag-zero value is.
fn execution_phase_from_i32(
    raw: i32,
) -> Result<crate::execution::report::ExecutionPhase, ConversionError> {
    worker_proto::ExecutionPhase::try_from(raw)
        .unwrap_or(worker_proto::ExecutionPhase::Unspecified)
        .try_into()
}

impl TryFrom<worker_proto::AllocationContract> for runtime_allocation::AllocationContract {
    type Error = ConversionError;

    fn try_from(value: worker_proto::AllocationContract) -> Result<Self, Self::Error> {
        let max_execution_duration = value
            .max_execution_duration
            .ok_or(ConversionError::MissingField("max_execution_duration"))?;
        let max_execution_duration = duration_from_proto(max_execution_duration)?;
        Ok(Self::new(max_execution_duration))
    }
}

impl TryFrom<worker_proto::ResolvedModelRef> for crate::execution::context::ResolvedDependency {
    type Error = ConversionError;

    fn try_from(value: worker_proto::ResolvedModelRef) -> Result<Self, Self::Error> {
        let object_id = value
            .object_id
            .ok_or(ConversionError::MissingField("object_id"))?
            .try_into()?;
        let object_version = value
            .object_version
            .ok_or(ConversionError::MissingField("object_version"))?
            .try_into()?;
        let content_hash = value
            .content_hash
            .ok_or(ConversionError::MissingField("content_hash"))?
            .try_into()?;
        Ok(Self::new(object_id, object_version, content_hash))
    }
}

impl From<crate::execution::context::WorkerCapability> for worker_proto::WorkerCapability {
    fn from(value: crate::execution::context::WorkerCapability) -> Self {
        Self {
            value: value.name().to_string(),
        }
    }
}

impl TryFrom<worker_proto::WorkerCapability> for crate::execution::context::WorkerCapability {
    type Error = ConversionError;

    fn try_from(value: worker_proto::WorkerCapability) -> Result<Self, Self::Error> {
        if value.value.is_empty() {
            return Err(ConversionError::MissingField("worker_capability"));
        }
        Ok(Self::new(value.value))
    }
}

impl From<worker_proto::SecurityContext> for crate::execution::context::SecurityContext {
    fn from(value: worker_proto::SecurityContext) -> Self {
        Self::new(value.tenant_id, value.principal_id, value.grant_scope)
    }
}

impl From<worker_proto::ObservabilityContext> for crate::execution::context::ObservabilityContext {
    fn from(value: worker_proto::ObservabilityContext) -> Self {
        Self::new(value.trace_id, value.span_id)
    }
}

/// Converts a `core::time::Duration` into the wire's `google.protobuf.Duration`.
/// Infallible: every `Duration` value is representable (`seconds`/`nanos` are
/// both non-negative by construction). The reverse of `duration_from_proto`.
fn duration_to_proto(value: core::time::Duration) -> WireDuration {
    WireDuration {
        seconds: value.as_secs() as i64,
        nanos: value.subsec_nanos() as i32,
    }
}

impl From<runtime_allocation::AllocationContract> for worker_proto::AllocationContract {
    fn from(value: runtime_allocation::AllocationContract) -> Self {
        Self {
            max_execution_duration: Some(duration_to_proto(value.max_execution_duration())),
        }
    }
}

impl From<crate::execution::context::ResolvedDependency> for worker_proto::ResolvedModelRef {
    fn from(value: crate::execution::context::ResolvedDependency) -> Self {
        Self {
            object_id: Some(value.object_id().into()),
            object_version: Some(value.object_version().into()),
            content_hash: Some(value.content_hash().clone().into()),
        }
    }
}

impl From<crate::execution::context::SecurityContext> for worker_proto::SecurityContext {
    fn from(value: crate::execution::context::SecurityContext) -> Self {
        Self {
            tenant_id: value.tenant_id().to_string(),
            principal_id: value.principal_id().to_string(),
            grant_scope: value.grant_scope().to_vec(),
        }
    }
}

impl From<crate::execution::context::ObservabilityContext> for worker_proto::ObservabilityContext {
    fn from(value: crate::execution::context::ObservabilityContext) -> Self {
        Self {
            trace_id: value.trace_id().to_string(),
            span_id: value.span_id().to_string(),
        }
    }
}

impl From<crate::execution::context::ExecutionContext> for worker_proto::ExecutionContext {
    fn from(value: crate::execution::context::ExecutionContext) -> Self {
        Self {
            workload_id: Some(value.workload_id().into()),
            allocation_id: Some(value.allocation_id().into()),
            allocation_contract: Some(value.allocation_contract().into()),
            dependencies: value
                .dependencies()
                .iter()
                .cloned()
                .map(Into::into)
                .collect(),
            security_context: Some(value.security_context().clone().into()),
            observability_context: Some(value.observability_context().clone().into()),
            execution_parameters: value.execution_parameters().clone().into_iter().collect(),
            worker_capability: Some(value.worker_capability().clone().into()),
        }
    }
}

impl From<worker_proto::CancelAck> for crate::execution::report::CancelAck {
    fn from(_value: worker_proto::CancelAck) -> Self {
        Self
    }
}

impl TryFrom<worker_proto::ExecutionContext> for crate::execution::context::ExecutionContext {
    type Error = ConversionError;

    fn try_from(value: worker_proto::ExecutionContext) -> Result<Self, Self::Error> {
        let workload_id = value
            .workload_id
            .ok_or(ConversionError::MissingField("workload_id"))?
            .try_into()?;
        let allocation_id = value
            .allocation_id
            .ok_or(ConversionError::MissingField("allocation_id"))?
            .try_into()?;
        let allocation_contract = value
            .allocation_contract
            .ok_or(ConversionError::MissingField("allocation_contract"))?
            .try_into()?;
        let dependencies = value
            .dependencies
            .into_iter()
            .map(TryInto::try_into)
            .collect::<Result<Vec<_>, _>>()?;
        let security_context = value
            .security_context
            .ok_or(ConversionError::MissingField("security_context"))?
            .into();
        let observability_context = value
            .observability_context
            .ok_or(ConversionError::MissingField("observability_context"))?
            .into();
        // `execution_parameters` conversion itself is infallible: the wire's
        // `HashMap<String, String>` becomes the domain's `BTreeMap<String,
        // String>` (D10 Consequences), a plain re-keying with no fallible
        // step (`tasks.md` 5a.10).
        let execution_parameters = value.execution_parameters.into_iter().collect();
        let worker_capability = value
            .worker_capability
            .ok_or(ConversionError::MissingField("worker_capability"))?
            .try_into()?;

        Ok(Self::new(
            workload_id,
            allocation_id,
            allocation_contract,
            dependencies,
            security_context,
            observability_context,
            execution_parameters,
            worker_capability,
        ))
    }
}

impl From<worker_proto::OutputChunk> for crate::execution::event::OutputChunk {
    fn from(value: worker_proto::OutputChunk) -> Self {
        Self {
            data: value.data,
            sequence: value.sequence,
        }
    }
}

impl From<worker_proto::Progress> for crate::execution::event::Progress {
    fn from(value: worker_proto::Progress) -> Self {
        Self {
            fraction_complete: value.fraction_complete,
            message: value.message,
        }
    }
}

impl From<worker_proto::Warning> for crate::execution::event::Warning {
    fn from(value: worker_proto::Warning) -> Self {
        Self {
            message: value.message,
        }
    }
}

/// `checkpoint_object_id` has no meaningful empty/absent domain variant,
/// so it stays fallible — the one arm among the six that cannot be a
/// plain `From`.
impl TryFrom<worker_proto::CheckpointCreated> for crate::execution::event::CheckpointCreated {
    type Error = ConversionError;

    fn try_from(value: worker_proto::CheckpointCreated) -> Result<Self, Self::Error> {
        let checkpoint_object_id = value
            .checkpoint_object_id
            .ok_or(ConversionError::MissingField("checkpoint_object_id"))?
            .try_into()?;
        Ok(Self {
            checkpoint_object_id,
        })
    }
}

impl From<worker_proto::MetricsSnapshot> for crate::execution::event::MetricsSnapshot {
    fn from(value: worker_proto::MetricsSnapshot) -> Self {
        Self {
            metrics: value.metrics.into_iter().collect(),
        }
    }
}

impl From<worker_proto::EndOfStream> for crate::execution::event::EndOfStream {
    fn from(_value: worker_proto::EndOfStream) -> Self {
        Self
    }
}

impl TryFrom<worker_proto::ExecutionEvent> for crate::execution::event::ExecutionEvent {
    type Error = ConversionError;

    fn try_from(value: worker_proto::ExecutionEvent) -> Result<Self, Self::Error> {
        use worker_proto::execution_event::Arm;

        match value.arm {
            Some(Arm::OutputChunk(v)) => Ok(Self::OutputChunk(v.into())),
            Some(Arm::Progress(v)) => Ok(Self::Progress(v.into())),
            Some(Arm::Warning(v)) => Ok(Self::Warning(v.into())),
            Some(Arm::CheckpointCreated(v)) => Ok(Self::CheckpointCreated(v.try_into()?)),
            Some(Arm::MetricsSnapshot(v)) => Ok(Self::MetricsSnapshot(v.into())),
            Some(Arm::EndOfStream(v)) => Ok(Self::EndOfStream(v.into())),
            None => Err(ConversionError::UnsetExecutionEventOneof),
        }
    }
}

impl TryFrom<worker_proto::ExecutionReport> for crate::execution::report::ExecutionReport {
    type Error = ConversionError;

    fn try_from(value: worker_proto::ExecutionReport) -> Result<Self, Self::Error> {
        let final_phase = execution_phase_from_i32(value.final_phase)?;
        let duration = value
            .duration
            .ok_or(ConversionError::MissingField("duration"))?;
        let duration = duration_from_proto(duration)?;
        Ok(Self {
            final_phase,
            duration,
            trace_id: value.trace_id,
            summary: value.summary,
        })
    }
}

impl TryFrom<worker_proto::ExecutionPulse> for crate::execution::report::ExecutionPulse {
    type Error = ConversionError;

    fn try_from(value: worker_proto::ExecutionPulse) -> Result<Self, Self::Error> {
        let phase = execution_phase_from_i32(value.phase)?;
        Ok(Self {
            phase,
            healthy: value.healthy,
        })
    }
}

/// This boundary's own routing type for the `ExecutionResponse` envelope:
/// "this frame is an event" vs. "this frame is the terminal report". Not a
/// mirror of a domain type — the domain has no `ExecutionResponse`-shaped
/// type at all (the Report travels as `execute`'s return value, never as a
/// channel frame; design.md D10 Consequences) — so this is genuinely
/// adapter-only routing, exactly the case `worker-wire-adapter/spec.md`'s
/// "no local mirror" requirement carves out (`tasks.md` 5a.3).
///
/// `pub(super)`: `RayWorker::execute` (`adapters/grpc/ray_worker.rs`, a
/// sibling module under `grpc`) routes `SubmitJob` response frames through
/// this type. Still confined to the `grpc` subtree — never `pub` — so it
/// stays outside this crate's public surface.
///
/// `dead_code` is allowed here (not at module scope): `RayWorker` is this
/// type's real caller, and `RayWorker` itself is only reachable from
/// `runtime`'s Composition Root (a later phase of
/// `worker-grpc-client-adapter`, out of scope for this slice) — so this
/// type is unreachable in a plain (non-test) library build until that
/// wiring lands, even though `ray_worker.rs` already calls it.
#[allow(dead_code)]
#[derive(Debug, Clone, PartialEq)]
pub(super) enum ResponseFrame {
    Event(crate::execution::event::ExecutionEvent),
    Report(crate::execution::report::ExecutionReport),
}

impl TryFrom<worker_proto::ExecutionResponse> for ResponseFrame {
    type Error = ConversionError;

    fn try_from(value: worker_proto::ExecutionResponse) -> Result<Self, Self::Error> {
        use worker_proto::execution_response::Payload;

        match value.payload {
            Some(Payload::Event(v)) => Ok(Self::Event(v.try_into()?)),
            Some(Payload::Report(v)) => Ok(Self::Report(v.try_into()?)),
            None => Err(ConversionError::UnsetExecutionResponseOneof),
        }
    }
}

impl crate::error::WorkerError {
    /// Maps a `tonic::Status` into a `WorkerError`, per design.md D5.
    /// `NotFound`/`AlreadyExists` reuse the existing correlation-failure
    /// variants — which is why this takes `workload_id` rather than being a
    /// plain `From<tonic::Status>` impl: a bare `Status` carries no
    /// correlation of its own, only the call site (which already knows the
    /// `WorkloadId` it made the RPC for) does. Every other code becomes
    /// `Transport`, classified by `transport_kind`. Defined here rather
    /// than in `error.rs` because this crate's architecture guard forbids
    /// any `tonic::` token outside the private adapter module.
    ///
    /// `dead_code` is allowed here (not at module scope): `RayWorker`
    /// (`adapters/grpc/ray_worker.rs`) is this function's real caller, but
    /// `RayWorker` itself awaits Composition-Root wiring (a later phase,
    /// out of scope for this slice), so this stays unreachable in a plain
    /// (non-test) library build until then.
    #[allow(dead_code)]
    pub(crate) fn from_status(
        status: tonic::Status,
        workload_id: runtime_primitives::WorkloadId,
    ) -> Self {
        match status.code() {
            tonic::Code::NotFound => Self::UnknownWorkload(workload_id),
            tonic::Code::AlreadyExists => Self::DuplicateWorkload(workload_id),
            code => Self::Transport {
                kind: transport_kind(code),
                message: status.message().to_string(),
            },
        }
    }
}

/// Buckets a `tonic::Code` into `Transient`/`Permanent` per design.md D5's
/// table. A code the table does not name (e.g. `Cancelled`) defaults to
/// `Permanent`: retry-looping an unrecognized rejection is worse than giving
/// up once on it.
///
/// `dead_code` is allowed here (not at module scope): `from_status` is this
/// function's only caller, and `from_status` is itself unreachable outside
/// `#[cfg(test)]` until `RayWorker` is wired into the Composition Root (a
/// later phase, out of scope for this slice).
#[allow(dead_code)]
fn transport_kind(code: tonic::Code) -> runtime_primitives::ErrorClass {
    use tonic::Code;
    match code {
        Code::Unavailable
        | Code::DeadlineExceeded
        | Code::Aborted
        | Code::ResourceExhausted
        | Code::Unknown => runtime_primitives::ErrorClass::Transient,
        _ => runtime_primitives::ErrorClass::Permanent,
    }
}

#[cfg(test)]
mod tests {
    use super::{ConversionError, ResponseFrame, WireDuration, identity_proto, worker_proto};
    use crate::error::WorkerError;
    use crate::execution::context::{
        ExecutionContext, ObservabilityContext, ResolvedDependency, SecurityContext,
        WorkerCapability,
    };
    use crate::execution::event::{CheckpointCreated, ExecutionEvent};
    use crate::execution::report::{CancelAck, ExecutionPhase};
    use runtime_allocation::AllocationContract;
    use runtime_primitives::{
        AllocationId, Classify, ContentHash, ErrorClass, ObjectId, ObjectVersion, WorkloadId,
    };

    #[test]
    fn object_id_round_trips_through_wire() {
        let original = ObjectId::new();
        let wire: identity_proto::ObjectId = original.into();
        let parsed = ObjectId::try_from(wire).unwrap();
        assert_eq!(parsed, original);
    }

    #[test]
    fn object_id_rejects_invalid_ulid_text() {
        let wire = identity_proto::ObjectId {
            value: "not-a-valid-ulid".to_string(),
        };
        let result = ObjectId::try_from(wire);
        assert_eq!(
            result,
            Err(ConversionError::InvalidUlid(
                "ObjectId",
                ObjectId::parse("not-a-valid-ulid").unwrap_err()
            ))
        );
    }

    #[test]
    fn workload_id_round_trips_through_wire() {
        let original = WorkloadId::new();
        let wire: identity_proto::WorkloadId = original.into();
        let parsed = WorkloadId::try_from(wire).unwrap();
        assert_eq!(parsed, original);
    }

    #[test]
    fn workload_id_rejects_invalid_ulid_text() {
        let wire = identity_proto::WorkloadId {
            value: "not-a-valid-ulid".to_string(),
        };
        let result = WorkloadId::try_from(wire);
        assert!(matches!(
            result,
            Err(ConversionError::InvalidUlid("WorkloadId", _))
        ));
    }

    #[test]
    fn allocation_id_round_trips_through_wire() {
        let original = AllocationId::new();
        let wire: identity_proto::AllocationId = original.into();
        let parsed = AllocationId::try_from(wire).unwrap();
        assert_eq!(parsed, original);
    }

    #[test]
    fn allocation_id_rejects_invalid_ulid_text() {
        let wire = identity_proto::AllocationId {
            value: "not-a-valid-ulid".to_string(),
        };
        let result = AllocationId::try_from(wire);
        assert!(matches!(
            result,
            Err(ConversionError::InvalidUlid("AllocationId", _))
        ));
    }

    #[test]
    fn object_version_round_trips_through_wire() {
        let original = ObjectVersion::from_u64(42);
        let wire: identity_proto::ObjectVersion = original.into();
        let parsed = ObjectVersion::try_from(wire).unwrap();
        assert_eq!(parsed, original);
    }

    #[test]
    fn object_version_rejects_non_numeric_text() {
        let wire = identity_proto::ObjectVersion {
            value: "not-a-number".to_string(),
        };
        let result = ObjectVersion::try_from(wire);
        assert!(matches!(
            result,
            Err(ConversionError::InvalidObjectVersion(_))
        ));
    }

    #[test]
    fn content_hash_round_trips_through_wire() {
        let original = ContentHash::new("sha256:af23");
        let wire: identity_proto::ContentHash = original.clone().into();
        let parsed = ContentHash::try_from(wire).unwrap();
        assert_eq!(parsed, original);
    }

    #[test]
    fn worker_capability_round_trips_through_wire() {
        let original = WorkerCapability::new("chat.generate");
        let wire: worker_proto::WorkerCapability = original.clone().into();
        let parsed = WorkerCapability::try_from(wire).unwrap();
        assert_eq!(parsed, original);
    }

    #[test]
    fn worker_capability_rejects_unset_message() {
        let wire = worker_proto::WorkerCapability {
            value: String::new(),
        };
        let result = WorkerCapability::try_from(wire);
        assert_eq!(
            result,
            Err(ConversionError::MissingField("worker_capability"))
        );
    }

    #[test]
    fn worker_capability_rejects_empty_value() {
        let wire = worker_proto::WorkerCapability {
            value: String::new(),
        };
        let result = WorkerCapability::try_from(wire);
        assert_eq!(
            result,
            Err(ConversionError::MissingField("worker_capability"))
        );
    }

    #[test]
    fn checkpoint_created_rejects_unset_checkpoint_object_id() {
        let wire = worker_proto::CheckpointCreated {
            checkpoint_object_id: None,
        };
        let result = CheckpointCreated::try_from(wire);
        assert_eq!(
            result,
            Err(ConversionError::MissingField("checkpoint_object_id"))
        );
        let message = format!("{}", result.unwrap_err());
        assert!(message.contains("checkpoint_object_id"));
    }

    fn valid_checkpoint_object_id() -> identity_proto::ObjectId {
        identity_proto::ObjectId {
            value: ObjectId::new().to_string(),
        }
    }

    #[test]
    fn execution_event_output_chunk_arm_converts() {
        let wire = worker_proto::ExecutionEvent {
            arm: Some(worker_proto::execution_event::Arm::OutputChunk(
                worker_proto::OutputChunk {
                    data: vec![1, 2, 3],
                    sequence: 7,
                },
            )),
        };
        let result = ExecutionEvent::try_from(wire).unwrap();
        assert!(matches!(result, ExecutionEvent::OutputChunk(_)));
    }

    #[test]
    fn execution_event_progress_arm_converts() {
        let wire = worker_proto::ExecutionEvent {
            arm: Some(worker_proto::execution_event::Arm::Progress(
                worker_proto::Progress {
                    fraction_complete: 0.5,
                    message: "halfway".to_string(),
                },
            )),
        };
        let result = ExecutionEvent::try_from(wire).unwrap();
        assert!(matches!(result, ExecutionEvent::Progress(_)));
    }

    #[test]
    fn execution_event_warning_arm_converts() {
        let wire = worker_proto::ExecutionEvent {
            arm: Some(worker_proto::execution_event::Arm::Warning(
                worker_proto::Warning {
                    message: "careful".to_string(),
                },
            )),
        };
        let result = ExecutionEvent::try_from(wire).unwrap();
        assert!(matches!(result, ExecutionEvent::Warning(_)));
    }

    #[test]
    fn execution_event_checkpoint_created_arm_converts() {
        let object_id = valid_checkpoint_object_id();
        let expected = ObjectId::try_from(object_id.clone()).unwrap();
        let wire = worker_proto::ExecutionEvent {
            arm: Some(worker_proto::execution_event::Arm::CheckpointCreated(
                worker_proto::CheckpointCreated {
                    checkpoint_object_id: Some(object_id),
                },
            )),
        };
        let result = ExecutionEvent::try_from(wire).unwrap();
        match result {
            ExecutionEvent::CheckpointCreated(checkpoint) => {
                assert_eq!(checkpoint.checkpoint_object_id, expected);
            }
            _ => panic!("expected CheckpointCreated arm"),
        }
    }

    #[test]
    fn execution_event_checkpoint_created_arm_rejects_missing_object_id() {
        let wire = worker_proto::ExecutionEvent {
            arm: Some(worker_proto::execution_event::Arm::CheckpointCreated(
                worker_proto::CheckpointCreated {
                    checkpoint_object_id: None,
                },
            )),
        };
        let result = ExecutionEvent::try_from(wire);
        assert_eq!(
            result,
            Err(ConversionError::MissingField("checkpoint_object_id"))
        );
    }

    #[test]
    fn execution_event_metrics_snapshot_arm_converts() {
        let mut metrics = std::collections::HashMap::new();
        metrics.insert("latency_ms".to_string(), 12.5);
        let wire = worker_proto::ExecutionEvent {
            arm: Some(worker_proto::execution_event::Arm::MetricsSnapshot(
                worker_proto::MetricsSnapshot { metrics },
            )),
        };
        let result = ExecutionEvent::try_from(wire).unwrap();
        assert!(matches!(result, ExecutionEvent::MetricsSnapshot(_)));
    }

    #[test]
    fn execution_event_end_of_stream_arm_converts() {
        let wire = worker_proto::ExecutionEvent {
            arm: Some(worker_proto::execution_event::Arm::EndOfStream(
                worker_proto::EndOfStream {},
            )),
        };
        let result = ExecutionEvent::try_from(wire).unwrap();
        assert!(matches!(result, ExecutionEvent::EndOfStream(_)));
    }

    #[test]
    fn execution_event_rejects_unset_oneof() {
        let wire = worker_proto::ExecutionEvent { arm: None };
        let result = ExecutionEvent::try_from(wire);
        assert_eq!(result, Err(ConversionError::UnsetExecutionEventOneof));
    }

    #[test]
    fn execution_response_event_arm_converts() {
        let wire = worker_proto::ExecutionResponse {
            payload: Some(worker_proto::execution_response::Payload::Event(
                worker_proto::ExecutionEvent {
                    arm: Some(worker_proto::execution_event::Arm::EndOfStream(
                        worker_proto::EndOfStream {},
                    )),
                },
            )),
        };
        let result = ResponseFrame::try_from(wire).unwrap();
        assert!(matches!(result, ResponseFrame::Event(_)));
    }

    #[test]
    fn execution_response_report_arm_converts() {
        let wire = worker_proto::ExecutionResponse {
            payload: Some(worker_proto::execution_response::Payload::Report(
                worker_proto::ExecutionReport {
                    final_phase: worker_proto::ExecutionPhase::Completed as i32,
                    duration: Some(WireDuration {
                        seconds: 3,
                        nanos: 0,
                    }),
                    trace_id: "trace-1".to_string(),
                    summary: "done".to_string(),
                },
            )),
        };
        let result = ResponseFrame::try_from(wire).unwrap();
        assert!(matches!(result, ResponseFrame::Report(_)));
    }

    #[test]
    fn execution_response_rejects_unset_oneof() {
        let wire = worker_proto::ExecutionResponse { payload: None };
        let result = ResponseFrame::try_from(wire);
        assert_eq!(result, Err(ConversionError::UnsetExecutionResponseOneof));
    }

    #[test]
    fn every_conversion_error_variant_classifies_permanent() {
        let variants = vec![
            ConversionError::InvalidUlid("ObjectId", ObjectId::parse("").unwrap_err()),
            ConversionError::InvalidObjectVersion("x".parse::<u64>().unwrap_err()),
            ConversionError::MissingField("checkpoint_object_id"),
            ConversionError::UnsetExecutionEventOneof,
            ConversionError::UnsetExecutionResponseOneof,
            ConversionError::UnspecifiedExecutionPhase,
            ConversionError::NegativeDuration,
        ];
        for variant in variants {
            assert_eq!(variant.classify(), ErrorClass::Permanent);
        }
    }

    #[test]
    fn conversion_error_display_is_not_empty() {
        let err = ConversionError::MissingField("checkpoint_object_id");
        assert!(!format!("{err}").is_empty());
    }

    #[test]
    fn unspecified_wire_execution_phase_is_rejected_and_classifies_permanent() {
        let result = ExecutionPhase::try_from(worker_proto::ExecutionPhase::Unspecified);
        assert_eq!(result, Err(ConversionError::UnspecifiedExecutionPhase));
        assert_eq!(result.unwrap_err().classify(), ErrorClass::Permanent);
    }

    #[test]
    fn negative_duration_is_rejected_and_classifies_permanent() {
        let wire = worker_proto::AllocationContract {
            max_execution_duration: Some(WireDuration {
                seconds: -1,
                nanos: 0,
            }),
        };
        let result = AllocationContract::try_from(wire);
        assert_eq!(result, Err(ConversionError::NegativeDuration));
        assert_eq!(result.unwrap_err().classify(), ErrorClass::Permanent);
    }

    #[test]
    fn execution_context_missing_worker_capability_is_rejected_and_classifies_permanent() {
        let wire = worker_proto::ExecutionContext {
            workload_id: Some(identity_proto::WorkloadId {
                value: WorkloadId::new().to_string(),
            }),
            allocation_id: Some(identity_proto::AllocationId {
                value: AllocationId::new().to_string(),
            }),
            allocation_contract: Some(worker_proto::AllocationContract {
                max_execution_duration: Some(WireDuration {
                    seconds: 30,
                    nanos: 0,
                }),
            }),
            dependencies: vec![],
            security_context: Some(worker_proto::SecurityContext {
                tenant_id: "tenant-1".to_string(),
                principal_id: "principal-1".to_string(),
                grant_scope: vec![],
            }),
            observability_context: Some(worker_proto::ObservabilityContext {
                trace_id: "trace-1".to_string(),
                span_id: "span-1".to_string(),
            }),
            execution_parameters: std::collections::HashMap::new(),
            worker_capability: None,
        };
        let result = ExecutionContext::try_from(wire);
        assert_eq!(
            result,
            Err(ConversionError::MissingField("worker_capability"))
        );
        assert_eq!(result.unwrap_err().classify(), ErrorClass::Permanent);
    }

    #[test]
    fn execution_context_empty_worker_capability_is_rejected_and_classifies_permanent() {
        let wire = worker_proto::ExecutionContext {
            workload_id: Some(identity_proto::WorkloadId {
                value: WorkloadId::new().to_string(),
            }),
            allocation_id: Some(identity_proto::AllocationId {
                value: AllocationId::new().to_string(),
            }),
            allocation_contract: Some(worker_proto::AllocationContract {
                max_execution_duration: Some(WireDuration {
                    seconds: 30,
                    nanos: 0,
                }),
            }),
            dependencies: vec![],
            security_context: Some(worker_proto::SecurityContext {
                tenant_id: "tenant-1".to_string(),
                principal_id: "principal-1".to_string(),
                grant_scope: vec![],
            }),
            observability_context: Some(worker_proto::ObservabilityContext {
                trace_id: "trace-1".to_string(),
                span_id: "span-1".to_string(),
            }),
            execution_parameters: std::collections::HashMap::new(),
            worker_capability: Some(worker_proto::WorkerCapability {
                value: String::new(),
            }),
        };
        let result = ExecutionContext::try_from(wire);
        assert_eq!(
            result,
            Err(ConversionError::MissingField("worker_capability"))
        );
        assert_eq!(result.unwrap_err().classify(), ErrorClass::Permanent);
    }

    #[test]
    fn execution_context_domain_to_wire_round_trips_every_field() {
        let workload_id = WorkloadId::new();
        let allocation_id = AllocationId::new();
        let allocation_contract = AllocationContract::new(core::time::Duration::from_secs(30));
        let object_id = ObjectId::new();
        let object_version = ObjectVersion::from_u64(3);
        let content_hash = ContentHash::new("sha256:af23");
        let dependency = ResolvedDependency::new(object_id, object_version, content_hash.clone());
        let mut execution_parameters = std::collections::BTreeMap::new();
        execution_parameters.insert("temperature".to_string(), "0.7".to_string());

        let original = ExecutionContext::new(
            workload_id,
            allocation_id,
            allocation_contract,
            vec![dependency],
            SecurityContext::new("tenant-1", "principal-1", vec!["scope-a".to_string()]),
            ObservabilityContext::new("trace-1", "span-1"),
            execution_parameters.clone(),
            WorkerCapability::new("chat.generate"),
        );

        let wire: worker_proto::ExecutionContext = original.clone().into();

        assert_eq!(
            wire.workload_id.as_ref().unwrap().value,
            workload_id.to_string()
        );
        assert_eq!(
            wire.allocation_id.as_ref().unwrap().value,
            allocation_id.to_string()
        );
        assert_eq!(
            wire.allocation_contract
                .as_ref()
                .unwrap()
                .max_execution_duration
                .as_ref()
                .unwrap()
                .seconds,
            30
        );
        assert_eq!(wire.dependencies.len(), 1);
        assert_eq!(
            wire.dependencies[0].object_id.as_ref().unwrap().value,
            object_id.to_string()
        );
        assert_eq!(
            wire.dependencies[0].content_hash.as_ref().unwrap().value,
            content_hash.digest().to_string()
        );
        let security = wire.security_context.as_ref().unwrap();
        assert_eq!(security.tenant_id, "tenant-1");
        assert_eq!(security.principal_id, "principal-1");
        assert_eq!(security.grant_scope, vec!["scope-a".to_string()]);
        let observability = wire.observability_context.as_ref().unwrap();
        assert_eq!(observability.trace_id, "trace-1");
        assert_eq!(observability.span_id, "span-1");
        assert_eq!(
            wire.execution_parameters.get("temperature"),
            Some(&"0.7".to_string())
        );
        assert_eq!(
            wire.worker_capability.as_ref().unwrap().value,
            "chat.generate"
        );

        let round_tripped = ExecutionContext::try_from(wire).unwrap();
        assert_eq!(round_tripped, original);
    }

    #[test]
    fn cancel_ack_wire_to_domain_always_succeeds() {
        let wire = worker_proto::CancelAck {};
        let domain: CancelAck = wire.into();
        assert_eq!(domain, CancelAck);
    }

    #[test]
    fn status_not_found_and_already_exists_map_to_existing_correlation_variants() {
        let workload_id = WorkloadId::new();

        let not_found = tonic::Status::not_found("no such workload");
        assert_eq!(
            WorkerError::from_status(not_found, workload_id),
            WorkerError::UnknownWorkload(workload_id)
        );

        let already_exists = tonic::Status::already_exists("already running");
        assert_eq!(
            WorkerError::from_status(already_exists, workload_id),
            WorkerError::DuplicateWorkload(workload_id)
        );
    }

    #[test]
    fn every_other_tonic_code_classifies_per_d5_table() {
        use tonic::Code;

        let workload_id = WorkloadId::new();
        let transient_codes = [
            Code::Unavailable,
            Code::DeadlineExceeded,
            Code::Aborted,
            Code::ResourceExhausted,
            Code::Unknown,
        ];
        let permanent_codes = [
            Code::InvalidArgument,
            Code::PermissionDenied,
            Code::Unauthenticated,
            Code::FailedPrecondition,
            Code::OutOfRange,
            Code::Unimplemented,
            Code::Internal,
            Code::DataLoss,
        ];

        for code in transient_codes {
            let status = tonic::Status::new(code, "transient condition");
            let error = WorkerError::from_status(status, workload_id);
            assert!(matches!(error, WorkerError::Transport { .. }));
            assert_eq!(error.classify(), ErrorClass::Transient);
        }

        for code in permanent_codes {
            let status = tonic::Status::new(code, "permanent condition");
            let error = WorkerError::from_status(status, workload_id);
            assert!(matches!(error, WorkerError::Transport { .. }));
            assert_eq!(error.classify(), ErrorClass::Permanent);
        }
    }

    #[test]
    fn transport_error_carries_the_status_message_and_no_transport_type() {
        let workload_id = WorkloadId::new();
        let status = tonic::Status::unavailable("connection refused");
        let error = WorkerError::from_status(status, workload_id);
        match error {
            WorkerError::Transport { message, kind } => {
                assert!(message.contains("connection refused"));
                assert_eq!(kind, ErrorClass::Transient);
            }
            _ => panic!("expected Transport variant"),
        }
    }

    #[test]
    fn missing_allocation_contract_is_rejected_and_classifies_permanent() {
        let wire = worker_proto::ExecutionContext {
            workload_id: Some(identity_proto::WorkloadId {
                value: WorkloadId::new().to_string(),
            }),
            allocation_id: Some(identity_proto::AllocationId {
                value: AllocationId::new().to_string(),
            }),
            allocation_contract: None,
            dependencies: vec![],
            security_context: Some(worker_proto::SecurityContext {
                tenant_id: "tenant-1".to_string(),
                principal_id: "principal-1".to_string(),
                grant_scope: vec![],
            }),
            observability_context: Some(worker_proto::ObservabilityContext {
                trace_id: "trace-1".to_string(),
                span_id: "span-1".to_string(),
            }),
            execution_parameters: std::collections::HashMap::new(),
            worker_capability: None,
        };
        let result = ExecutionContext::try_from(wire);
        assert_eq!(
            result,
            Err(ConversionError::MissingField("allocation_contract"))
        );
        assert_eq!(result.unwrap_err().classify(), ErrorClass::Permanent);
    }
}
