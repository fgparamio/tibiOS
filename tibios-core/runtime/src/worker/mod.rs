//! The Composition Root's own concrete Worker wiring — owned exclusively by
//! `runtime`, never `runtime-worker` (`runtime-worker/spec.md` forbids any
//! `tokio::` path there). This module tree is where `runtime`'s sole
//! `tokio` dependency is actually used.

mod channel;
mod in_process;
mod registry;

use in_process::InProcessWorker;
use runtime_worker::WorkerService;

// `#[allow(unused_imports)]`: not yet used from `main.rs` — wiring lands in
// PR 3 of this change (`design.md` D9). Remove this allow there.
#[allow(unused_imports)]
pub use channel::MpscExecutionChannel;

/// Builds the in-process `WorkerService`. The **only** way any caller
/// obtains a worker instance — `InProcessWorker` is `pub(super)` and never
/// re-exported, so no binding site can name the concrete type or the
/// transport it implies (`worker-inprocess-adapter/spec.md`; design.md D5).
/// Takes no arguments: per-execution behavior comes entirely from
/// `ExecutionContext`, so there is nothing to configure here.
///
/// `#[allow(dead_code)]`: not yet called from `main.rs` — that wiring lands
/// in PR 3 of this change (design.md D9). Remove this allow there.
#[allow(dead_code)]
#[must_use]
pub fn in_process_worker() -> impl WorkerService {
    InProcessWorker::new()
}
