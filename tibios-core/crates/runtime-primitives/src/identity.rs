//! Identity primitives: ULID-backed identifiers used across every domain,
//! plus `ObjectVersion` — a Logical Object's identity is `ObjectId` (ULID) +
//! `ObjectVersion` (`13-object-model.md`).

use serde::{Deserialize, Serialize};
use ulid::Ulid;

/// Error returned when text fails to parse as a valid ULID for one of the
/// ULID-backed identity newtypes (`ObjectId`, `NodeId`, `RuntimeId`,
/// `WorkloadId`, `AllocationId`, `SessionId`, `TenantId`). Deliberately not
/// `FromStr`-based: a dedicated fallible constructor (`parse`) keeps this
/// error type visible at the call site instead of being inferred implicitly.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct IdentityParseError {
    text: String,
}

impl IdentityParseError {
    fn new(text: &str) -> Self {
        Self {
            text: text.to_string(),
        }
    }
}

impl core::fmt::Display for IdentityParseError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        write!(f, "invalid ULID text: {:?}", self.text)
    }
}

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

            /// Fallible text constructor: parses this identity's wrapped
            /// `Ulid` from a 26-character ULID string, so a wire-format
            /// converter can build the type from an incoming string without
            /// reaching into its private field. Rejects text that is not a
            /// valid ULID; never panics, never substitutes `Self::default()`.
            pub fn parse(text: &str) -> Result<Self, IdentityParseError> {
                Ulid::from_string(text)
                    .map(Self)
                    .map_err(|_| IdentityParseError::new(text))
            }

            /// Accessor returning the wrapped `Ulid`, whose `Display` text
            /// is identical to this newtype's own `Display` text — the
            /// counterpart to `parse` for a wire-format converter that
            /// serializes back out to text.
            #[must_use]
            pub fn as_ulid(&self) -> Ulid {
                self.0
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

    /// Infallible numeric constructor. The fallible, text-based entry point
    /// required by the wire format is composed at the call site as
    /// `text.parse::<u64>().map(ObjectVersion::from_u64)` — `ObjectVersion`
    /// itself owns only the numeric half of that composition.
    #[must_use]
    pub const fn from_u64(value: u64) -> Self {
        Self(value)
    }

    /// Accessor returning the wrapped `u64`, the counterpart to
    /// `from_u64` for a wire-format converter that serializes back out to
    /// the proto `string` representation.
    #[must_use]
    pub const fn as_u64(&self) -> u64 {
        self.0
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
    fn parse_round_trips_valid_ulid_text() {
        let original = ObjectId::new();
        let text = format!("{original}");
        let parsed = ObjectId::parse(&text).unwrap();
        assert_eq!(parsed, original);
        assert_eq!(format!("{}", parsed.as_ulid()), text);
    }

    #[test]
    fn parse_rejects_invalid_ulid_text() {
        let result = ObjectId::parse("not-a-valid-ulid");
        assert!(result.is_err());
    }

    #[test]
    fn parse_rejects_empty_text() {
        let result = ObjectId::parse("");
        assert!(result.is_err());
    }

    #[test]
    fn identity_parse_error_display_is_not_empty() {
        let err = ObjectId::parse("").unwrap_err();
        assert!(!format!("{err}").is_empty());
    }

    #[test]
    fn object_version_round_trips_valid_numeric_text() {
        let text = "42";
        let parsed = text.parse::<u64>().map(ObjectVersion::from_u64).unwrap();
        assert_eq!(parsed.as_u64(), 42);
    }

    #[test]
    fn object_version_rejects_non_numeric_text() {
        let result = "not-a-number".parse::<u64>().map(ObjectVersion::from_u64);
        assert!(result.is_err());
    }

    #[test]
    fn object_version_rejects_empty_text() {
        let result = "".parse::<u64>().map(ObjectVersion::from_u64);
        assert!(result.is_err());
    }

    #[test]
    fn object_version_rejects_negative_text() {
        let result = "-1".parse::<u64>().map(ObjectVersion::from_u64);
        assert!(result.is_err());
    }

    #[test]
    fn object_version_rejects_overflowing_text() {
        let result = "99999999999999999999"
            .parse::<u64>()
            .map(ObjectVersion::from_u64);
        assert!(result.is_err());
    }

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

    #[test]
    fn next_is_strictly_greater_than_default() {
        let v = ObjectVersion::default();
        assert!(v.next() > v);
    }
}
