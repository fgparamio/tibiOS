//! `WorkerService`: the Worker domain's Inbound Port
//! (`18-worker-model.md:52`; `worker-inbound-port` capability).

use core::future::Future;

use crate::error::WorkerError;
use crate::execution::context::ExecutionContext;
use crate::execution::report::{CancelAck, ExecutionPulse, ExecutionReport};
use crate::ports::execution_channel::ExecutionChannel;
use runtime_primitives::WorkloadId;

/// The Worker domain's Inbound Port: what a Runtime calls to run, cancel,
/// and health-check an execution.
///
/// # Why `dyn`-incompatible, permanently
///
/// This trait can never be made into a trait object (`dyn WorkerService`),
/// and that is true for a reason independent of the async question: `execute`
/// is generic over `C: ExecutionChannel`, and a generic method cannot appear
/// in a trait object's vtable (the compiler would need one vtable entry per
/// possible `C`, an unbounded set). Removing every `async fn`/RPITIT from
/// this trait tomorrow would not change this; only erasing `execute`'s
/// generic parameter would, and design.md D9 chooses not to, because
/// `local-infer`'s implementation is mandated to move its `ExecutionChannel`
/// into a `spawn_blocking` closure by value — a boxed
/// `dyn ExecutionChannel` would still need to be `Send + 'static` to cross
/// that boundary, so erasing the type buys nothing there and costs an
/// allocation on every call.
///
/// # Composition-Root recipe for runtime selection
///
/// Because this trait cannot be boxed, the Composition Root selects a
/// concrete `WorkerService` implementation at startup through an enum, not
/// a trait object:
///
/// ```text
/// enum AnyWorker {
///     Local(LocalInferWorker),
///     Ray(RayWorker),
/// }
///
/// impl WorkerService for AnyWorker {
///     fn execute<C: ExecutionChannel>(&self, context: ExecutionContext, channel: C)
///         -> impl Future<Output = Result<ExecutionReport, WorkerError>> + Send
///     {
///         // The `match` runs here, synchronously, in this method's own
///         // body — never deferred into an `async move { match .. }` block.
///         match self {
///             Self::Local(worker) => Box::pin(worker.execute(context, channel)),
///             Self::Ray(worker) => Box::pin(worker.execute(context, channel)),
///         }
///     }
///     // `cancel` and `pulse` follow the same shape.
/// }
/// ```
///
/// Each method's body matches on `self` and delegates to the concrete
/// implementation's own method, exactly as any hand-written enum dispatch
/// does; nothing in `runtime-worker` changes to support this — the pattern
/// lives entirely in `runtime` (the Composition Root), where `AnyWorker` is
/// defined. `Box::pin` unifies the two branches' otherwise-distinct
/// anonymous future types; an `Either`-style wrapper would need unsafe Pin
/// projection to avoid that allocation, which the workspace denies
/// (`unsafe_code = "deny"`), so `AnyWorker` pays one allocation per call
/// instead (design.md D10).
///
/// # Hazard: a lazily-evaluated wrapper silently breaks O1
///
/// The `match` above MUST run eagerly, in `execute`'s own body, not inside
/// the future it returns. A version that instead defers dispatch —
/// `async move { match self { .. => worker.execute(context, channel).await, .. } }`
/// — looks equivalent but is not: nothing calls the concrete Worker's own
/// `execute` method until the outer future is first polled, so O1
/// registration (which happens inside that inner `execute` call, not inside
/// the future it returns) is delayed past `AnyWorker::execute`'s own return.
/// A `cancel` issued between that return and the first poll then wrongly
/// observes an unregistered workload. This is exactly why `runtime`'s
/// `AnyWorker` carries a dedicated regression test proving the eager
/// version's behavior directly, not just its own O1 conformance-suite
/// coverage (`runtime-composition-root/spec.md`; design.md D10).
///
/// # `'static`
///
/// This trait requires `Send + Sync` but deliberately **not** `'static`: the
/// port states what the contract requires, and the contract does not
/// require a `WorkerService` implementation to own no borrowed data. Whether
/// a concrete implementation's storage happens to need `'static` is a
/// wiring concern, decided where that implementation is composed, not
/// dictated by the port it implements (design.md D9 Rationale).
pub trait WorkerService: Send + Sync {
    /// Runs one execution to completion, publishing `ExecutionEvent`s
    /// through `channel` as it goes and returning the terminal
    /// `ExecutionReport` when done.
    ///
    /// Generic over `C: ExecutionChannel`, and `channel` is taken **by
    /// value** rather than by reference: `local-infer`'s implementation is
    /// mandated to move its channel into a `spawn_blocking` closure, which
    /// requires ownership, not a borrow (design.md D9).
    ///
    /// # Obligations (design.md D11)
    ///
    /// - **O1**: a Worker MUST register `context.workload_id()` before the
    ///   first suspension point in this method, so a `cancel` issued
    ///   immediately after `execute` is called is never lost racing against
    ///   registration.
    /// - **O2**: a Worker MUST deregister `context.workload_id()` before
    ///   `execute` returns, on every path — success, failure, and
    ///   cancellation alike.
    /// - **O4**: `execute` called again for a `WorkloadId` that already has
    ///   an in-flight registration MUST return
    ///   `Err(WorkerError::DuplicateWorkload)` without starting a second
    ///   execution.
    ///
    /// The port mandates the obligation, never the mechanism
    /// (`02-project-structure.md:194` — "Ports never expose implementation
    /// details"): an actor, a `Mutex`-guarded map, or — for `tibios-ray` —
    /// forwarding to the remote process's own bookkeeping are all
    /// conforming implementations.
    fn execute<C>(
        &self,
        context: ExecutionContext,
        channel: C,
    ) -> impl Future<Output = Result<ExecutionReport, WorkerError>> + Send
    where
        C: ExecutionChannel;

    /// Requests cancellation of the in-flight execution registered under
    /// `workload_id`.
    ///
    /// Idempotent while the execution stays registered: a second `cancel`
    /// call for the same still-registered `workload_id` returns another
    /// `Ok(CancelAck)`, not an error (design.md D11 Decision). `CancelAck`
    /// means "cancellation request accepted", and **never** means
    /// "execution terminated" — completion is observed only through
    /// `execute`'s own return value (mirrors `worker.proto:213-220`).
    ///
    /// Returns `Err(WorkerError::UnknownWorkload)` if `workload_id` has no
    /// in-flight registration — obligation **O3** (design.md D11); a Worker
    /// cannot distinguish "never existed" from "already completed", so both
    /// cases return the same variant.
    fn cancel(
        &self,
        workload_id: WorkloadId,
    ) -> impl Future<Output = Result<CancelAck, WorkerError>> + Send;

    /// Returns a point-in-time health check for the in-flight execution
    /// registered under `workload_id`.
    ///
    /// Returns `Err(WorkerError::UnknownWorkload)` if `workload_id` has no
    /// in-flight registration — obligation **O3** (design.md D11), the same
    /// rule `cancel` applies.
    fn pulse(
        &self,
        workload_id: WorkloadId,
    ) -> impl Future<Output = Result<ExecutionPulse, WorkerError>> + Send;
}
