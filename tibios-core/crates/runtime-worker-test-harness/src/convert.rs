//! Inbound wire -> domain conversions this harness needs to decode a
//! `SubmitJob`/`Cancel`/`Pulse` request into `runtime_worker`'s public
//! domain types. Deliberately duplicated from `runtime-worker`'s own
//! `adapters/grpc/convert.rs` rather than shared: this crate compiles its
//! own copy of the wire types (`build.rs`), so the two `convert` modules
//! can never be the same code even if extracted into a common crate — one
//! side would still depend on the other's generated types. Only the
//! inbound direction is needed; this harness's outbound `ExecutionResponse`
//! frames are hand-built directly from primitives (see `lib.rs`).

use super::tibios::{primitives::v1 as identity_proto, worker::v1 as worker_proto};

type WireDuration = super::google::protobuf::Duration;

#[derive(Debug)]
pub enum ConversionError {
    InvalidUlid(&'static str),
    InvalidObjectVersion,
    MissingField(&'static str),
    NegativeDuration,
}

impl From<ConversionError> for tonic::Status {
    fn from(error: ConversionError) -> Self {
        let message = match error {
            ConversionError::InvalidUlid(name) => format!("invalid {name} on the wire"),
            ConversionError::InvalidObjectVersion => {
                "invalid ObjectVersion text on the wire".to_string()
            }
            ConversionError::MissingField(field) => {
                format!("required field {field:?} was unset on the wire")
            }
            ConversionError::NegativeDuration => {
                "wire Duration had a negative seconds or nanos field".to_string()
            }
        };
        tonic::Status::invalid_argument(message)
    }
}

impl TryFrom<identity_proto::ObjectId> for runtime_primitives::ObjectId {
    type Error = ConversionError;

    fn try_from(value: identity_proto::ObjectId) -> Result<Self, Self::Error> {
        Self::parse(&value.value).map_err(|_| ConversionError::InvalidUlid("ObjectId"))
    }
}

impl TryFrom<identity_proto::ObjectVersion> for runtime_primitives::ObjectVersion {
    type Error = ConversionError;

    fn try_from(value: identity_proto::ObjectVersion) -> Result<Self, Self::Error> {
        value
            .value
            .parse::<u64>()
            .map(Self::from_u64)
            .map_err(|_| ConversionError::InvalidObjectVersion)
    }
}

impl TryFrom<identity_proto::ContentHash> for runtime_primitives::ContentHash {
    type Error = ConversionError;

    fn try_from(value: identity_proto::ContentHash) -> Result<Self, Self::Error> {
        Ok(Self::new(value.value))
    }
}

impl TryFrom<identity_proto::WorkloadId> for runtime_primitives::WorkloadId {
    type Error = ConversionError;

    fn try_from(value: identity_proto::WorkloadId) -> Result<Self, Self::Error> {
        Self::parse(&value.value).map_err(|_| ConversionError::InvalidUlid("WorkloadId"))
    }
}

impl TryFrom<identity_proto::AllocationId> for runtime_primitives::AllocationId {
    type Error = ConversionError;

    fn try_from(value: identity_proto::AllocationId) -> Result<Self, Self::Error> {
        Self::parse(&value.value).map_err(|_| ConversionError::InvalidUlid("AllocationId"))
    }
}

fn duration_from_proto(value: WireDuration) -> Result<core::time::Duration, ConversionError> {
    if value.seconds < 0 || value.nanos < 0 {
        return Err(ConversionError::NegativeDuration);
    }
    Ok(core::time::Duration::new(
        value.seconds as u64,
        value.nanos as u32,
    ))
}

impl TryFrom<worker_proto::AllocationContract> for runtime_allocation::AllocationContract {
    type Error = ConversionError;

    fn try_from(value: worker_proto::AllocationContract) -> Result<Self, Self::Error> {
        let max_execution_duration = value
            .max_execution_duration
            .ok_or(ConversionError::MissingField("max_execution_duration"))?;
        Ok(Self::new(duration_from_proto(max_execution_duration)?))
    }
}

impl TryFrom<worker_proto::ResolvedModelRef> for runtime_worker::ResolvedDependency {
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

impl TryFrom<worker_proto::WorkerCapability> for runtime_worker::WorkerCapability {
    type Error = ConversionError;

    fn try_from(value: worker_proto::WorkerCapability) -> Result<Self, Self::Error> {
        if value.value.is_empty() {
            return Err(ConversionError::MissingField("worker_capability"));
        }
        Ok(Self::new(value.value))
    }
}

impl From<worker_proto::SecurityContext> for runtime_worker::SecurityContext {
    fn from(value: worker_proto::SecurityContext) -> Self {
        Self::new(value.tenant_id, value.principal_id, value.grant_scope)
    }
}

impl From<worker_proto::ObservabilityContext> for runtime_worker::ObservabilityContext {
    fn from(value: worker_proto::ObservabilityContext) -> Self {
        Self::new(value.trace_id, value.span_id)
    }
}

impl TryFrom<worker_proto::ExecutionContext> for runtime_worker::ExecutionContext {
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

pub fn parse_workload_id(
    wire: Option<identity_proto::WorkloadId>,
) -> Result<runtime_primitives::WorkloadId, tonic::Status> {
    let wire = wire.ok_or(ConversionError::MissingField("workload_id"))?;
    Ok(runtime_primitives::WorkloadId::try_from(wire)?)
}
