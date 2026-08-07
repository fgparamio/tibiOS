//! `AnyWorker`: enum dispatch over every concrete `WorkerService`
//! implementation in the workspace (`runtime-composition-root/spec.md` —
//! "AnyWorker Dispatches Eagerly To Each Concrete Worker, Never Through A
//! Lazily-Evaluated Wrapper"; design.md D10).

use core::future::Future;
use core::pin::Pin;

use runtime_primitives::WorkloadId;
use runtime_worker::{
    CancelAck, ExecutionChannel, ExecutionContext, ExecutionPulse, ExecutionReport, WorkerError,
    WorkerService,
};

use super::channel::MpscExecutionChannel;
use super::in_process::InProcessWorker;
use super::local_infer::LocalInferWorker;
use super::ray_dispatch::ErasedWorker;

/// One concrete `WorkerService` per workspace implementation. `pub(super)`
/// — never named outside `worker/` (design D10: `main.rs` selects via
/// `WorkerKind` + `any_worker()`, never this type directly).
pub(super) enum AnyWorker {
    InProcess(InProcessWorker),
    LocalInfer(LocalInferWorker),
    /// Erased via `ErasedWorker` (`worker-grpc-client-adapter/design.md`
    /// D1) rather than held as a bare `RayWorker`, because `WorkerService`
    /// itself isn't object-safe (`execute<C>` is generic).
    Ray(Box<dyn ErasedWorker>),
}

impl WorkerService for AnyWorker {
    /// The `match` runs synchronously, in this method's own body — never
    /// deferred into an `async move { match .. }` block. Each concrete
    /// Worker's `execute()` call (not the future it returns) is where O1
    /// registration happens, so the dispatch itself must be eager: only the
    /// resulting future is boxed and pinned, to unify the two branches'
    /// otherwise-distinct anonymous future types (design D10).
    fn execute<C>(
        &self,
        context: ExecutionContext,
        channel: C,
    ) -> impl Future<Output = Result<ExecutionReport, WorkerError>> + Send
    where
        C: ExecutionChannel,
    {
        match self {
            Self::InProcess(worker) => Box::pin(worker.execute(context, channel))
                as Pin<Box<dyn Future<Output = _> + Send>>,
            Self::LocalInfer(worker) => Box::pin(worker.execute(context, channel)),
            Self::Ray(worker) => {
                // `ErasedWorker::execute` is object-safe only because it is
                // monomorphized to `MpscExecutionChannel` (design D1) —
                // `runtime` never constructs any other `ExecutionChannel`
                // impl, so this downcast cannot fail in practice.
                let channel: Box<dyn core::any::Any> = Box::new(channel);
                let channel = channel
                    .downcast::<MpscExecutionChannel>()
                    .expect("runtime only ever constructs MpscExecutionChannel");
                worker.execute(context, *channel)
            }
        }
    }

    fn cancel(
        &self,
        workload_id: WorkloadId,
    ) -> impl Future<Output = Result<CancelAck, WorkerError>> + Send {
        match self {
            Self::InProcess(worker) => {
                Box::pin(worker.cancel(workload_id)) as Pin<Box<dyn Future<Output = _> + Send>>
            }
            Self::LocalInfer(worker) => Box::pin(worker.cancel(workload_id)),
            Self::Ray(worker) => worker.cancel(workload_id),
        }
    }

    fn pulse(
        &self,
        workload_id: WorkloadId,
    ) -> impl Future<Output = Result<ExecutionPulse, WorkerError>> + Send {
        match self {
            Self::InProcess(worker) => {
                Box::pin(worker.pulse(workload_id)) as Pin<Box<dyn Future<Output = _> + Send>>
            }
            Self::LocalInfer(worker) => Box::pin(worker.pulse(workload_id)),
            Self::Ray(worker) => worker.pulse(workload_id),
        }
    }
}

#[cfg(test)]
mod tests {
    use runtime_primitives::WorkloadId;
    use runtime_worker::{CancelAck, ExecutionPhase, WorkerService};

    use crate::worker::conformance::{generous_channel, sample_context, worker_conformance_suite};
    use crate::worker::{WorkerKind, any_worker};

    /// Task 3.6: written BEFORE `AnyWorker`'s dispatch was made eager. Proves
    /// the eagerness obligation directly: a cancel issued between
    /// `AnyWorker::execute`'s call and its returned future's first poll must
    /// still be accepted. A dispatch that defers the inner `match` into an
    /// `async move { … .await }` block (the version this test was first
    /// written against) fails this: nothing has registered yet, so `cancel`
    /// wrongly sees an unknown workload.
    ///
    /// Goes through `any_worker(WorkerKind::InProcess)` — the actual
    /// production entry point — rather than naming `AnyWorker` or
    /// `InProcessWorker` directly, so this test also exercises the real
    /// Composition-Root wiring, not just the enum's dispatch in isolation.
    #[tokio::test]
    async fn a_cancel_issued_before_the_dispatched_future_is_first_polled_is_accepted() {
        let worker = any_worker(WorkerKind::InProcess);
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

    mod any_in_process_conformance {
        use super::*;

        worker_conformance_suite!(any_worker(WorkerKind::InProcess));
    }

    // Under the default build, `any_worker(WorkerKind::LocalInfer)` is the
    // real dispatcher: it instantiates whatever engine `default_engine()`
    // selects, with no test seam — proving the dispatcher itself wires a
    // working `WorkerService`.
    #[cfg(not(feature = "llamacpp"))]
    mod any_local_infer_conformance {
        use super::*;

        worker_conformance_suite!(any_worker(WorkerKind::LocalInfer));
    }

    // Under `--features llamacpp`, `default_engine()` needs an
    // operator-supplied GGUF model (`TIBIOS_LOCAL_INFER_MODEL_PATH`) that
    // CI does not provide, so going through the real dispatcher here would
    // fail before any O1-O4 obligation could be observed — "does inference
    // actually complete" belongs to that engine's own Tier-3 operator-run
    // tests, not this suite. This arm keeps the harness invocation itself
    // alive (`worker-inbound-port`'s "invoked ≥3 times, none skipped") by
    // wrapping the same deterministic reference engine `LocalInferWorker`'s
    // own unit tests use, via the test-only `with_engine` seam, instead of
    // `default_engine()`.
    #[cfg(feature = "llamacpp")]
    mod any_local_infer_conformance {
        use super::*;
        use super::super::AnyWorker;
        use crate::worker::local_infer::local_infer_worker_with_deterministic_engine;

        worker_conformance_suite!(AnyWorker::LocalInfer(
            local_infer_worker_with_deterministic_engine()
        ));
    }

    // 6th invocation (task 3.9): `AnyWorker::Ray` via the real dispatcher
    // `any_worker`, exercising `RayDispatch`'s eager `execute`/`cancel`/
    // `pulse` forwarding through the object-safe `ErasedWorker` erasure —
    // distinct from `ray_dispatch.rs`'s 5th invocation, which calls
    // `runtime_worker::new_ray_worker` directly with no erasure involved.
    mod any_ray_conformance {
        use super::*;

        worker_conformance_suite!(any_worker(WorkerKind::Ray(
            runtime_worker_test_harness::spawn_fake_ray_server().await
        )));
    }
}
