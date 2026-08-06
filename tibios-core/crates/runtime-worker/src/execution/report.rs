//! `ExecutionReport`, `ExecutionPhase`, `ExecutionPulse`, and `CancelAck`:
//! the values a Worker returns while performing, or being asked about, one
//! execution (`18-worker-model.md`).

/// The phase of one execution. Exactly six variants, corresponding to six
/// of the frozen wire contract's seven `ExecutionPhase` values. The wire's
/// `EXECUTION_PHASE_UNSPECIFIED` proto3 tag-zero obligation is deliberately
/// **not** modeled here: this type defines no `Unspecified`/`Unknown`/
/// placeholder variant and implements no `Default`
/// (`runtime-worker/spec.md` — "ExecutionPhase Has Exactly Six States And
/// No Placeholder"). An unset wire value is a conversion-time rejection
/// (`worker-wire-adapter/spec.md`), never a domain value.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExecutionPhase {
    /// The execution request has been received but not yet prepared.
    Received,
    /// The execution's dependencies and context have been prepared.
    Prepared,
    /// The execution is actively running.
    Running,
    /// The execution finished successfully.
    Completed,
    /// The execution finished with a failure.
    Failed,
    /// The execution was cancelled.
    Cancelled,
}

/// The terminal outcome of one execution, returned as `execute`'s return
/// value rather than emitted through the `ExecutionChannel` — a cancelled
/// execution still returns a `Completed`-or-`Cancelled`-tagged Report
/// (`18-worker-model.md:118`; design.md D11 Consequences: "completion
/// remains owned by the Worker... even mid-cancellation").
#[derive(Debug, Clone, PartialEq)]
pub struct ExecutionReport {
    /// The phase the execution ended in.
    pub final_phase: ExecutionPhase,
    /// How long the execution ran, from receipt to this Report.
    pub duration: core::time::Duration,
    /// The trace identifier this execution ran under.
    pub trace_id: String,
    /// A human-readable summary of the outcome.
    pub summary: String,
}

/// A point-in-time health check response for one in-flight execution,
/// returned by `WorkerService::pulse`.
#[derive(Debug, Clone, PartialEq)]
pub struct ExecutionPulse {
    /// The phase the execution is currently in.
    pub phase: ExecutionPhase,
    /// Whether the Worker considers this execution healthy.
    pub healthy: bool,
}

/// The response to a `WorkerService::cancel` call. Means "cancellation
/// request accepted", and NEVER means "execution terminated": completion
/// remains Worker-owned and is observed only through `execute`'s own
/// return value (`worker.proto:213-220`; `18-worker-model.md:118`).
/// `cancel` is idempotent while the execution is registered — a second
/// `cancel` returns another `CancelAck` (design.md D11 Decision). A named
/// unit struct, not `()`, so it stays evolvable, mirroring the wire's own
/// choice of a named message over `google.protobuf.Empty`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CancelAck;

#[cfg(test)]
mod tests {
    use super::{CancelAck, ExecutionPhase, ExecutionPulse, ExecutionReport};

    /// Exhaustive match over `ExecutionPhase`'s variants: a seventh arm
    /// added later breaks this build (`runtime-worker/spec.md` —
    /// "ExecutionPhase Has Exactly Six States And No Placeholder").
    fn describe(phase: ExecutionPhase) -> &'static str {
        match phase {
            ExecutionPhase::Received => "received",
            ExecutionPhase::Prepared => "prepared",
            ExecutionPhase::Running => "running",
            ExecutionPhase::Completed => "completed",
            ExecutionPhase::Failed => "failed",
            ExecutionPhase::Cancelled => "cancelled",
        }
    }

    #[test]
    fn execution_phase_matches_exhaustively_over_all_six_variants() {
        let phases = [
            ExecutionPhase::Received,
            ExecutionPhase::Prepared,
            ExecutionPhase::Running,
            ExecutionPhase::Completed,
            ExecutionPhase::Failed,
            ExecutionPhase::Cancelled,
        ];

        let described: Vec<&'static str> = phases.into_iter().map(describe).collect();
        assert_eq!(
            described,
            vec![
                "received",
                "prepared",
                "running",
                "completed",
                "failed",
                "cancelled",
            ]
        );
    }

    // No runtime assertion is possible for "ExecutionPhase does not
    // implement Default" — confirmed by code review only, per
    // tasks.md 3b.13. If a `Default` impl is ever added, this comment is
    // the place a reviewer should look for the requirement it violates.

    #[test]
    fn execution_report_carries_its_final_phase_and_duration() {
        let report = ExecutionReport {
            final_phase: ExecutionPhase::Completed,
            duration: core::time::Duration::from_secs(3),
            trace_id: "trace-1".to_string(),
            summary: "done".to_string(),
        };
        assert_eq!(report.final_phase, ExecutionPhase::Completed);
        assert_eq!(report.duration, core::time::Duration::from_secs(3));
    }

    #[test]
    fn execution_pulse_carries_its_phase_and_health() {
        let pulse = ExecutionPulse {
            phase: ExecutionPhase::Running,
            healthy: true,
        };
        assert_eq!(pulse.phase, ExecutionPhase::Running);
        assert!(pulse.healthy);
    }

    #[test]
    fn cancel_ack_is_a_unit_value_distinct_from_the_empty_tuple() {
        let ack = CancelAck;
        assert_eq!(ack, CancelAck);
    }
}
