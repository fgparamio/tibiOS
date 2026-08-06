//! `ErrorClass` primitive: behavior-based error classification shared across
//! every domain error type (`04-error-handling.md`). Orthogonal to *which*
//! domain failed — it answers *how the Runtime should react*. The
//! `Classify` mapping trait mentioned in `04-error-handling.md` is now
//! defined here — the explicit follow-up the prior "no public traits in
//! this change" deferral (`02-project-structure.md`, No Public Traits In
//! This Change) promised.
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

/// Maps a domain error to its `ErrorClass` (`04-error-handling.md:146`:
/// "`ErrorClass` and the `Classify` trait live in `runtime-primitives`").
/// Every domain error type across the Runtime (`WorkerError`,
/// `ConversionError`, and future domain errors) implements this trait
/// instead of defining its own private copy.
pub trait Classify {
    /// Returns how the Runtime should react to this error.
    fn classify(&self) -> ErrorClass;
}

#[cfg(test)]
mod tests {
    use super::{Classify, ErrorClass};

    #[test]
    fn variants_are_distinct() {
        assert_ne!(ErrorClass::Transient, ErrorClass::Permanent);
        assert_ne!(ErrorClass::Permanent, ErrorClass::Fatal);
    }

    /// Minimal local type implementing `Classify`, exercised for every
    /// `ErrorClass` variant, proving the trait's single-method shape is
    /// usable exactly as documented.
    struct FakeError(ErrorClass);

    impl Classify for FakeError {
        fn classify(&self) -> ErrorClass {
            self.0
        }
    }

    #[test]
    fn classify_trait_is_usable_for_every_error_class_variant() {
        assert_eq!(
            FakeError(ErrorClass::Transient).classify(),
            ErrorClass::Transient
        );
        assert_eq!(
            FakeError(ErrorClass::Permanent).classify(),
            ErrorClass::Permanent
        );
        assert_eq!(FakeError(ErrorClass::Fatal).classify(), ErrorClass::Fatal);
    }
}
