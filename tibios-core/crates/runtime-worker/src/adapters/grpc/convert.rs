//! Fallible wire <-> domain conversion for the Worker gRPC contract.
//!
//! Implements `worker-wire-adapter/spec.md`: the boundary between the
//! generated `tonic`/`prost` wire types (`super::tibios::{primitives,
//! worker}::v1`) and their `runtime-primitives` domain counterparts. Scoped
//! exactly to the five identity-wrapper messages (`ObjectId`,
//! `ObjectVersion`, `ContentHash`, `WorkloadId`, `AllocationId`) and the
//! two oneofs (`ExecutionEvent`'s six arms, `ExecutionResponse`'s two
//! arms). Worker domain types (`ExecutionContext`, `ExecutionReport`, and
//! the rest of `18-worker-model.md`'s domain model) are out of scope — they
//! do not exist yet and are not converted here.
//!
//! `dead_code` is allowed at module scope: this boundary is consumed by a
//! future phase that wires the actual `WorkerExecution` RPCs (out of scope
//! here — see the module doc comment above); today it is exercised only by
//! this module's own unit tests, which does not count as "used" for a
//! plain (non-test) library build.
#![allow(dead_code)]

use super::tibios::{primitives::v1 as identity_proto, worker::v1 as worker_proto};

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
        }
    }
}

/// Local counterpart to `04-error-handling.md`'s `Classify` mapping trait.
/// `runtime-primitives` has deliberately not added the public trait yet
/// (`crates/runtime-primitives/src/error.rs`'s doc comment — "no public
/// traits in this change"), so this boundary defines its own private copy,
/// scoped to `ConversionError`, matching the documented shape exactly.
trait Classify {
    fn classify(&self) -> runtime_primitives::ErrorClass;
}

impl Classify for ConversionError {
    fn classify(&self) -> runtime_primitives::ErrorClass {
        match self {
            Self::InvalidUlid(..)
            | Self::InvalidObjectVersion(_)
            | Self::MissingField(_)
            | Self::UnsetExecutionEventOneof
            | Self::UnsetExecutionResponseOneof => runtime_primitives::ErrorClass::Permanent,
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
        Self::parse(&value.value).map_err(|source| ConversionError::InvalidUlid("WorkloadId", source))
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

/// Domain-shape counterpart to the wire `CheckpointCreated` arm.
/// `checkpoint_object_id` has no meaningful empty/absent domain variant, so
/// it is resolved to a non-optional `runtime_primitives::ObjectId` here
/// rather than carried as the wire `Option`.
#[derive(Debug, Clone, PartialEq, Eq)]
struct CheckpointCreated {
    checkpoint_object_id: runtime_primitives::ObjectId,
}

impl TryFrom<worker_proto::CheckpointCreated> for CheckpointCreated {
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

/// Non-optional counterpart to `worker_proto::execution_event::Arm`
/// (carried as `Option` at the wire level because `oneof` is always
/// optional in proto3). Carries each arm's payload verbatim except
/// `CheckpointCreated`, whose required identity field is resolved eagerly
/// (see `CheckpointCreated` above).
#[derive(Debug, Clone, PartialEq)]
enum ExecutionEventArm {
    OutputChunk(worker_proto::OutputChunk),
    Progress(worker_proto::Progress),
    Warning(worker_proto::Warning),
    CheckpointCreated(CheckpointCreated),
    MetricsSnapshot(worker_proto::MetricsSnapshot),
    EndOfStream(worker_proto::EndOfStream),
}

impl TryFrom<worker_proto::ExecutionEvent> for ExecutionEventArm {
    type Error = ConversionError;

    fn try_from(value: worker_proto::ExecutionEvent) -> Result<Self, Self::Error> {
        use worker_proto::execution_event::Arm;

        match value.arm {
            Some(Arm::OutputChunk(v)) => Ok(Self::OutputChunk(v)),
            Some(Arm::Progress(v)) => Ok(Self::Progress(v)),
            Some(Arm::Warning(v)) => Ok(Self::Warning(v)),
            Some(Arm::CheckpointCreated(v)) => Ok(Self::CheckpointCreated(v.try_into()?)),
            Some(Arm::MetricsSnapshot(v)) => Ok(Self::MetricsSnapshot(v)),
            Some(Arm::EndOfStream(v)) => Ok(Self::EndOfStream(v)),
            None => Err(ConversionError::UnsetExecutionEventOneof),
        }
    }
}

/// Non-optional counterpart to `worker_proto::execution_response::Payload`.
#[derive(Debug, Clone, PartialEq)]
enum ExecutionResponseArm {
    Event(ExecutionEventArm),
    Report(worker_proto::ExecutionReport),
}

impl TryFrom<worker_proto::ExecutionResponse> for ExecutionResponseArm {
    type Error = ConversionError;

    fn try_from(value: worker_proto::ExecutionResponse) -> Result<Self, Self::Error> {
        use worker_proto::execution_response::Payload;

        match value.payload {
            Some(Payload::Event(v)) => Ok(Self::Event(v.try_into()?)),
            Some(Payload::Report(v)) => Ok(Self::Report(v)),
            None => Err(ConversionError::UnsetExecutionResponseOneof),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{
        identity_proto, worker_proto, CheckpointCreated, Classify, ConversionError,
        ExecutionEventArm, ExecutionResponseArm,
    };
    use runtime_primitives::{AllocationId, ContentHash, ErrorClass, ObjectId, ObjectVersion, WorkloadId};

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
        assert!(matches!(result, Err(ConversionError::InvalidUlid("WorkloadId", _))));
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
        assert!(matches!(result, Err(ConversionError::InvalidObjectVersion(_))));
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
        let result = ExecutionEventArm::try_from(wire).unwrap();
        assert!(matches!(result, ExecutionEventArm::OutputChunk(_)));
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
        let result = ExecutionEventArm::try_from(wire).unwrap();
        assert!(matches!(result, ExecutionEventArm::Progress(_)));
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
        let result = ExecutionEventArm::try_from(wire).unwrap();
        assert!(matches!(result, ExecutionEventArm::Warning(_)));
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
        let result = ExecutionEventArm::try_from(wire).unwrap();
        match result {
            ExecutionEventArm::CheckpointCreated(checkpoint) => {
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
        let result = ExecutionEventArm::try_from(wire);
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
        let result = ExecutionEventArm::try_from(wire).unwrap();
        assert!(matches!(result, ExecutionEventArm::MetricsSnapshot(_)));
    }

    #[test]
    fn execution_event_end_of_stream_arm_converts() {
        let wire = worker_proto::ExecutionEvent {
            arm: Some(worker_proto::execution_event::Arm::EndOfStream(
                worker_proto::EndOfStream {},
            )),
        };
        let result = ExecutionEventArm::try_from(wire).unwrap();
        assert!(matches!(result, ExecutionEventArm::EndOfStream(_)));
    }

    #[test]
    fn execution_event_rejects_unset_oneof() {
        let wire = worker_proto::ExecutionEvent { arm: None };
        let result = ExecutionEventArm::try_from(wire);
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
        let result = ExecutionResponseArm::try_from(wire).unwrap();
        assert!(matches!(result, ExecutionResponseArm::Event(_)));
    }

    #[test]
    fn execution_response_report_arm_converts() {
        let wire = worker_proto::ExecutionResponse {
            payload: Some(worker_proto::execution_response::Payload::Report(
                worker_proto::ExecutionReport {
                    final_phase: worker_proto::ExecutionPhase::Completed as i32,
                    duration: None,
                    trace_id: "trace-1".to_string(),
                    summary: "done".to_string(),
                },
            )),
        };
        let result = ExecutionResponseArm::try_from(wire).unwrap();
        assert!(matches!(result, ExecutionResponseArm::Report(_)));
    }

    #[test]
    fn execution_response_rejects_unset_oneof() {
        let wire = worker_proto::ExecutionResponse { payload: None };
        let result = ExecutionResponseArm::try_from(wire);
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
}
