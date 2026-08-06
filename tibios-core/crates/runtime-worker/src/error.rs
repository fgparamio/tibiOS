//! `WorkerError`: every failure a `WorkerService` implementation can
//! return. The Worker classifies the *nature* of the failure; the Runtime
//! decides what to do about it — `Classify` becoming public
//! (`runtime-primitives/spec.md`) does not mean the Worker prescribes
//! recovery policy (design.md D11 Rationale).

use runtime_primitives::{Classify, ErrorClass, WorkloadId};

use crate::ports::execution_channel::ChannelClosed;

/// Every failure a `WorkerService` implementation can return.
///
/// The Worker classifies the nature of the failure; the Runtime decides
/// what to do about it. This enum defines the two correlation failures a
/// `WorkloadId`-keyed registry can produce (design.md D11), plus the one
/// conversion a Worker can reach for after a failed `ExecutionChannel::emit`
/// (`ports/execution_channel.rs`); it grows as further obligations are added
/// to the port.
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
    /// A Worker chose to abort an execution after `ExecutionChannel::emit`
    /// returned `Err(ChannelClosed)` — the Runtime's `Receiver` is gone.
    /// This variant exists so an `execute` body can use
    /// `channel.emit(event).await?` and return early; a closed channel
    /// never *forces* an early return (`ports/execution_channel.rs`'s own
    /// doc comment, design.md D9 Consequences) — it only makes one
    /// available.
    ChannelClosed(ChannelClosed),
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
            Self::ChannelClosed(cause) => write!(f, "{cause}"),
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
            // The Runtime dropping its `Receiver` is an environmental
            // condition, not an invalid request or a broken invariant — a
            // retried `execute` call gets a fresh `ExecutionChannel` from
            // the Runtime, so retrying can resolve it.
            Self::ChannelClosed(_) => ErrorClass::Transient,
        }
    }
}

impl From<ChannelClosed> for WorkerError {
    fn from(cause: ChannelClosed) -> Self {
        Self::ChannelClosed(cause)
    }
}

#[cfg(test)]
mod tests {
    use runtime_primitives::{Classify, ErrorClass, WorkloadId};

    use super::WorkerError;
    use crate::ports::execution_channel::ChannelClosed;

    #[test]
    fn correlation_failures_classify_permanent() {
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
    fn channel_closed_classifies_transient() {
        let error = WorkerError::from(ChannelClosed);
        assert_eq!(error.classify(), ErrorClass::Transient);
    }

    #[test]
    fn worker_error_display_names_the_workload() {
        let workload_id = WorkloadId::new();
        let unknown = format!("{}", WorkerError::UnknownWorkload(workload_id));
        assert!(unknown.contains(&workload_id.to_string()));

        let duplicate = format!("{}", WorkerError::DuplicateWorkload(workload_id));
        assert!(duplicate.contains(&workload_id.to_string()));
    }

    #[test]
    fn worker_error_display_carries_the_channel_closed_cause() {
        let error = WorkerError::from(ChannelClosed);
        let cause = ChannelClosed;
        assert_eq!(format!("{error}"), format!("{cause}"));
    }

    #[test]
    fn from_channel_closed_wraps_it_in_the_channel_closed_variant() {
        let error: WorkerError = ChannelClosed.into();
        assert_eq!(error, WorkerError::ChannelClosed(ChannelClosed));
    }
}
