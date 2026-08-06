//! `ErrorClass` primitive: behavior-based error classification shared across
//! every domain error type (`04-error-handling.md`). Orthogonal to *which*
//! domain failed — it answers *how the Runtime should react*. The
//! `Classify` mapping trait mentioned in `04-error-handling.md` is deferred:
//! `runtime-primitives` defines no public traits in this change
//! (`02-project-structure.md`, No Public Traits In This Change).
use serde::{Deserialize, Serialize};

/// How the Runtime should react to a failure, independent of which domain
/// raised it.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ErrorClass {
    /// Retry — the failure is expected to resolve itself (timeout, network
    /// partition, leader election).
    Transient,
    /// Return the error to the caller — retrying will not help (invalid
    /// input, permission denied, unsupported version).
    Permanent,
    /// Isolate the node, alert, or begin recovery — the failure indicates a
    /// broken invariant or data loss.
    Fatal,
}

#[cfg(test)]
mod tests {
    use super::ErrorClass;

    #[test]
    fn variants_are_distinct() {
        assert_ne!(ErrorClass::Transient, ErrorClass::Permanent);
        assert_ne!(ErrorClass::Permanent, ErrorClass::Fatal);
    }
}
