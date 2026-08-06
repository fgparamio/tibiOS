//! Timestamp primitive: a point in time, expressed as milliseconds since the
//! Unix epoch. Documented exception to the "ULID-wrapped" default — a
//! `Timestamp` needs total ordering and arithmetic, which a ULID's embedded,
//! millisecond-resolution timestamp is not meant to expose directly.

use core::time::Duration;
use serde::{Deserialize, Serialize};
use std::time::SystemTime;

/// A point in time, expressed as milliseconds since the Unix epoch.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
pub struct Timestamp(u64);

impl Timestamp {
    /// Builds a `Timestamp` from an explicit millisecond value — for callers
    /// that already hold one (e.g. persisted state, tests).
    #[must_use]
    pub const fn from_millis(millis: u64) -> Self {
        Self(millis)
    }

    /// Primitive Generator: the current wall-clock time. Depends only on
    /// local system time, per `02-project-structure.md`'s Primitive
    /// Generators — never on networking, storage, or remote systems.
    #[must_use]
    pub fn now() -> Self {
        let millis = SystemTime::now()
            .duration_since(SystemTime::UNIX_EPOCH)
            .unwrap_or(Duration::ZERO)
            .as_millis() as u64;
        Self(millis)
    }

    /// Milliseconds since the Unix epoch.
    #[must_use]
    pub const fn as_millis(&self) -> u64 {
        self.0
    }

    /// Pure Operation: elapsed time from `earlier` to `self`, saturating at
    /// zero if `earlier` is not actually earlier than `self`.
    #[must_use]
    pub const fn duration_since(&self, earlier: Timestamp) -> Duration {
        Duration::from_millis(self.0.saturating_sub(earlier.0))
    }
}

#[cfg(test)]
mod tests {
    use super::Timestamp;

    #[test]
    fn from_millis_roundtrips_via_as_millis() {
        let ts = Timestamp::from_millis(42);
        assert_eq!(ts.as_millis(), 42);
    }
}
