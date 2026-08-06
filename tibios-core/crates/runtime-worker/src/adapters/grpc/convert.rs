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

        Ok(Self::new(
            workload_id,
            allocation_id,
            allocation_contract,
            dependencies,
            security_context,
            observability_context,
            execution_parameters,
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
/// `dead_code` is narrowly allowed on this one item (not at module scope —
/// `tasks.md` 5a.16): a future phase wires the actual `WorkerExecution`
/// RPCs and consumes this type (out of scope for this slice); today it is
/// exercised only by this module's own unit tests, which does not count as
/// "used" for a plain (non-test) library build. Every other conversion in
/// this file is exercised outside `#[cfg(test)]` too (as trait impls
/// callable by any future consumer), so no other item needs this allow.
#[allow(dead_code)]
#[derive(Debug, Clone, PartialEq)]
enum ResponseFrame {
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

#[cfg(test)]
mod tests {
    use super::{ConversionError, ResponseFrame, WireDuration, identity_proto, worker_proto};
    use crate::execution::context::ExecutionContext;
    use crate::execution::event::{CheckpointCreated, ExecutionEvent};
    use crate::execution::report::ExecutionPhase;
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
