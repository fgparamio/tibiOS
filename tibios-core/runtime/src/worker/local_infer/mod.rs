//! The Local-Infer `WorkerService` adapter (`worker-local-infer-adapter/spec.md`).
//!
//! `LocalInferWorker` drives the synchronous, `std`-only `engine/` subtree
//! across the async/sync boundary via `tokio::task::spawn_blocking` +
//! `tokio::runtime::Handle::block_on` (design.md D8) — the one sanctioned
//! blocking bridge in this codebase (`05-async-concurrency.md`). Engine work
//! never runs directly on a Tokio task; cancellation and the duration
//! budget cross the blocking boundary by polling `Registry::should_stop`,
//! never by signalling (design.md D9).

use core::future::Future;
use std::collections::BTreeMap;
use std::sync::Arc;
use std::time::Instant;

use runtime_primitives::WorkloadId;
use runtime_worker::{
    CancelAck, ChannelClosed, EndOfStream, ExecutionChannel, ExecutionContext, ExecutionEvent,
    ExecutionPhase, ExecutionPulse, ExecutionReport, MetricsSnapshot, OutputChunk, Progress,
    Warning, WorkerError, WorkerService,
};
use tokio::runtime::Handle;

pub(super) mod engine;

use engine::{EngineError, GenerationRequest, SinkVerdict, TextGenerationEngine, Token, TokenSink};

use super::registry::{RegistrationGuard, Registry};

/// The number of tokens a run produces when
/// `execution_parameters["max_tokens"]` is absent or fails to parse.
const DEFAULT_MAX_TOKENS: u64 = 3;
/// The engine's per-token CPU-spin cost when
/// `execution_parameters["cpu_spin_iterations"]` is absent or fails to
/// parse — small by default so most tests run fast; individual tests that
/// need to observe the blocking boundary under real CPU pressure raise it
/// explicitly.
const DEFAULT_CPU_SPIN_ITERATIONS: u32 = 64;

fn max_tokens_from(execution_parameters: &BTreeMap<String, String>) -> u64 {
    execution_parameters
        .get("max_tokens")
        .and_then(|value| value.parse().ok())
        .unwrap_or(DEFAULT_MAX_TOKENS)
}

fn cpu_spin_iterations_from(execution_parameters: &BTreeMap<String, String>) -> u32 {
    execution_parameters
        .get("cpu_spin_iterations")
        .and_then(|value| value.parse().ok())
        .unwrap_or(DEFAULT_CPU_SPIN_ITERATIONS)
}

fn prompt_from(execution_parameters: &BTreeMap<String, String>) -> String {
    execution_parameters.get("prompt").cloned().unwrap_or_default()
}

/// The local-infer, real `WorkerService` implementation
/// (`worker-local-infer-adapter/spec.md`). `pub(super)`, never re-exported —
/// `build_local_infer_worker()` below is the only way any caller obtains
/// one.
pub(super) struct LocalInferWorker {
    registry: Arc<Registry>,
    engine: Arc<dyn TextGenerationEngine>,
}

impl LocalInferWorker {
    pub(super) fn new() -> Self {
        Self {
            registry: Arc::new(Registry::new()),
            engine: engine::default_engine(),
        }
    }

    /// Test-only injection point for a non-default engine (e.g. one that
    /// panics), so panic propagation (task 2.6) can be proven without
    /// touching `engine/`'s own subtree.
    #[cfg(test)]
    fn with_engine(engine: Arc<dyn TextGenerationEngine>) -> Self {
        Self {
            registry: Arc::new(Registry::new()),
            engine,
        }
    }
}

/// The sole way anything outside this module obtains a `LocalInferWorker`
/// value. Returns the concrete type, not `impl WorkerService`: `any.rs`'s
/// `AnyWorker::LocalInfer` variant needs to name and hold the concrete type
/// to wrap it (design.md D10) — `worker::any_worker` is what actually
/// upholds the spec's "exposed only through a factory returning `impl
/// WorkerService`" requirement for external callers.
pub(super) fn build_local_infer_worker() -> LocalInferWorker {
    LocalInferWorker::new()
}

impl WorkerService for LocalInferWorker {
    /// Not an `async fn`: O1/O4 registration happens synchronously in this
    /// function body, before the returned future is ever polled (mirrors
    /// `InProcessWorker::execute`, `in_process.rs`). `Handle::current()` is
    /// captured here, on the async side, before entering the blocking
    /// closure — never from inside it (design.md D8).
    fn execute<C>(
        &self,
        context: ExecutionContext,
        channel: C,
    ) -> impl Future<Output = Result<ExecutionReport, WorkerError>> + Send
    where
        C: ExecutionChannel,
    {
        let workload_id = context.workload_id();
        let start = Instant::now();
        let acquired = RegistrationGuard::try_acquire(Arc::clone(&self.registry), workload_id);
        let registry = Arc::clone(&self.registry);
        let engine = Arc::clone(&self.engine);
        async move {
            let guard = acquired.ok_or(WorkerError::DuplicateWorkload(workload_id))?;
            let handle = Handle::current();
            let join = tokio::task::spawn_blocking(move || {
                run_off_executor(engine.as_ref(), registry.as_ref(), &handle, start, context, channel)
            });
            let outcome = match join.await {
                Ok(outcome) => outcome,
                Err(join_error) => std::panic::resume_unwind(join_error.into_panic()),
            };
            drop(guard); // O2 — Drop alone would do this; explicit for clarity.
            outcome
        }
    }

    fn cancel(
        &self,
        workload_id: WorkloadId,
    ) -> impl Future<Output = Result<CancelAck, WorkerError>> + Send {
        let result = self.registry.cancel(workload_id);
        async move { result }
    }

    fn pulse(
        &self,
        workload_id: WorkloadId,
    ) -> impl Future<Output = Result<ExecutionPulse, WorkerError>> + Send {
        let result = self.registry.pulse(workload_id);
        async move { result }
    }
}

/// Why the blocking-side loop stopped early, recorded as sidecar state on
/// `ChannelSink` since `TokenSink::accept` can only return a `SinkVerdict`,
/// not a `Result` — the engine port stays ignorant of these three reasons
/// entirely (design.md D9).
enum StopCause {
    ChannelClosed(ChannelClosed),
    Cancelled,
    DurationExceeded,
}

/// Bridges `TokenSink` (synchronous, `std`-only, engine-side) to
/// `ExecutionChannel` (async, worker-side) via the ONE sanctioned
/// `Handle::block_on` call in this codebase (design.md D8). Checks
/// cancellation and the duration budget in the mandated order — channel
/// closed, then `should_stop`, then the deadline — after every successful
/// emit, and once before the first token (`run_off_executor` performs that
/// pre-check).
struct ChannelSink<'a, C: ExecutionChannel> {
    channel: C,
    handle: &'a Handle,
    registry: &'a Registry,
    workload_id: WorkloadId,
    deadline: Instant,
    max_tokens: u64,
    stop: Option<StopCause>,
}

impl<C: ExecutionChannel> ChannelSink<'_, C> {
    fn emit(&self, event: ExecutionEvent) -> Result<(), ChannelClosed> {
        self.handle.block_on(self.channel.emit(event))
    }

    /// The order mandated after every token, and once before the first
    /// (design.md D9; `worker-local-infer-adapter/spec.md`): channel
    /// closed, then cancellation-or-abandonment, then the duration budget.
    fn check_stop(&mut self) -> bool {
        if self.registry.should_stop(self.workload_id) {
            self.stop = Some(StopCause::Cancelled);
            return true;
        }
        if Instant::now() >= self.deadline {
            self.stop = Some(StopCause::DurationExceeded);
            return true;
        }
        false
    }
}

impl<C: ExecutionChannel> TokenSink for ChannelSink<'_, C> {
    fn accept(&mut self, token: Token) -> SinkVerdict {
        let sequence = token.sequence;
        if let Err(cause) = self.emit(ExecutionEvent::OutputChunk(OutputChunk {
            data: token.bytes,
            sequence,
        })) {
            self.stop = Some(StopCause::ChannelClosed(cause));
            return SinkVerdict::Stop;
        }
        let fraction_complete = if self.max_tokens == 0 {
            1.0
        } else {
            (sequence + 1) as f64 / self.max_tokens as f64
        };
        if let Err(cause) = self.emit(ExecutionEvent::Progress(Progress {
            fraction_complete,
            message: format!("token {sequence}"),
        })) {
            self.stop = Some(StopCause::ChannelClosed(cause));
            return SinkVerdict::Stop;
        }
        if self.check_stop() {
            return SinkVerdict::Stop;
        }
        SinkVerdict::Continue
    }
}

/// Builds the terminal `ExecutionReport` for `final_phase`, stamped with
/// `context`'s carried `trace_id` and the wall-clock duration since
/// `start`.
fn build_report(
    context: &ExecutionContext,
    final_phase: ExecutionPhase,
    start: Instant,
    summary: String,
) -> ExecutionReport {
    ExecutionReport {
        final_phase,
        duration: start.elapsed(),
        trace_id: context.observability_context().trace_id().to_string(),
        summary,
    }
}

/// Emits a `Warning` plus `EndOfStream` and returns the terminal Report for
/// a non-`Completed` outcome — the shared tail of the cancelled,
/// duration-exceeded, and engine-rejected paths.
fn terminal_report<C: ExecutionChannel>(
    sink: &ChannelSink<'_, C>,
    context: &ExecutionContext,
    start: Instant,
    phase: ExecutionPhase,
    message: String,
) -> Result<ExecutionReport, WorkerError> {
    sink.emit(ExecutionEvent::Warning(Warning {
        message: message.clone(),
    }))?;
    sink.emit(ExecutionEvent::EndOfStream(EndOfStream))?;
    Ok(build_report(context, phase, start, message))
}

/// Runs entirely on a `spawn_blocking` thread (design.md D8): the engine
/// call itself, plus every `ChannelSink::emit` — each of which crosses back
/// onto the async runtime via `handle.block_on`, the one sanctioned bridge.
/// `start` is captured on the async side, before `spawn_blocking`, so the
/// duration budget's clock starts at the true beginning of the execution,
/// not when this thread happens to get scheduled.
fn run_off_executor<C>(
    engine: &dyn TextGenerationEngine,
    registry: &Registry,
    handle: &Handle,
    start: Instant,
    context: ExecutionContext,
    channel: C,
) -> Result<ExecutionReport, WorkerError>
where
    C: ExecutionChannel,
{
    let workload_id = context.workload_id();
    let max_duration = context.allocation_contract().max_execution_duration();
    let deadline = start + max_duration;
    let max_tokens = max_tokens_from(context.execution_parameters());
    let cpu_spin_iterations = cpu_spin_iterations_from(context.execution_parameters());
    let prompt = prompt_from(context.execution_parameters());

    let mut sink = ChannelSink {
        channel,
        handle,
        registry,
        workload_id,
        deadline,
        max_tokens,
        stop: None,
    };

    sink.emit(ExecutionEvent::Progress(Progress {
        fraction_complete: 0.0,
        message: "received".to_string(),
    }))?;

    // The mandated pre-check, once before the first token (design.md D9;
    // spec scenario "A zero-duration contract fails before the first
    // token").
    if sink.check_stop() {
        let (phase, message) = match sink.stop.take() {
            Some(StopCause::Cancelled) => (ExecutionPhase::Cancelled, "execution cancelled".to_string()),
            _ => (
                ExecutionPhase::Failed,
                "execution exceeded its maximum duration".to_string(),
            ),
        };
        return terminal_report(&sink, &context, start, phase, message);
    }

    let request = GenerationRequest {
        prompt,
        max_tokens,
        cpu_spin_iterations,
    };
    let generate_result = engine.generate(&request, &mut sink);

    match sink.stop.take() {
        Some(StopCause::ChannelClosed(cause)) => Err(WorkerError::from(cause)),
        Some(StopCause::Cancelled) => {
            terminal_report(&sink, &context, start, ExecutionPhase::Cancelled, "execution cancelled".to_string())
        }
        Some(StopCause::DurationExceeded) => terminal_report(
            &sink,
            &context,
            start,
            ExecutionPhase::Failed,
            "execution exceeded its maximum duration".to_string(),
        ),
        None => match generate_result {
            Ok(summary) => {
                let mut metrics = BTreeMap::new();
                metrics.insert(
                    "tokens_produced".to_string(),
                    summary.tokens_produced as f64,
                );
                sink.emit(ExecutionEvent::MetricsSnapshot(MetricsSnapshot { metrics }))?;
                sink.emit(ExecutionEvent::EndOfStream(EndOfStream))?;
                Ok(build_report(
                    &context,
                    ExecutionPhase::Completed,
                    start,
                    format!("completed {} tokens", summary.tokens_produced),
                ))
            }
            Err(EngineError::Rejected(reason)) => terminal_report(
                &sink,
                &context,
                start,
                ExecutionPhase::Failed,
                format!("engine rejected the request: {reason}"),
            ),
        },
    }
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::sync::Arc;
    use std::time::Duration;

    use runtime_allocation::AllocationContract;
    use runtime_primitives::WorkloadId;
    use runtime_worker::{
        EndOfStream, ExecutionEvent, ExecutionPhase, OutputChunk, Progress, WorkerError,
        WorkerService,
    };

    use super::super::channel::MpscExecutionChannel;
    use super::super::conformance::{
        context_with, generous_channel, sample_context, worker_conformance_suite,
    };
    use super::engine::{EngineError, GenerationRequest, GenerationSummary, TextGenerationEngine, TokenSink};
    use super::LocalInferWorker;

    fn worker() -> LocalInferWorker {
        LocalInferWorker::new()
    }

    worker_conformance_suite!(worker());

    /// Task 2.1 (spike, gate): proves `Handle::block_on` called from inside
    /// `spawn_blocking` does not panic or deadlock on this toolchain/tokio
    /// version — the mechanism `ChannelSink::emit` depends on (design.md
    /// D8). GREEN here means the `Handle::block_on` design is safe to build
    /// on as specified; Fallback A (a bounded `std::sync::mpsc` bridge) is
    /// unnecessary.
    #[tokio::test(flavor = "multi_thread")]
    async fn handle_block_on_inside_spawn_blocking_does_not_panic_or_deadlock() {
        let handle = tokio::runtime::Handle::current();
        let result = tokio::task::spawn_blocking(move || {
            handle.block_on(async {
                tokio::task::yield_now().await;
                42
            })
        })
        .await
        .expect("spawn_blocking task must not panic");

        assert_eq!(result, 42);
    }

    #[tokio::test]
    async fn full_event_sequence_reaches_a_real_channel_receiver() {
        let worker = worker();
        let workload_id = WorkloadId::new();
        let (channel, mut receiver) = generous_channel();
        let mut execution_parameters = BTreeMap::new();
        execution_parameters.insert("max_tokens".to_string(), "3".to_string());
        execution_parameters.insert("cpu_spin_iterations".to_string(), "1".to_string());
        let context = context_with(
            workload_id,
            AllocationContract::new(Duration::from_secs(30)),
            execution_parameters,
        );

        let report = worker
            .execute(context, channel)
            .await
            .expect("execute must complete successfully");
        assert_eq!(report.final_phase, ExecutionPhase::Completed);

        let mut events = Vec::new();
        while let Ok(event) = receiver.try_recv() {
            events.push(event);
        }

        assert!(matches!(
            events.first(),
            Some(ExecutionEvent::Progress(Progress { fraction_complete, message }))
                if *fraction_complete == 0.0 && message == "received"
        ));
        let chunk_sequences: Vec<u64> = events
            .iter()
            .filter_map(|event| match event {
                ExecutionEvent::OutputChunk(OutputChunk { sequence, .. }) => Some(*sequence),
                _ => None,
            })
            .collect();
        assert_eq!(chunk_sequences, vec![0, 1, 2]);
        assert_eq!(
            events
                .iter()
                .filter(|event| matches!(event, ExecutionEvent::MetricsSnapshot(_)))
                .count(),
            1
        );
        assert!(matches!(
            events.last(),
            Some(ExecutionEvent::EndOfStream(EndOfStream))
        ));
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn a_zero_duration_contract_fails_before_the_first_token() {
        let worker = worker();
        let workload_id = WorkloadId::new();
        let (channel, mut receiver) = generous_channel();
        let context = context_with(workload_id, AllocationContract::new(Duration::ZERO), BTreeMap::new());

        let report = worker
            .execute(context, channel)
            .await
            .expect("a duration breach still returns a report, not an error");
        assert_eq!(report.final_phase, ExecutionPhase::Failed);

        let mut events = Vec::new();
        while let Ok(event) = receiver.try_recv() {
            events.push(event);
        }
        // No token was ever requested from the engine: the deadline check
        // ran once, before the first token (spec scenario "A zero-duration
        // contract fails before the first token").
        assert!(
            events.iter().all(|event| !matches!(event, ExecutionEvent::OutputChunk(_))),
            "no OutputChunk may be emitted when the deadline is already breached before the first token"
        );
        assert!(matches!(
            events.last(),
            Some(ExecutionEvent::EndOfStream(EndOfStream))
        ));
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn a_channel_closure_mid_run_is_reported_distinctly_as_channel_closed() {
        let worker = worker();
        let workload_id = WorkloadId::new();
        let (channel, mut receiver) = generous_channel();
        let mut execution_parameters = BTreeMap::new();
        execution_parameters.insert("max_tokens".to_string(), "1000".to_string());
        execution_parameters.insert("cpu_spin_iterations".to_string(), "1".to_string());
        let context = context_with(
            workload_id,
            AllocationContract::new(Duration::from_secs(30)),
            execution_parameters,
        );

        let execute_handle = tokio::spawn(async move { worker.execute(context, channel).await });
        // Let a couple of events through, proving some tokens really were
        // produced, then close the channel mid-run.
        let _ = receiver.recv().await; // "received" Progress
        let _ = receiver.recv().await; // OutputChunk(0)
        drop(receiver);

        let result = execute_handle.await.expect("execute task must not panic");
        assert!(
            matches!(result, Err(WorkerError::ChannelClosed(_))),
            "a channel closure mid-run must surface as WorkerError::ChannelClosed, not be swallowed or reclassified"
        );
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn dropping_the_execute_future_deregisters_immediately_even_though_the_blocking_task_keeps_running(
    ) {
        let worker = worker();
        let workload_id = WorkloadId::new();
        let (channel, mut receiver) = generous_channel();
        let mut execution_parameters = BTreeMap::new();
        execution_parameters.insert("max_tokens".to_string(), "1000".to_string());
        execution_parameters.insert("cpu_spin_iterations".to_string(), "50000".to_string());
        let context = context_with(
            workload_id,
            AllocationContract::new(Duration::from_secs(30)),
            execution_parameters,
        );

        let task = tokio::spawn(async move { worker.execute(context, channel).await });
        // Wait for the blocking task to actually start running (its first
        // emitted event proves `spawn_blocking`'s closure is executing)
        // before aborting — deterministic, no race on scheduling timing.
        let _ = receiver
            .recv()
            .await
            .expect("execution must emit at least one event before being aborted");

        // Abort — never calls `cancel()` — drops `execute`'s future
        // (including its `RegistrationGuard`) without the blocking task
        // ever being told to stop directly.
        task.abort();
        let _ = task.await;

        // Deregistered immediately: draining whatever the still-running
        // blocking task manages to emit before it notices the abandonment
        // (via `should_stop`'s `is_none` half) and stops shows far fewer
        // than the full 1000 tokens — proving the background task detected
        // abandonment on its own, rather than running to completion.
        let mut output_chunks = 0usize;
        while let Some(event) = receiver.recv().await {
            if matches!(event, ExecutionEvent::OutputChunk(_)) {
                output_chunks += 1;
            }
        }
        assert!(
            output_chunks < 1000,
            "abandonment must be detected well before the natural max_tokens limit is reached, got {output_chunks} chunks"
        );
    }

    struct PanickingEngine;

    impl TextGenerationEngine for PanickingEngine {
        fn generate(
            &self,
            _request: &GenerationRequest,
            _sink: &mut dyn TokenSink,
        ) -> Result<GenerationSummary, EngineError> {
            panic!("engine exploded mid-generation");
        }
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn an_engine_panic_propagates_to_executes_caller_unchanged() {
        let worker = LocalInferWorker::with_engine(Arc::new(PanickingEngine));
        let workload_id = WorkloadId::new();
        let (channel, _receiver) = generous_channel();
        let context = sample_context(workload_id);

        let join = tokio::spawn(async move { worker.execute(context, channel).await });
        let result = join.await;

        let join_error = result.expect_err("execute must panic, not return a value");
        assert!(join_error.is_panic());
        let payload = join_error.into_panic();
        let message = payload
            .downcast_ref::<&str>()
            .copied()
            .or_else(|| payload.downcast_ref::<String>().map(String::as_str));
        assert_eq!(message, Some("engine exploded mid-generation"));
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 1)]
    async fn the_executor_keeps_making_progress_while_an_execution_runs() {
        let worker = worker();
        let workload_id = WorkloadId::new();
        let (channel, _receiver) = generous_channel();
        let mut execution_parameters = BTreeMap::new();
        execution_parameters.insert("max_tokens".to_string(), "5".to_string());
        execution_parameters.insert("cpu_spin_iterations".to_string(), "5000000".to_string());
        let context = context_with(
            workload_id,
            AllocationContract::new(Duration::from_secs(30)),
            execution_parameters,
        );

        let ticks = Arc::new(AtomicU64::new(0));
        let ticker_ticks = Arc::clone(&ticks);
        let ticker = tokio::spawn(async move {
            loop {
                ticker_ticks.fetch_add(1, Ordering::Relaxed);
                tokio::task::yield_now().await;
            }
        });

        let report = worker
            .execute(context, channel)
            .await
            .expect("execute must complete");
        assert_eq!(report.final_phase, ExecutionPhase::Completed);

        ticker.abort();
        assert!(
            ticks.load(Ordering::Relaxed) > 10,
            "the single worker thread must keep servicing the ticker while the engine runs off-executor, ticked {} times",
            ticks.load(Ordering::Relaxed)
        );
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn a_bounded_channel_under_backpressure_completes_without_deadlock() {
        let workload_id = WorkloadId::new();
        let (sender, mut receiver) = tokio::sync::mpsc::channel(4);
        let channel = MpscExecutionChannel::new(sender);
        let worker = worker();
        let mut execution_parameters = BTreeMap::new();
        execution_parameters.insert("max_tokens".to_string(), "20".to_string());
        execution_parameters.insert("cpu_spin_iterations".to_string(), "1".to_string());
        let context = context_with(
            workload_id,
            AllocationContract::new(Duration::from_secs(30)),
            execution_parameters,
        );

        let execute_handle = tokio::spawn(async move { worker.execute(context, channel).await });

        let mut output_chunks = 0usize;
        while let Some(event) = receiver.recv().await {
            if matches!(event, ExecutionEvent::OutputChunk(_)) {
                output_chunks += 1;
            }
        }

        let report = execute_handle
            .await
            .expect("execute task must not panic")
            .expect("execute must complete without error");
        assert_eq!(report.final_phase, ExecutionPhase::Completed);
        assert_eq!(output_chunks, 20);
    }
}
