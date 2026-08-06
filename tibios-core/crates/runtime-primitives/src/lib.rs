//! `runtime-primitives` — the fundamental identity and value types shared
//! across every Runtime domain, per `02-project-structure.md`'s "Shared
//! Primitives" section.
//!
//! Adding a primitive type is an architectural change, not an implementation
//! detail: precedent is that adding `RuntimeId` required reopening
//! `02-project-structure.md`. Any future addition to this set MUST follow the
//! same path.

mod content;
mod error;
mod identity;
mod lease;
mod time;

pub use content::ContentHash;
pub use error::ErrorClass;
pub use identity::{
    AllocationId, NodeId, ObjectId, ObjectVersion, RuntimeId, SessionId, TenantId, WorkloadId,
};
pub use lease::Lease;
pub use time::Timestamp;
