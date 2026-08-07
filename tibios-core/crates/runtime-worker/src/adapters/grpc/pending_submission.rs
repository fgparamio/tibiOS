//! `PendingSubmissions`: the *only* client-side state `RayWorker` keeps for
//! a workload, and only for the brief window between `execute()` being
//! called and its `SubmitJob` RPC being acknowledged.
//!
//! Architectural rule this exists to enforce: the client owns workload
//! identity only until successful submission; once `SubmitJob` returns
//! `Ok`, the server has already registered the workload (the fake harness's
//! `submit_job` does this synchronously before returning its response
//! stream, and a real `tibios-ray` must too), so the server becomes the
//! sole authority for the rest of the workload's lifecycle — `cancel`/
//! `pulse` forward straight to it, unmodified, exactly as before this
//! module existed. Two authorities over the same resource never coexist:
//! before `SubmitJob` succeeds, only this table knows about the workload;
//! after, only the server does.

use std::collections::HashMap;
use std::collections::hash_map::Entry;
use std::sync::{Arc, Mutex};

use runtime_primitives::WorkloadId;

/// A pending workload's only state: whether `cancel()` arrived before
/// `SubmitJob` was acknowledged. An enum, not a `bool` — leaves room to add
/// a variant (e.g. a future `TimedOut`) without reshaping the table's value
/// type; not because today's logic needs more than two states.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum PendingState {
    Pending,
    CancelRequested,
}

/// `Mutex<HashMap<..>>`, same "no `MutexGuard` ever crosses an `.await`"
/// rule `runtime/src/worker/registry.rs` documents for its own, unrelated
/// registry — every access here is synchronous too.
#[derive(Default)]
pub(super) struct PendingSubmissions {
    state: Mutex<HashMap<WorkloadId, PendingState>>,
}

impl PendingSubmissions {
    fn with_state<T>(&self, f: impl FnOnce(&mut HashMap<WorkloadId, PendingState>) -> T) -> T {
        let mut state = self.state.lock().expect("pending-submissions mutex poisoned");
        f(&mut state)
    }

    fn insert_if_absent(&self, workload_id: WorkloadId) -> bool {
        self.with_state(|state| match state.entry(workload_id) {
            Entry::Occupied(_) => false,
            Entry::Vacant(entry) => {
                entry.insert(PendingState::Pending);
                true
            }
        })
    }

    fn remove(&self, workload_id: WorkloadId) {
        self.with_state(|state| {
            state.remove(&workload_id);
        });
    }

    /// The synchronous half of the O1 cancel-before-submit path: marks the
    /// entry `CancelRequested` if it is still present (`SubmitJob` hasn't
    /// been acknowledged yet), returning whether it found one to mark.
    /// `false` means either this workload was never registered here, or it
    /// already graduated past this table (submission already succeeded) —
    /// either way, `RayWorker::cancel` falls back to its normal server
    /// round trip.
    pub(super) fn mark_cancel_requested(&self, workload_id: WorkloadId) -> bool {
        self.with_state(|state| match state.get_mut(&workload_id) {
            Some(entry) => {
                *entry = PendingState::CancelRequested;
                true
            }
            None => false,
        })
    }

    fn is_cancel_requested(&self, workload_id: WorkloadId) -> bool {
        self.with_state(|state| state.get(&workload_id) == Some(&PendingState::CancelRequested))
    }
}

/// RAII guard proving O1 + O4: constructed synchronously in `execute()`'s
/// own function body, never inside the `async move` block it returns — so a
/// concurrent duplicate `execute()` call, or a `cancel()`, racing against
/// this one always sees the workload already claimed. `Drop` removes the
/// table entry on every exit path this guard's holder takes: `SubmitJob`
/// acknowledged (authority now the server's), `SubmitJob` failed (nothing
/// was ever the server's to own), or cancelled before submission (already
/// resolved locally, nothing left to track).
pub(super) struct PendingSubmissionGuard {
    table: Arc<PendingSubmissions>,
    workload_id: WorkloadId,
}

impl PendingSubmissionGuard {
    /// Attempts to register `workload_id`, synchronously — no `.await`
    /// anywhere in this function. Returns `None` without constructing a
    /// guard if `workload_id` already has a live entry (O4): the losing
    /// call's `Drop` never runs and can never remove the winner's entry.
    pub(super) fn try_acquire(
        table: Arc<PendingSubmissions>,
        workload_id: WorkloadId,
    ) -> Option<Self> {
        table
            .insert_if_absent(workload_id)
            .then(|| Self { table, workload_id })
    }

    pub(super) fn is_cancel_requested(&self) -> bool {
        self.table.is_cancel_requested(self.workload_id)
    }
}

impl Drop for PendingSubmissionGuard {
    fn drop(&mut self) {
        self.table.remove(self.workload_id);
    }
}

#[cfg(test)]
mod tests {
    use std::sync::Arc;

    use runtime_primitives::WorkloadId;

    use super::{PendingSubmissionGuard, PendingSubmissions};

    #[test]
    fn try_acquire_succeeds_for_a_fresh_workload_id() {
        let table = Arc::new(PendingSubmissions::default());
        let workload_id = WorkloadId::new();

        let guard = PendingSubmissionGuard::try_acquire(Arc::clone(&table), workload_id);

        assert!(guard.is_some());
    }

    #[test]
    fn try_acquire_returns_none_for_an_already_registered_workload_id() {
        let table = Arc::new(PendingSubmissions::default());
        let workload_id = WorkloadId::new();
        let _first = PendingSubmissionGuard::try_acquire(Arc::clone(&table), workload_id)
            .expect("first acquire on a fresh id must succeed");

        let second = PendingSubmissionGuard::try_acquire(Arc::clone(&table), workload_id);

        assert!(second.is_none());
    }

    #[test]
    fn dropping_the_guard_frees_the_workload_id_for_reacquisition() {
        let table = Arc::new(PendingSubmissions::default());
        let workload_id = WorkloadId::new();
        let guard = PendingSubmissionGuard::try_acquire(Arc::clone(&table), workload_id)
            .expect("acquire on a fresh id must succeed");

        drop(guard);

        let reacquired = PendingSubmissionGuard::try_acquire(Arc::clone(&table), workload_id);
        assert!(reacquired.is_some());
    }

    #[test]
    fn mark_cancel_requested_returns_false_for_an_unregistered_workload_id() {
        let table = PendingSubmissions::default();

        assert!(!table.mark_cancel_requested(WorkloadId::new()));
    }

    #[test]
    fn mark_cancel_requested_is_observed_by_the_live_guard() {
        let table = Arc::new(PendingSubmissions::default());
        let workload_id = WorkloadId::new();
        let guard = PendingSubmissionGuard::try_acquire(Arc::clone(&table), workload_id)
            .expect("acquire on a fresh id must succeed");

        assert!(table.mark_cancel_requested(workload_id));

        assert!(guard.is_cancel_requested());
    }
}
