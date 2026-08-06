//! Identity primitives: ULID-backed identifiers used across every domain,
//! plus `ObjectVersion` — a Logical Object's identity is `ObjectId` (ULID) +
//! `ObjectVersion` (`13-object-model.md`).

use serde::{Deserialize, Serialize};
use ulid::Ulid;

/// Generates a ULID-backed identity newtype implementing the identity
/// primitive contract: `Debug`, `Clone`, `Copy`, `PartialEq`, `Eq`, `Hash`,
/// `Serialize`, `Deserialize`, a `new()` Primitive Generator, `Default`
/// (delegating to `new()`), and `Display`.
///
/// This macro exists only to avoid repeating identical boilerplate seven
/// times; it introduces no behavior beyond what each type would hand-write
/// individually, and it declares no new public trait.
macro_rules! ulid_newtype {
    ($(#[$meta:meta])* $name:ident) => {
        $(#[$meta])*
        #[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
        pub struct $name(Ulid);

        impl $name {
            /// Primitive Generator: produces a new, globally unique
            /// identifier. Depends only on local system time and local
            /// cryptographic randomness, per `02-project-structure.md`'s
            /// Primitive Generators.
            #[must_use]
            pub fn new() -> Self {
                Self(Ulid::new())
            }
        }

        impl Default for $name {
            fn default() -> Self {
                Self::new()
            }
        }

        impl core::fmt::Display for $name {
            fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
                core::fmt::Display::fmt(&self.0, f)
            }
        }
    };
}

ulid_newtype! {
    /// Identifies a Logical Object independently of its `ObjectVersion`
    /// (`13-object-model.md`).
    ObjectId
}
ulid_newtype! {
    /// Answers which machine participates in the Runtime
    /// (`02-project-structure.md`).
    NodeId
}
ulid_newtype! {
    /// Identifies a Runtime instance independently of the Nodes currently
    /// composing it — the Identity component of a Deployment Unit
    /// (`29-deployment.md`).
    RuntimeId
}
ulid_newtype! {
    /// Identifies a Workload independently of its Allocations
    /// (`15-allocation-model.md`).
    WorkloadId
}
ulid_newtype! {
    /// Identifies an Allocation of Resource capacity to a Workload
    /// (`15-allocation-model.md`).
    AllocationId
}
ulid_newtype! {
    /// Identifies a Networking Session (`22-networking.md`).
    SessionId
}
ulid_newtype! {
    /// Identifies a tenant within the Runtime.
    TenantId
}

/// Monotonic version counter attached to a Logical Object's `ObjectId`
/// (`13-object-model.md`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
pub struct ObjectVersion(u64);

impl ObjectVersion {
    /// The first version of a newly created Logical Object.
    #[must_use]
    pub const fn initial() -> Self {
        Self(0)
    }

    /// Pure Operation: the next version in sequence — deterministic, no
    /// side effects, no I/O.
    #[must_use]
    pub const fn next(&self) -> Self {
        Self(self.0 + 1)
    }
}

impl Default for ObjectVersion {
    fn default() -> Self {
        Self::initial()
    }
}

#[cfg(test)]
mod tests {
    use super::{ObjectId, ObjectVersion};

    #[test]
    fn new_generates_distinct_ids() {
        let a = ObjectId::new();
        let b = ObjectId::new();
        assert_ne!(a, b);
    }

    #[test]
    fn display_renders_full_length_ulid_text() {
        let id = ObjectId::new();
        assert_eq!(format!("{id}").len(), 26);
    }

    #[test]
    fn next_increments_version() {
        let v0 = ObjectVersion::initial();
        let v1 = v0.next();
        assert_ne!(v0, v1);
        assert_eq!(v1.next(), v0.next().next());
    }
}
