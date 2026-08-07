//! The shared O1-O4 conformance harness
//! (`worker-inbound-port/spec.md` — "A Shared O1-O4 Conformance Harness
//! Exercises Every WorkerService Implementation"; design.md D11).
//!
//! `#[cfg(test)]`-gated at the declaration site (`worker/mod.rs`), because
//! `runtime` is a binary-only crate with no library target: an integration
//! test under `runtime/tests/` cannot reach any `pub(super)` Worker type, so
//! this harness has to live inside `runtime`'s own source tree instead.
//!
//! Six generic async assertions, one per obligation (O1, O2 x3, O3, O4),
//! each `async fn<W: WorkerService>(worker: W)` — the same assertion logic
//! runs unmodified against any `WorkerService` implementation. The
//! `worker_conformance_suite!` macro emits all six as `#[tokio::test]`
//! wrappers so conformance is all-or-nothing per invocation: no Worker can
//! silently adopt five obligations and skip the sixth.
//!
//! Invoked at least three times: once for `InProcessWorker`
//! (`in_process.rs`), once for `LocalInferWorker` (`local_infer/mod.rs`),
//! and once for each `AnyWorker` variant (`any.rs`) — the last is not
//! ceremony, since the dispatch layer is exactly where an eagerness
//! regression would silently reintroduce an O1 violation unobserved.

use std::collections::BTreeMap;
use std::time::Duration;

use runtime_allocation::AllocationContract;
use runtime_primitives::{AllocationId, ContentHash, ObjectId, ObjectVersion, WorkloadId};
use runtime_worker::{
    CancelAck, ExecutionContext, ExecutionEvent, ExecutionPhase, ObservabilityContext,
    ResolvedDependency, SecurityContext, WorkerCapability, WorkerError, WorkerService,
};
use tokio::sync::mpsc;

use super::channel::MpscExecutionChannel;

/// Builds an `ExecutionContext` from explicit `allocation_contract` and
/// `execution_parameters`, everything else fixed and unremarkable — moved
/// out of `in_process.rs`'s test module (task 3.1) so both concrete
/// Workers' test modules share one definition instead of two copies.
pub(super) fn context_with(
    workload_id: WorkloadId,
    allocation_contract: AllocationContract,
    execution_parameters: BTreeMap<String, String>,
) -> ExecutionContext {
    let dependency = ResolvedDependency::new(
        ObjectId::new(),
        ObjectVersion::initial(),
        ContentHash::new("sha256:af23"),
    );
    ExecutionContext::new(
        workload_id,
        AllocationId::new(),
        allocation_contract,
        vec![dependency],
        SecurityContext::new("tenant-1", "principal-1", vec!["scope-a".to_string()]),
        ObservabilityContext::new("trace-1", "span-1"),
        execution_parameters,
        WorkerCapability::new("chat.generate"),
    )
}

/// `context_with` with a generous 30s allocation contract and no execution
/// parameters — the default context for tests that don't care about timing
/// or per-run configuration.
pub(super) fn sample_context(workload_id: WorkloadId) -> ExecutionContext {
    context_with(
        workload_id,
        AllocationContract::new(Duration::from_secs(30)),
        BTreeMap::new(),
    )
}

/// A channel whose capacity comfortably exceeds every event any fixture
/// execution in this harness emits. The `Receiver` half MUST stay bound
/// (never `_`) in a caller that later drains it — for callers that never
/// drain, an unbound `_receiver` is fine only because capacity already
/// exceeds every event a single default-sized execution can emit (design
/// D11): with no drainer at all, a blocking-backed Worker's
/// `Handle::block_on(emit)` would otherwise park its thread forever once the
/// channel fills, hanging the test rather than failing it.
pub(super) fn generous_channel() -> (MpscExecutionChannel, mpsc::Receiver<ExecutionEvent>) {
    let (sender, receiver) = mpsc::channel(32);
    (MpscExecutionChannel::new(sender), receiver)
}

// ---- O1 ----

/// O1: a cancel issued immediately after `execute` is called — before its
/// returned future has ever been polled — is accepted, never lost to a
/// registration race.
pub(super) async fn assert_o1_cancel_immediately_after_execute_is_accepted<W: WorkerService>(
    worker: W,
) {
    let workload_id = WorkloadId::new();
    let (channel, _receiver) = generous_channel();

    let execute_future = worker.execute(sample_context(workload_id), channel);
    let cancel_result = worker.cancel(workload_id).await;
    assert_eq!(cancel_result, Ok(CancelAck));

    let report = execute_future
        .await
        .expect("execute must still complete after an immediate cancel");
    assert_eq!(report.final_phase, ExecutionPhase::Cancelled);
}

// ---- O2 (x3: completed / cancelled / duration-breached) ----

pub(super) async fn assert_o2_pulse_is_unknown_after_completion<W: WorkerService>(worker: W) {
    let workload_id = WorkloadId::new();
    let (channel, _receiver) = generous_channel();

    let report = worker
        .execute(sample_context(workload_id), channel)
        .await
        .expect("execute must complete successfully");
    assert_eq!(report.final_phase, ExecutionPhase::Completed);

    let pulse_result = worker.pulse(workload_id).await;
    assert!(matches!(
        pulse_result,
        Err(WorkerError::UnknownWorkload(id)) if id == workload_id
    ));
}

pub(super) async fn assert_o2_pulse_is_unknown_after_cancellation<W: WorkerService>(worker: W) {
    let workload_id = WorkloadId::new();
    let (channel, _receiver) = generous_channel();

    let execute_future = worker.execute(sample_context(workload_id), channel);
    worker
        .cancel(workload_id)
        .await
        .expect("cancel on a freshly registered workload must succeed");
    let report = execute_future
        .await
        .expect("a cancelled execution still returns a report, not an error");
    assert_eq!(report.final_phase, ExecutionPhase::Cancelled);

    let pulse_result = worker.pulse(workload_id).await;
    assert!(matches!(
        pulse_result,
        Err(WorkerError::UnknownWorkload(id)) if id == workload_id
    ));
}

pub(super) async fn assert_o2_pulse_is_unknown_after_duration_breach<W: WorkerService>(worker: W) {
    let workload_id = WorkloadId::new();
    let (channel, _receiver) = generous_channel();
    let context = context_with(
        workload_id,
        AllocationContract::new(Duration::ZERO),
        BTreeMap::new(),
    );

    let report = worker
        .execute(context, channel)
        .await
        .expect("a duration breach still returns a report, not an error");
    assert_eq!(report.final_phase, ExecutionPhase::Failed);

    let pulse_result = worker.pulse(workload_id).await;
    assert!(matches!(
        pulse_result,
        Err(WorkerError::UnknownWorkload(id)) if id == workload_id
    ));
}

// ---- O3 ----

/// O3: a `workload_id` with no in-flight registration is rejected by both
/// `cancel` and `pulse`.
pub(super) async fn assert_o3_unknown_workload_rejected_by_cancel_and_pulse<W: WorkerService>(
    worker: W,
) {
    let workload_id = WorkloadId::new();

    let cancel_result = worker.cancel(workload_id).await;
    assert!(matches!(
        cancel_result,
        Err(WorkerError::UnknownWorkload(id)) if id == workload_id
    ));

    let pulse_result = worker.pulse(workload_id).await;
    assert!(matches!(
        pulse_result,
        Err(WorkerError::UnknownWorkload(id)) if id == workload_id
    ));
}

// ---- O4 ----

/// O4: a second `execute` call for an already in-flight `workload_id` is
/// rejected without starting a second execution — nothing is ever emitted
/// on the duplicate call's own channel.
pub(super) async fn assert_o4_duplicate_in_flight_execute_is_rejected<W: WorkerService>(worker: W) {
    let workload_id = WorkloadId::new();
    let (first_channel, _first_receiver) = generous_channel();
    let (second_channel, mut second_receiver) = generous_channel();

    let first_execute = worker.execute(sample_context(workload_id), first_channel);
    let duplicate_result = worker
        .execute(sample_context(workload_id), second_channel)
        .await;
    assert!(matches!(
        duplicate_result,
        Err(WorkerError::DuplicateWorkload(id)) if id == workload_id
    ));
    assert!(second_receiver.try_recv().is_err());

    let report = first_execute
        .await
        .expect("the first, still-registered execution must complete normally");
    assert_eq!(report.final_phase, ExecutionPhase::Completed);
}

/// Emits one `#[tokio::test]` wrapper per obligation assertion above, each
/// invoking a freshly built `$factory` — a `WorkerService` value with fresh,
/// unshared state, since the six obligation assertions share no state across
/// each other (design D11: "conformance becomes all-or-nothing").
///
/// Expands to bare items (no wrapping `mod`): a wrapping module would be a
/// syntactically NEW item nested one level deeper than wherever the macro is
/// invoked, and — unlike names written directly in `$factory`'s own tokens,
/// which hygiene resolves against the invocation site regardless of nesting
/// — a nested module introduced by the macro's own body does not inherit
/// the invocation site's `use` imports for free. Concretely: `$factory`'s
/// tokens (e.g. `AnyWorker::InProcess(..)`) still resolve fine wherever
/// they're spliced, but a bare `mod inner { .. }` written directly in this
/// macro would need its OWN `use super::*;` to see anything, and hygiene
/// can't supply that for us. So: a single invocation per file goes directly
/// in the caller's own `#[cfg(test)] mod tests { .. }`; a second invocation
/// in the same file (`any.rs`, one per `AnyWorker` variant) needs the
/// caller to wrap it in its own small `mod { use super::*; .. }` — the
/// caller controls that wrapping, not this macro.
macro_rules! worker_conformance_suite {
    ($factory:expr) => {
        #[tokio::test]
        async fn o1_cancel_immediately_after_execute_is_accepted() {
            $crate::worker::conformance::assert_o1_cancel_immediately_after_execute_is_accepted(
                $factory,
            )
            .await;
        }

        #[tokio::test]
        async fn o2_pulse_is_unknown_after_completion() {
            $crate::worker::conformance::assert_o2_pulse_is_unknown_after_completion($factory)
                .await;
        }

        #[tokio::test]
        async fn o2_pulse_is_unknown_after_cancellation() {
            $crate::worker::conformance::assert_o2_pulse_is_unknown_after_cancellation($factory)
                .await;
        }

        #[tokio::test]
        async fn o2_pulse_is_unknown_after_duration_breach() {
            $crate::worker::conformance::assert_o2_pulse_is_unknown_after_duration_breach($factory)
                .await;
        }

        #[tokio::test]
        async fn o3_unknown_workload_rejected_by_cancel_and_pulse() {
            $crate::worker::conformance::assert_o3_unknown_workload_rejected_by_cancel_and_pulse(
                $factory,
            )
            .await;
        }

        #[tokio::test]
        async fn o4_duplicate_in_flight_execute_is_rejected() {
            $crate::worker::conformance::assert_o4_duplicate_in_flight_execute_is_rejected(
                $factory,
            )
            .await;
        }
    };
}

pub(super) use worker_conformance_suite;
