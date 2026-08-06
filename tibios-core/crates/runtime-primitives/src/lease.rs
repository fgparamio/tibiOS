//! Lease primitive: a time-bounded authorization window shared by
//! Allocations (`15-allocation-model.md`) and Networking Sessions
//! (`22-networking.md`). Owns only its expiry; Pure Operations answer
//! whether it is still valid and how much of it remains.

use core::time::Duration;
use serde::{Deserialize, Serialize};

use crate::time::Timestamp;

/// A time-bounded authorization window.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct Lease {
    expires_at: Timestamp,
}

impl Lease {
    /// Creates a `Lease` that expires at the given `Timestamp`.
    #[must_use]
    pub const fn new(expires_at: Timestamp) -> Self {
        Self { expires_at }
    }

    /// The instant this `Lease` expires.
    #[must_use]
    pub const fn expires_at(&self) -> Timestamp {
        self.expires_at
    }

    /// Pure Operation: `true` once `now` reaches or passes expiry.
    #[must_use]
    pub fn is_expired(&self, now: Timestamp) -> bool {
        now >= self.expires_at
    }

    /// Pure Operation: time left until expiry, or `Duration::ZERO` once
    /// already expired.
    #[must_use]
    pub fn remaining(&self, now: Timestamp) -> Duration {
        self.expires_at.duration_since(now)
    }
}

#[cfg(test)]
mod tests {
    use super::Lease;
    use crate::time::Timestamp;
    use core::time::Duration;

    #[test]
    fn is_expired_true_once_now_reaches_expiry() {
        let lease = Lease::new(Timestamp::from_millis(1_000));
        assert!(lease.is_expired(Timestamp::from_millis(1_000)));
        assert!(lease.is_expired(Timestamp::from_millis(1_500)));
    }

    #[test]
    fn is_expired_false_before_expiry() {
        let lease = Lease::new(Timestamp::from_millis(1_000));
        assert!(!lease.is_expired(Timestamp::from_millis(999)));
    }

    #[test]
    fn remaining_returns_time_left_before_expiry() {
        let lease = Lease::new(Timestamp::from_millis(1_000));
        assert_eq!(
            lease.remaining(Timestamp::from_millis(400)),
            Duration::from_millis(600)
        );
    }

    #[test]
    fn remaining_is_zero_once_expired() {
        let lease = Lease::new(Timestamp::from_millis(1_000));
        assert_eq!(
            lease.remaining(Timestamp::from_millis(1_500)),
            Duration::ZERO
        );
    }
}
