//! `WorkerError`: every failure a `WorkerService` implementation can
//! return. The Worker classifies the *nature* of the failure; the Runtime
//! decides what to do about it — `Classify` becoming public
//! (`runtime-primitives/spec.md`) does not mean the Worker prescribes
//! recovery policy (design.md D11 Rationale).

use runtime_primitives::{Classify, ErrorClass, WorkloadId};

/// Every failure a `WorkerService` implementation can return.
///
/// The Worker classifies the nature of the failure; the Runtime decides
/// what to do about it. This enum currently defines the two correlation
/// failures a `WorkloadId`-keyed registry can produce (design.md D11); it
/// grows as further obligations are added to the port.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WorkerError {
    /// `cancel`/`pulse` was called for a `WorkloadId` this Worker has no
    /// in-flight registration for. Returned whether the id never existed
    /// or its execution already completed and deregistered — a Worker
    /// cannot distinguish the two (design.md D11 Rationale), and this
    /// variant enforces obligation O3: unregistered id at `cancel`/`pulse`
    /// MUST return `UnknownWorkload`.
    UnknownWorkload(WorkloadId),
    /// `execute` was called for a `WorkloadId` that already has an
    /// in-flight registration. Enforces obligation O4: an already-registered
    /// id at a new `execute` call MUST return `DuplicateWorkload`, without
    /// starting a second execution (`18-worker-model.md:106` — Execution
    /// Contexts never share mutable state).
    DuplicateWorkload(WorkloadId),
}

impl core::fmt::Display for WorkerError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::UnknownWorkload(workload_id) => {
                write!(f, "no in-flight execution registered for {workload_id}")
            }
            Self::DuplicateWorkload(workload_id) => {
                write!(f, "an execution is already registered for {workload_id}")
            }
        }
    }
}

impl Classify for WorkerError {
    fn classify(&self) -> ErrorClass {
        match self {
            // A Worker cannot distinguish "never existed" from "already
            // completed"; `Transient` would invite an infinite retry loop
            // against a workload that finished successfully (design.md
            // D11 Rationale).
            Self::UnknownWorkload(_) | Self::DuplicateWorkload(_) => ErrorClass::Permanent,
        }
    }
}

#[cfg(test)]
mod tests {
    use runtime_primitives::{Classify, ErrorClass, WorkloadId};

    use super::WorkerError;

    #[test]
    fn every_worker_error_variant_classifies_permanent() {
        let workload_id = WorkloadId::new();
        let variants = [
            WorkerError::UnknownWorkload(workload_id),
            WorkerError::DuplicateWorkload(workload_id),
        ];
        for variant in variants {
            assert_eq!(variant.classify(), ErrorClass::Permanent);
        }
    }

    #[test]
    fn worker_error_display_names_the_workload() {
        let workload_id = WorkloadId::new();
        let unknown = format!("{}", WorkerError::UnknownWorkload(workload_id));
        assert!(unknown.contains(&workload_id.to_string()));

        let duplicate = format!("{}", WorkerError::DuplicateWorkload(workload_id));
        assert!(duplicate.contains(&workload_id.to_string()));
    }
}
