//! The Composition Root's own concrete Worker wiring — owned exclusively by
//! `runtime`, never `runtime-worker` (`runtime-worker/spec.md` forbids any
//! `tokio::` path there). This module tree is where `runtime`'s sole
//! `tokio` dependency is actually used.

mod any;
mod channel;
#[cfg(test)]
mod conformance;
mod in_process;
mod local_infer;
mod ray_dispatch;
mod registry;

use any::AnyWorker;
use in_process::InProcessWorker;
use local_infer::build_local_infer_worker;
use ray_dispatch::RayDispatch;
use runtime_worker::WorkerService;

pub use channel::MpscExecutionChannel;

/// Selects which concrete `WorkerService` implementation `any_worker`
/// builds (`runtime-composition-root/spec.md`; design.md D10).
pub enum WorkerKind {
    /// Never selected by `main.rs` — the plain `bin` target always picks
    /// `Ray` — but exercised via `any_worker(WorkerKind::InProcess)` by
    /// `any.rs`'s own conformance-suite invocations and eagerness test.
    /// Precedent for a variant-level allow (not module-level):
    /// `crates/runtime-worker/src/adapters/grpc/convert.rs:481`.
    #[allow(dead_code)]
    InProcess,
    /// Never selected by `main.rs` (see `InProcess`'s doc comment) —
    /// exercised only via `runtime/src/worker/conformance.rs`'s own
    /// conformance-suite invocation.
    #[allow(dead_code)]
    LocalInfer,
    /// Carries the `tibios-ray` gRPC endpoint (`worker-grpc-client-adapter/design.md`
    /// D2) — `main.rs` reads it from `TIBIOS_RAY_ENDPOINT`.
    Ray(String),
}

/// Builds a `WorkerService`, selecting the concrete implementation via
/// `kind` — an implementation *selection*, which
/// `02-project-structure.md`'s Composition Root section assigns exclusively
/// to `runtime` (design.md D10). Neither `AnyWorker` nor either concrete
/// Worker type is ever named outside `worker/`; only this function's `impl
/// WorkerService` return type crosses that boundary.
#[must_use]
pub fn any_worker(kind: WorkerKind) -> impl WorkerService {
    match kind {
        WorkerKind::InProcess => AnyWorker::InProcess(InProcessWorker::new()),
        WorkerKind::LocalInfer => AnyWorker::LocalInfer(build_local_infer_worker()),
        WorkerKind::Ray(endpoint) => AnyWorker::Ray(Box::new(RayDispatch(
            runtime_worker::new_ray_worker(endpoint),
        ))),
    }
}
