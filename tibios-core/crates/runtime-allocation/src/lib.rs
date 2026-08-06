//! Stub for the Allocation domain.
//!
//! Implements `15-allocation-model.md`.

use core::time::Duration;

/// The resource envelope the Allocation domain has already granted for an
/// Execution.
///
/// Owned here per `02-project-structure.md`'s Ownership Boundaries table
/// (`Allocation -> AllocationContract -> Worker`): the producer owns the
/// data contract, consumers never redefine it. Its field set matches
/// exactly what the frozen wire contract already carries
/// (`worker.proto`'s `AllocationContract` message): `max_execution_duration`.
///
/// This struct is **intentionally partial**, pending `15-allocation-model.md`'s
/// own future change to add the remaining documented facets: exclusive/shared,
/// renewable lease, preemptible, migration allowed, and checkpoint required.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct AllocationContract {
    max_execution_duration: Duration,
}

impl AllocationContract {
    /// Builds an `AllocationContract` from its single frozen field.
    #[must_use]
    pub const fn new(max_execution_duration: Duration) -> Self {
        Self {
            max_execution_duration,
        }
    }

    /// The maximum execution duration granted by this contract.
    #[must_use]
    pub const fn max_execution_duration(&self) -> Duration {
        self.max_execution_duration
    }
}

#[cfg(test)]
mod tests {
    use super::AllocationContract;
    use core::time::Duration;

    #[test]
    fn constructor_and_accessor_round_trip() {
        let contract = AllocationContract::new(Duration::from_secs(30));
        assert_eq!(contract.max_execution_duration(), Duration::from_secs(30));
    }

    #[test]
    fn equal_durations_are_equal() {
        let a = AllocationContract::new(Duration::from_secs(30));
        let b = AllocationContract::new(Duration::from_secs(30));
        assert_eq!(a, b);
    }

    #[test]
    fn differing_durations_are_not_equal() {
        let a = AllocationContract::new(Duration::from_secs(30));
        let b = AllocationContract::new(Duration::from_secs(60));
        assert_ne!(a, b);
    }

    #[test]
    fn clone_and_copy_preserve_value() {
        let a = AllocationContract::new(Duration::from_secs(45));
        let via_copy = a;
        #[allow(clippy::clone_on_copy)]
        let via_clone = a.clone();
        assert_eq!(a, via_copy);
        assert_eq!(a, via_clone);
    }
}
