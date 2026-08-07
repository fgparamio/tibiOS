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
#[derive(Debug, Clone, PartialEq, Eq)]
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
    /// A gRPC transport-level failure (connection refused, deadline
    /// exceeded, a rejected request, ...) normalized away from `tonic`'s own
    /// type (`worker-inbound-port/spec.md` — "WorkerError Normalizes
    /// Transport Failures Without Naming A Transport Type"). `kind` is the
    /// classification this specific condition maps to per D5's table, not a
    /// blanket constant — see `from_status`.
    Transport {
        /// The classification this specific transport condition maps to,
        /// resolved once at construction time by `from_status`.
        kind: ErrorClass,
        /// The status message carried by the transport failure, verbatim.
        message: String,
    },
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
            Self::Transport { message, .. } => write!(f, "transport failure: {message}"),
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
            // Precomputed at construction time by `from_status`, per
            // condition — never a blanket classification for every
            // transport failure alike.
            Self::Transport { kind, .. } => *kind,
        }
    }
}

impl From<ChannelClosed> for WorkerError {
    fn from(cause: ChannelClosed) -> Self {
        Self::ChannelClosed(cause)
    }
}

// The `tonic::Status` -> `WorkerError` mapping (design.md D5) lives in
// `adapters/grpc/convert.rs`, not here: this crate's architecture guard
// (`runtime_worker_transport_types_stay_inside_the_private_adapter_module`)
// forbids any `tonic::`/`prost::` token outside the private adapter module,
// and `error.rs` is not part of it. `WorkerError::from_status` is still
// reachable as `WorkerError::from_status(..)` from there — the `impl
// WorkerError` block granting it lives in `convert.rs`, in the same crate.

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

    #[test]
    fn transport_variant_display_carries_the_message() {
        let error = WorkerError::Transport {
            kind: ErrorClass::Transient,
            message: "connection refused".to_string(),
        };
        assert!(format!("{error}").contains("connection refused"));
    }

    #[test]
    fn transport_variant_classifies_by_its_stored_kind() {
        let transient = WorkerError::Transport {
            kind: ErrorClass::Transient,
            message: String::new(),
        };
        assert_eq!(transient.classify(), ErrorClass::Transient);

        let permanent = WorkerError::Transport {
            kind: ErrorClass::Permanent,
            message: String::new(),
        };
        assert_eq!(permanent.classify(), ErrorClass::Permanent);
    }
}
