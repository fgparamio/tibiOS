//! `Registry`: workload-keyed bookkeeping backing `InProcessWorker`'s O1-O4
//! obligations (design.md D7) — an `Arc<Mutex<HashMap<..>>>`, accessed only
//! through synchronous helpers so no `MutexGuard` ever crosses an `.await`.
//!
//! Deviation from `design.md` D7: the design's pseudocode names
//! `BTreeMap<WorkloadId, Registration>`, but `WorkloadId` (the
//! `ulid_newtype!` macro, `runtime-primitives/src/identity.rs`) derives
//! `Hash + Eq`, not `Ord` — unlike `ObjectVersion`, which derives `Ord`
//! explicitly. A literal `BTreeMap<WorkloadId, _>` does not compile.
//! `HashMap` preserves D7's actual rationale (one mutex-guarded map, no
//! `MutexGuard` crossing an `.await`) without requiring iteration order,
//! which nothing here depends on.

use std::collections::HashMap;
use std::sync::{Arc, Mutex};

use runtime_primitives::WorkloadId;
use runtime_worker::{CancelAck, ExecutionPhase, ExecutionPulse, WorkerError};

/// One workload's live bookkeeping: its current phase (for `pulse`) and
/// whether a `cancel` request has been accepted (observed by the run loop).
#[derive(Debug, Clone, Copy)]
struct Registration {
    phase: ExecutionPhase,
    cancelled: bool,
}

/// The workload-keyed registry backing O1 (register before the first
/// suspension point), O2 (deregister on every path), O3 (unknown-id
/// rejection), and O4 (duplicate-in-flight rejection). Every access goes
/// through a synchronous critical section — no `MutexGuard` is ever held
/// across an `.await` (design.md D7): `std::sync::MutexGuard` is `!Send`,
/// so holding one across a suspension point would make the enclosing
/// future non-`Send`, and the compiler rejects the code outright — the
/// rule is enforced by the type system, not by review.
pub(super) struct Registry {
    state: Mutex<HashMap<WorkloadId, Registration>>,
}

impl Registry {
    pub(super) fn new() -> Self {
        Self {
            state: Mutex::new(HashMap::new()),
        }
    }

    fn with_registry<T>(&self, f: impl FnOnce(&mut HashMap<WorkloadId, Registration>) -> T) -> T {
        let mut state = self.state.lock().expect("registry mutex poisoned");
        f(&mut state)
    }

    /// Inserts a fresh registration for `workload_id`, returning `true` if
    /// it was absent (now registered) or `false` if it was already present
    /// (no change made) — the synchronous half of O1/O4.
    fn insert_if_absent(&self, workload_id: WorkloadId) -> bool {
        self.with_registry(|state| match state.entry(workload_id) {
            std::collections::hash_map::Entry::Occupied(_) => false,
            std::collections::hash_map::Entry::Vacant(entry) => {
                entry.insert(Registration {
                    phase: ExecutionPhase::Received,
                    cancelled: false,
                });
                true
            }
        })
    }

    fn deregister(&self, workload_id: WorkloadId) {
        self.with_registry(|state| {
            state.remove(&workload_id);
        });
    }

    pub(super) fn set_phase(&self, workload_id: WorkloadId, phase: ExecutionPhase) {
        self.with_registry(|state| {
            if let Some(registration) = state.get_mut(&workload_id) {
                registration.phase = phase;
            }
        });
    }

    pub(super) fn is_cancelled(&self, workload_id: WorkloadId) -> bool {
        self.with_registry(|state| {
            state
                .get(&workload_id)
                .is_some_and(|registration| registration.cancelled)
        })
    }

    /// True when the runtime side no longer wants this execution to
    /// continue: either `cancel` was accepted, or the registration is gone
    /// entirely — which means `execute`'s future was dropped and nobody is
    /// waiting (design.md D9). The `is_none()` half is the part a naive
    /// `is_cancelled` reuse would miss: it is how an abandoned blocking task
    /// learns nobody is waiting anymore.
    ///
    /// Temporary: `LocalInferWorker` (the only caller) isn't wired into
    /// `main.rs`'s bin target until PR3 — until then this is dead code from
    /// the bin target's point of view, though fully exercised by this
    /// module's own tests. Disappears once PR3 lands.
    #[allow(dead_code)]
    pub(super) fn should_stop(&self, workload_id: WorkloadId) -> bool {
        self.with_registry(|state| {
            state
                .get(&workload_id)
                .is_none_or(|registration| registration.cancelled)
        })
    }


    /// Idempotent while registered (`worker-inbound-port/design.md` D11
    /// Decision): every call against a still-registered id returns another
    /// `Ok(CancelAck)`, never an error.
    pub(super) fn cancel(&self, workload_id: WorkloadId) -> Result<CancelAck, WorkerError> {
        self.with_registry(|state| {
            state.get_mut(&workload_id).map_or(
                Err(WorkerError::UnknownWorkload(workload_id)),
                |registration| {
                    registration.cancelled = true;
                    Ok(CancelAck)
                },
            )
        })
    }

    pub(super) fn pulse(&self, workload_id: WorkloadId) -> Result<ExecutionPulse, WorkerError> {
        self.with_registry(|state| {
            state.get(&workload_id).map_or(
                Err(WorkerError::UnknownWorkload(workload_id)),
                |registration| {
                    Ok(ExecutionPulse {
                        phase: registration.phase,
                        healthy: !registration.cancelled,
                    })
                },
            )
        })
    }
}

/// RAII guard proving O1 (registration happens synchronously, inside this
/// guard's constructor — `try_acquire` — before it ever returns) and O2
/// (`Drop` deregisters on every path: success, failure, or the future being
/// dropped before it ever completes).
pub(super) struct RegistrationGuard {
    registry: Arc<Registry>,
    workload_id: WorkloadId,
}

impl RegistrationGuard {
    /// Attempts to register `workload_id` against `registry`, synchronously
    /// — no `.await` anywhere in this function. Returns `None` without
    /// constructing a guard if `workload_id` already has a live
    /// registration (O4): critically, this means the losing call's `Drop`
    /// never runs and can never deregister the *winner's* entry.
    pub(super) fn try_acquire(registry: Arc<Registry>, workload_id: WorkloadId) -> Option<Self> {
        registry.insert_if_absent(workload_id).then(|| Self {
            registry,
            workload_id,
        })
    }

    pub(super) fn is_cancelled(&self) -> bool {
        self.registry.is_cancelled(self.workload_id)
    }

    pub(super) fn set_phase(&self, phase: ExecutionPhase) {
        self.registry.set_phase(self.workload_id, phase);
    }
}

impl Drop for RegistrationGuard {
    fn drop(&mut self) {
        self.registry.deregister(self.workload_id);
    }
}

#[cfg(test)]
mod tests {
    use std::sync::Arc;

    use runtime_primitives::WorkloadId;

    use super::{RegistrationGuard, Registry};

    #[test]
    fn try_acquire_succeeds_for_a_fresh_workload_id() {
        let registry = Arc::new(Registry::new());
        let workload_id = WorkloadId::new();

        let guard = RegistrationGuard::try_acquire(Arc::clone(&registry), workload_id);

        assert!(guard.is_some());
    }

    #[test]
    fn try_acquire_returns_none_for_an_already_registered_workload_id() {
        let registry = Arc::new(Registry::new());
        let workload_id = WorkloadId::new();
        let _first = RegistrationGuard::try_acquire(Arc::clone(&registry), workload_id)
            .expect("first acquire on a fresh id must succeed");

        let second = RegistrationGuard::try_acquire(Arc::clone(&registry), workload_id);

        assert!(second.is_none());
    }

    #[test]
    fn dropping_the_guard_deregisters_the_workload_id() {
        let registry = Arc::new(Registry::new());
        let workload_id = WorkloadId::new();
        let guard = RegistrationGuard::try_acquire(Arc::clone(&registry), workload_id)
            .expect("acquire on a fresh id must succeed");

        drop(guard);

        let reacquired = RegistrationGuard::try_acquire(Arc::clone(&registry), workload_id);
        assert!(
            reacquired.is_some(),
            "dropping the guard must free the workload id for reacquisition"
        );
    }

    /// Task 2.2 / design.md D9: `should_stop` is true when cancelled, true
    /// when the registration is absent entirely (deregistered or never
    /// existed), and false when present and not cancelled.
    #[test]
    fn should_stop_is_true_when_cancelled_true_when_absent_false_otherwise() {
        let registry = Registry::new();
        let cancelled_id = WorkloadId::new();
        let present_id = WorkloadId::new();
        let never_registered_id = WorkloadId::new();

        registry.insert_if_absent(cancelled_id);
        registry
            .cancel(cancelled_id)
            .expect("cancel on a freshly registered id must succeed");
        assert!(registry.should_stop(cancelled_id));

        registry.insert_if_absent(present_id);
        assert!(!registry.should_stop(present_id));

        assert!(registry.should_stop(never_registered_id));

        registry.deregister(present_id);
        assert!(registry.should_stop(present_id));
    }
}
