//! The Worker domain's public language and its Inbound Port
//! (`18-worker-model.md`): `ExecutionContext` and the values it carries.
//! Generated transport code stays confined to a private module tree; the
//! public surface below names no transport type and no async-runtime type.

#![deny(private_interfaces, private_bounds)]

mod adapters;
pub mod execution;

pub use execution::context::{
    ExecutionContext, ObservabilityContext, ResolvedDependency, SecurityContext,
};
