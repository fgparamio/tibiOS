//! The Composition Root's own concrete Worker wiring — owned exclusively by
//! `runtime`, never `runtime-worker` (`runtime-worker/spec.md` forbids any
//! `tokio::` path there). This module tree is where `runtime`'s sole
//! `tokio` dependency is actually used.

mod channel;
mod in_process;
mod local_infer;
mod registry;

use in_process::InProcessWorker;
use runtime_worker::WorkerService;

pub use channel::MpscExecutionChannel;

/// Builds the in-process `WorkerService`. The **only** way any caller
/// obtains a worker instance — `InProcessWorker` is `pub(super)` and never
/// re-exported, so no binding site can name the concrete type or the
/// transport it implies (`worker-inprocess-adapter/spec.md`; design.md D5).
/// Takes no arguments: per-execution behavior comes entirely from
/// `ExecutionContext`, so there is nothing to configure here.
#[must_use]
pub fn in_process_worker() -> impl WorkerService {
    InProcessWorker::new()
}
