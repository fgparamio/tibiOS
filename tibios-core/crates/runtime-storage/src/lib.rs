//! The Runtime Storage Engine domain's stream-primitives data family:
//! `StreamId`, `Sequence`. No Ports yet — `append`/`replay` and any backend
//! are a future change (Slices 2-3).
//!
//! Implements `21-runtime-storage-engine.md`.
//!
//! **Log-is-authority** (`13-object-model.md:170`,
//! `21-runtime-storage-engine.md:49-51`, `23-object-store.md:180`): any
//! materialized "current state" MUST always be a rebuildable projection of
//! the append-only log; the log remains the only authoritative source.
//! This slice defines no "current state" type, so there is nothing that
//! could violate the invariant yet, and consequently no runtime-passing
//! test to write for it — the same treatment `runtime-object`'s `lib.rs`
//! gives its untestable "no `Default` impl" guarantee (see its
//! `#[cfg(test)] mod tests` comment). Verified by review instead: `StreamId`
//! and `Sequence` are this crate's only public types, and neither
//! represents materialized current state. This becomes runtime-testable
//! once append/replay ports and a backend exist (Slices 2-3).
//!
//! **Domain-agnosticism**: neither public type references `runtime-object`
//! or carries a payload field — `StreamId` wraps `String`, `Sequence` wraps
//! `u64`, both closed over `core`/`std`. Verified by review plus
//! `runtime/tests/architecture_guard.rs`'s dependency-set scan, which
//! asserts `Cargo.toml` declares exactly `runtime-primitives`.

/// Identifies exactly one per-aggregate consistency-domain stream
/// (`21-runtime-storage-engine.md:45`: independently-ordered streams, no
/// global log). An opaque name — `runtime-storage` learns nothing about
/// what the name means; each consumer derives its own stream identity.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct StreamId(String);

impl StreamId {
    /// Names a stream from any string-like value.
    #[must_use]
    pub fn new(name: impl Into<String>) -> Self {
        Self(name.into())
    }

    /// The stream's name.
    #[must_use]
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

/// A per-stream monotonic ordinal — the ordering primitive for
/// `21-runtime-storage-engine.md:69` ("ordering is guaranteed only within a
/// consistency domain"). An ordinal, not a counter: gaps are permitted at
/// the type level. No `next()`, no `initial()`, no `Default` — contiguity
/// and origin policy are deferred to a future append behavior (Slice 2/3),
/// not encoded here.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Sequence(u64);

impl Sequence {
    /// Infallible numeric constructor.
    #[must_use]
    pub const fn from_u64(value: u64) -> Self {
        Self(value)
    }

    /// Accessor returning the wrapped `u64`.
    #[must_use]
    pub const fn as_u64(&self) -> u64 {
        self.0
    }
}

#[cfg(test)]
mod tests {
    use super::{Sequence, StreamId};

    #[test]
    fn stream_id_round_trips_the_exact_name_supplied() {
        let id = StreamId::new("admission-log");
        assert_eq!(id.as_str(), "admission-log");
    }

    #[test]
    fn two_stream_ids_naming_the_same_stream_are_equal() {
        let a = StreamId::new("trust-log");
        let b = StreamId::new("trust-log");
        assert_eq!(a, b);
    }

    #[test]
    fn two_stream_ids_naming_different_streams_are_not_equal() {
        let a = StreamId::new("trust-log");
        let b = StreamId::new("admission-log");
        assert_ne!(a, b);
    }

    #[test]
    fn sequence_round_trips_the_exact_value_supplied() {
        let seq = Sequence::from_u64(42);
        assert_eq!(seq.as_u64(), 42);
    }

    #[test]
    fn a_later_sequence_compares_greater_than_an_earlier_one() {
        let earlier = Sequence::from_u64(1);
        let later = Sequence::from_u64(2);
        assert!(later > earlier);
    }
}
