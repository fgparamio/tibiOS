//! The Worker domain's public language and its Inbound Port
//! (`18-worker-model.md`): `ExecutionContext` and the values it carries.
//! Generated transport code stays confined to a private module tree; the
//! public surface below names no transport type and no async-runtime type.

#![deny(private_interfaces, private_bounds)]

mod adapters;
mod error;
pub mod execution;

pub use error::WorkerError;
pub use execution::context::{
    ExecutionContext, ObservabilityContext, ResolvedDependency, SecurityContext,
};
pub use execution::event::{
    CheckpointCreated, EndOfStream, ExecutionEvent, MetricsSnapshot, OutputChunk, Progress, Warning,
};
pub use execution::report::{CancelAck, ExecutionPhase, ExecutionPulse, ExecutionReport};
