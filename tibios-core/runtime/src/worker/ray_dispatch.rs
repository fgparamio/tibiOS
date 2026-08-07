//! `ErasedWorker`: an object-safe erasure of `WorkerService`, monomorphized
//! to `MpscExecutionChannel` — the only `ExecutionChannel` `runtime` ever
//! constructs (`worker-grpc-client-adapter/design.md` D1). `WorkerService`
//! itself is not object-safe (`execute<C>` is generic), so `AnyWorker`
//! cannot hold a `Box<dyn WorkerService>` directly; `RayDispatch<W>`
//! blanket-implements `ErasedWorker` for any `W: WorkerService`, giving
//! `AnyWorker::Ray` a `Box<dyn ErasedWorker>` to store instead.

use core::future::Future;
use core::pin::Pin;

use runtime_primitives::WorkloadId;
use runtime_worker::{
    CancelAck, ExecutionContext, ExecutionPulse, ExecutionReport, WorkerError, WorkerService,
};

use super::channel::MpscExecutionChannel;

/// `Send + Sync` supertraits (not just per-method bounds) so `Box<dyn
/// ErasedWorker>` alone is enough for `AnyWorker` to stay `Send + Sync`,
/// matching `WorkerService`'s own supertraits.
pub(super) trait ErasedWorker: Send + Sync {
    fn execute(
        &self,
        context: ExecutionContext,
        channel: MpscExecutionChannel,
    ) -> Pin<Box<dyn Future<Output = Result<ExecutionReport, WorkerError>> + Send + '_>>;

    fn cancel(
        &self,
        workload_id: WorkloadId,
    ) -> Pin<Box<dyn Future<Output = Result<CancelAck, WorkerError>> + Send + '_>>;

    fn pulse(
        &self,
        workload_id: WorkloadId,
    ) -> Pin<Box<dyn Future<Output = Result<ExecutionPulse, WorkerError>> + Send + '_>>;
}

/// Wraps any `WorkerService` (in practice, `runtime_worker::ray_worker`'s
/// opaque return type) so it can implement `ErasedWorker`.
pub(super) struct RayDispatch<W>(pub(super) W);

impl<W: WorkerService> ErasedWorker for RayDispatch<W> {
    /// Calls the wrapped worker's `execute()` synchronously, before boxing
    /// the future — identical to every other `AnyWorker` arm, so O1
    /// registration still happens at call-time, not at first poll.
    fn execute(
        &self,
        context: ExecutionContext,
        channel: MpscExecutionChannel,
    ) -> Pin<Box<dyn Future<Output = Result<ExecutionReport, WorkerError>> + Send + '_>> {
        Box::pin(self.0.execute(context, channel))
    }

    fn cancel(
        &self,
        workload_id: WorkloadId,
    ) -> Pin<Box<dyn Future<Output = Result<CancelAck, WorkerError>> + Send + '_>> {
        Box::pin(self.0.cancel(workload_id))
    }

    fn pulse(
        &self,
        workload_id: WorkloadId,
    ) -> Pin<Box<dyn Future<Output = Result<ExecutionPulse, WorkerError>> + Send + '_>> {
        Box::pin(self.0.pulse(workload_id))
    }
}

#[cfg(test)]
mod tests {
    use super::super::conformance::worker_conformance_suite;

    // 5th invocation (task 3.9): `runtime_worker::new_ray_worker` itself,
    // bypassing `AnyWorker`/`ErasedWorker` entirely — proves the opaque
    // Composition-Root factory satisfies O1-O4 against a real gRPC transport
    // (`runtime-worker-test-harness::spawn_fake_ray_server`), independent of
    // `AnyWorker::Ray`'s own dispatch-and-erasure wiring (6th invocation,
    // `any.rs`). A fresh fake server is spun up per test, matching every
    // other invocation's "fresh, unshared state per test" contract.
    worker_conformance_suite!(runtime_worker::new_ray_worker(
        runtime_worker_test_harness::spawn_fake_ray_server().await
    ));
}
