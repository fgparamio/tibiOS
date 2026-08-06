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
///         match self {
///             Self::Local(worker) => Either::Left(worker.execute(context, channel)),
///             Self::Ray(worker) => Either::Right(worker.execute(context, channel)),
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
/// defined. If a boxing/type-erasure wrapper (a hand-written `Box<dyn ..>`
/// adapter around a monomorphized `execute` call for one fixed `C`) is ever
/// needed instead, it also belongs in the Composition Root, not here — the
/// port states what the contract requires, not how a caller chooses to
/// erase it (design.md D9 Consequences).
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
