//! Integration test (deliberately outside `#[cfg(test)]`, so it can only
//! reach `runtime-worker`'s public API): proves `WorkerService` and
//! `ExecutionChannel` can be driven end-to-end with zero runtime, zero
//! transport, and zero I/O — the `worker-inbound-port` capability's own
//! testability claim. Every fixture below depends only on `std` and `core`
//! — no async-runtime crate and no trait-macro helper crate of any kind.

use std::collections::{BTreeMap, HashSet};
use std::sync::Mutex;
use std::sync::mpsc::{self, Receiver, Sender};

use core::future::Future;
use core::pin::pin;
use core::task::{Context, Poll, Waker};

use runtime_allocation::AllocationContract;
use runtime_primitives::{AllocationId, ContentHash, ObjectId, ObjectVersion, WorkloadId};
use runtime_worker::{
    CancelAck, ChannelClosed, EndOfStream, ExecutionChannel, ExecutionContext, ExecutionEvent,
    ExecutionPhase, ExecutionPulse, ExecutionReport, ObservabilityContext, Progress,
    ResolvedDependency, SecurityContext, WorkerError, WorkerService,
};

/// Drives any `Future` to completion with a no-op waker, under a bounded
/// poll count. Every fixture in this file is expected to make progress on
/// every poll (no real I/O ever pends here); exceeding the cap means a
/// fixture is genuinely stuck, so this panics naming the cause instead of
/// hanging the test suite.
fn poll_to_completion<F: Future>(future: F) -> F::Output {
    let mut future = pin!(future);
    let waker = Waker::noop();
    let mut context = Context::from_waker(waker);
    for _ in 0..1_000 {
        if let Poll::Ready(output) = future.as_mut().poll(&mut context) {
            return output;
        }
    }
    panic!("the fake channel must never pend");
}

/// An in-memory `ExecutionChannel` over `std::sync::mpsc`: `emit` always
/// returns `Ready(Ok(()))` immediately, because an unbounded `std` sender
/// never blocks — the fake never pends.
struct RecordingChannel(Sender<ExecutionEvent>);

impl ExecutionChannel for RecordingChannel {
    async fn emit(&self, event: ExecutionEvent) -> Result<(), ChannelClosed> {
        // A dropped `Receiver` would make `send` fail; this fake channel
        // has no need to report that as `ChannelClosed` itself, since no
        // test here drops the receiver early. Always `Ok`, per this type's
        // own contract.
        let _ = self.0.send(event);
        Ok(())
    }
}

/// A `Future` that returns `Poll::Pending` exactly once, then completes —
/// distinct from `RecordingChannel`'s always-`Ready` `emit`, which cannot by
/// itself demonstrate a live in-flight registration window (design.md D11).
struct YieldOnce {
    yielded: bool,
}

impl YieldOnce {
    fn new() -> Self {
        Self { yielded: false }
    }
}

impl Future for YieldOnce {
    type Output = ();

    fn poll(mut self: core::pin::Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<()> {
        if self.yielded {
            Poll::Ready(())
        } else {
            self.yielded = true;
            cx.waker().wake_by_ref();
            Poll::Pending
        }
    }
}

/// A test-only `WorkerService`: "echoes" one `Progress` event and an
/// `EndOfStream` through whatever `ExecutionChannel` it is given, then
/// returns a `Completed` `ExecutionReport`. Its `registry` is the entire
/// conformance surface under test here — O1 (register before the first
/// suspension point), O2 (deregister on every path), O3
/// (`cancel`/`pulse` on an unregistered id), and O4 (reject a duplicate
/// `execute`) all pivot on it.
struct EchoWorker {
    registry: Mutex<HashSet<WorkloadId>>,
    /// When `true`, `execute` awaits one `YieldOnce` right after
    /// registering, so a test can observe the in-flight registration
    /// window from outside (4.13, 4.14).
    yield_once: bool,
}

impl EchoWorker {
    fn new() -> Self {
        Self {
            registry: Mutex::new(HashSet::new()),
            yield_once: false,
        }
    }

    fn with_yield_once() -> Self {
        Self {
            registry: Mutex::new(HashSet::new()),
            yield_once: true,
        }
    }
}

impl WorkerService for EchoWorker {
    async fn execute<C>(
        &self,
        context: ExecutionContext,
        channel: C,
    ) -> Result<ExecutionReport, WorkerError>
    where
        C: ExecutionChannel,
    {
        let workload_id = context.workload_id();

        // O1: register before the first suspension point — nothing above
        // this line ever awaits.
        {
            let mut registry = self.registry.lock().expect("registry mutex poisoned");
            if !registry.insert(workload_id) {
                return Err(WorkerError::DuplicateWorkload(workload_id));
            }
        }

        // The fallible body is wrapped so every exit path — success or a
        // failed `emit` — flows through the single deregistration below
        // (O2), rather than needing a deregister call at each early return.
        // `async move`, not `async` — `channel` (`C: Send + 'static`, not
        // `Sync`) must be captured by value, not by the shared reference an
        // implicit borrow would take, or the resulting future would need
        // `C: Sync` to be `Send` (design.md D9).
        let outcome = async move {
            if self.yield_once {
                YieldOnce::new().await;
            }
            channel
                .emit(ExecutionEvent::Progress(Progress {
                    fraction_complete: 1.0,
                    message: "echo".to_string(),
                }))
                .await?;
            channel
                .emit(ExecutionEvent::EndOfStream(EndOfStream))
                .await?;
            Ok(ExecutionReport {
                final_phase: ExecutionPhase::Completed,
                duration: core::time::Duration::from_secs(0),
                trace_id: context.workload_id().to_string(),
                summary: "echoed".to_string(),
            })
        }
        .await;

        // O2: deregister before returning, on every path.
        self.registry
            .lock()
            .expect("registry mutex poisoned")
            .remove(&workload_id);

        outcome
    }

    async fn cancel(&self, workload_id: WorkloadId) -> Result<CancelAck, WorkerError> {
        let registry = self.registry.lock().expect("registry mutex poisoned");
        if registry.contains(&workload_id) {
            // Idempotent while registered (design.md D11 Decision): every
            // call while still registered returns another `CancelAck`.
            Ok(CancelAck)
        } else {
            // O3: unregistered id at `cancel` MUST return `UnknownWorkload`.
            Err(WorkerError::UnknownWorkload(workload_id))
        }
    }

    async fn pulse(&self, workload_id: WorkloadId) -> Result<ExecutionPulse, WorkerError> {
        let registry = self.registry.lock().expect("registry mutex poisoned");
        if registry.contains(&workload_id) {
            Ok(ExecutionPulse {
                phase: ExecutionPhase::Running,
                healthy: true,
            })
        } else {
            // O3: unregistered id at `pulse` MUST return `UnknownWorkload`.
            Err(WorkerError::UnknownWorkload(workload_id))
        }
    }
}

/// Builds an `ExecutionContext` by hand — plain values only, no async
/// runtime, no transport, no private adapter module.
fn sample_context(workload_id: WorkloadId) -> ExecutionContext {
    let dependency = ResolvedDependency::new(
        ObjectId::new(),
        ObjectVersion::initial(),
        ContentHash::new("sha256:af23"),
    );
    let mut execution_parameters = BTreeMap::new();
    execution_parameters.insert("temperature".to_string(), "0.7".to_string());

    ExecutionContext::new(
        workload_id,
        AllocationId::new(),
        AllocationContract::new(core::time::Duration::from_secs(30)),
        vec![dependency],
        SecurityContext::new("tenant-1", "principal-1", vec!["scope-a".to_string()]),
        ObservabilityContext::new("trace-1", "span-1"),
        execution_parameters,
    )
}

fn recording_channel() -> (RecordingChannel, Receiver<ExecutionEvent>) {
    let (sender, receiver) = mpsc::channel();
    (RecordingChannel(sender), receiver)
}

/// Satisfies `worker-inbound-port/spec.md`'s "execute runs against a fake
/// context and an in-memory channel with zero runtime, zero transport, zero
/// I/O" scenario.
#[test]
fn execute_runs_to_completion_with_fake_context_and_in_memory_channel() {
    let worker = EchoWorker::new();
    let workload_id = WorkloadId::new();
    let context = sample_context(workload_id);
    let (channel, receiver) = recording_channel();

    let report = poll_to_completion(worker.execute(context, channel))
        .expect("execute must complete successfully against a fake context and channel");

    assert_eq!(report.final_phase, ExecutionPhase::Completed);

    let events: Vec<ExecutionEvent> = receiver.try_iter().collect();
    assert_eq!(
        events,
        vec![
            ExecutionEvent::Progress(Progress {
                fraction_complete: 1.0,
                message: "echo".to_string(),
            }),
            ExecutionEvent::EndOfStream(EndOfStream),
        ]
    );
}

/// The concrete, observable assertion for O2 (design.md D9 Consequences:
/// "O1/O2 are observable from outside the Worker... That turns D11's
/// obligations into assertions rather than documentation").
#[test]
fn pulse_returns_unknown_workload_after_execute_completes() {
    let worker = EchoWorker::new();
    let workload_id = WorkloadId::new();
    let context = sample_context(workload_id);
    let (channel, _receiver) = recording_channel();

    poll_to_completion(worker.execute(context, channel))
        .expect("execute must complete successfully");

    let result = poll_to_completion(worker.pulse(workload_id));
    assert!(matches!(result, Err(WorkerError::UnknownWorkload(id)) if id == workload_id));
}

/// O3, using only fakes and test doubles: a `WorkloadId` this `EchoWorker`
/// never registered.
#[test]
fn cancel_and_pulse_reject_an_unregistered_workload() {
    let worker = EchoWorker::new();
    let workload_id = WorkloadId::new();

    let cancel_result = poll_to_completion(worker.cancel(workload_id));
    assert!(matches!(cancel_result, Err(WorkerError::UnknownWorkload(id)) if id == workload_id));

    let pulse_result = poll_to_completion(worker.pulse(workload_id));
    assert!(matches!(pulse_result, Err(WorkerError::UnknownWorkload(id)) if id == workload_id));
}

/// O1 + cancel idempotency (design.md D11 Decision): polls `execute` once
/// to land inside its registration window (the `YieldOnce` fixture, not
/// `RecordingChannel`'s always-`Ready` `emit`, is what makes that window
/// observable), calls `cancel` twice from within that window, then resumes
/// polling to completion.
#[test]
fn cancel_is_idempotent_while_registered() {
    let worker = EchoWorker::with_yield_once();
    let workload_id = WorkloadId::new();
    let context = sample_context(workload_id);
    let (channel, _receiver) = recording_channel();

    let waker = Waker::noop();
    let mut poll_context = Context::from_waker(waker);
    let mut execute_future = pin!(worker.execute(context, channel));

    let first_poll = execute_future.as_mut().poll(&mut poll_context);
    assert!(
        matches!(first_poll, Poll::Pending),
        "the yielding fixture must still be pending after exactly one poll"
    );

    let first_cancel = poll_to_completion(worker.cancel(workload_id));
    assert_eq!(first_cancel, Ok(CancelAck));
    let second_cancel = poll_to_completion(worker.cancel(workload_id));
    assert_eq!(second_cancel, Ok(CancelAck));

    let report = loop {
        match execute_future.as_mut().poll(&mut poll_context) {
            Poll::Ready(output) => break output,
            Poll::Pending => continue,
        }
    }
    .expect("execute must still complete successfully after being cancelled mid-flight");
    assert_eq!(report.final_phase, ExecutionPhase::Completed);
}

/// O4, using the same yielding-fixture technique as
/// `cancel_is_idempotent_while_registered`: a second `execute` call for a
/// `WorkloadId` that is still mid-flight MUST be rejected without starting
/// a second execution.
#[test]
fn execute_rejects_a_duplicate_in_flight_workload_id() {
    let worker = EchoWorker::with_yield_once();
    let workload_id = WorkloadId::new();
    let (first_channel, _first_receiver) = recording_channel();
    let (second_channel, _second_receiver) = recording_channel();

    let waker = Waker::noop();
    let mut poll_context = Context::from_waker(waker);
    let mut first_execute = pin!(worker.execute(sample_context(workload_id), first_channel));

    let first_poll = first_execute.as_mut().poll(&mut poll_context);
    assert!(
        matches!(first_poll, Poll::Pending),
        "the yielding fixture must still be pending after exactly one poll"
    );

    let duplicate_result =
        poll_to_completion(worker.execute(sample_context(workload_id), second_channel));
    assert!(matches!(
        duplicate_result,
        Err(WorkerError::DuplicateWorkload(id)) if id == workload_id
    ));

    let report = loop {
        match first_execute.as_mut().poll(&mut poll_context) {
            Poll::Ready(output) => break output,
            Poll::Pending => continue,
        }
    }
    .expect("the first, still-registered execution must complete normally");
    assert_eq!(report.final_phase, ExecutionPhase::Completed);
}
