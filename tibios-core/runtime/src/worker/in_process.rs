//! `InProcessWorker`: the first concrete, real `WorkerService` implementation
//! (`worker-inprocess-adapter/spec.md`) — real awaits, a real
//! `tokio::sync::mpsc`-backed `ExecutionChannel`, and the O1-O4 obligations
//! upheld under real concurrency, not simulated by a test double.

use core::future::Future;
use std::collections::BTreeMap;
use std::sync::Arc;
use std::time::Instant;

use runtime_primitives::WorkloadId;
use runtime_worker::{
    CancelAck, EndOfStream, ExecutionChannel, ExecutionContext, ExecutionEvent, ExecutionPhase,
    ExecutionPulse, ExecutionReport, MetricsSnapshot, OutputChunk, Progress, Warning, WorkerError,
    WorkerService,
};

use super::registry::{RegistrationGuard, Registry};

/// The number of `OutputChunk`s a run produces when
/// `execution_parameters["output_chunks"]` is absent or fails to parse
/// (design.md D8).
const DEFAULT_OUTPUT_CHUNKS: u64 = 3;

/// FNV-1a's standard 64-bit offset basis and prime (design.md D8: "FNV-1a
/// rolling checksum ... data-dependent, not constant").
const FNV_OFFSET_BASIS: u64 = 0xcbf2_9ce4_8422_2325;
const FNV_PRIME: u64 = 0x0000_0100_0000_01b3;

/// Folds `bytes` into `hash` via one FNV-1a pass.
fn fnv1a_step(hash: u64, bytes: &[u8]) -> u64 {
    bytes.iter().fold(hash, |acc, &byte| {
        (acc ^ u64::from(byte)).wrapping_mul(FNV_PRIME)
    })
}

/// Seeds a rolling checksum from `workload_id` — different workloads never
/// happen to produce the same output bytes for the same chunk sequence.
fn seed_checksum(workload_id: WorkloadId) -> u64 {
    fnv1a_step(FNV_OFFSET_BASIS, workload_id.to_string().as_bytes())
}

/// The number of output chunks this execution should produce, from
/// `context.execution_parameters()["output_chunks"]`, defaulting to
/// `DEFAULT_OUTPUT_CHUNKS` if the key is absent or fails to parse as `u64`.
fn output_chunk_count(execution_parameters: &BTreeMap<String, String>) -> u64 {
    execution_parameters
        .get("output_chunks")
        .and_then(|value| value.parse::<u64>().ok())
        .unwrap_or(DEFAULT_OUTPUT_CHUNKS)
}

/// The in-process, real `WorkerService` implementation
/// (`worker-inprocess-adapter/spec.md`). `pub(super)`, and never
/// re-exported — `runtime/src/worker/mod.rs`'s `in_process_worker()`
/// factory is the only way any caller obtains one (design.md D5).
pub(super) struct InProcessWorker {
    registry: Arc<Registry>,
}

impl InProcessWorker {
    pub(super) fn new() -> Self {
        Self {
            registry: Arc::new(Registry::new()),
        }
    }
}

impl WorkerService for InProcessWorker {
    /// Not an `async fn`: registration (O1) happens synchronously in this
    /// function body, before the returned future is ever polled, so a
    /// `cancel` issued right after `execute` is called — even before its
    /// future is awaited even once — is never lost racing against
    /// registration (design.md D6).
    fn execute<C>(
        &self,
        context: ExecutionContext,
        channel: C,
    ) -> impl Future<Output = Result<ExecutionReport, WorkerError>> + Send
    where
        C: ExecutionChannel,
    {
        let workload_id = context.workload_id();
        // O1 + O4, both synchronous — before any suspension point exists.
        // On the `DuplicateWorkload` path this returns `None` *without*
        // constructing a guard, so no `Drop` runs here that could
        // deregister the winning call's registration (design.md D6).
        let acquired = RegistrationGuard::try_acquire(Arc::clone(&self.registry), workload_id);
        async move {
            let guard = acquired.ok_or(WorkerError::DuplicateWorkload(workload_id))?;
            run_execution(context, channel, &guard).await
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

/// Builds the terminal `ExecutionReport` for `final_phase`, stamped with
/// `context`'s carried `trace_id` and the wall-clock duration since `start`
/// (design.md D8 step 4).
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

/// Performs one execution's real async work (design.md D8): not a sleep,
/// not a stub. Emits the full `ExecutionEvent` sequence through `channel`,
/// checking cancellation and the allocation contract's
/// `max_execution_duration` after every chunk, and returns the terminal
/// `ExecutionReport` — deregistering `guard`'s workload on every path (O2),
/// via `RegistrationGuard`'s `Drop` once this function's caller drops it.
async fn run_execution<C>(
    context: ExecutionContext,
    channel: C,
    guard: &RegistrationGuard,
) -> Result<ExecutionReport, WorkerError>
where
    C: ExecutionChannel,
{
    let start = Instant::now();
    let workload_id = context.workload_id();
    let output_chunks = output_chunk_count(context.execution_parameters());
    let max_duration = context.allocation_contract().max_execution_duration();

    channel
        .emit(ExecutionEvent::Progress(Progress {
            fraction_complete: 0.0,
            message: "received".to_string(),
        }))
        .await?;
    guard.set_phase(ExecutionPhase::Prepared);
    guard.set_phase(ExecutionPhase::Running);

    let mut checksum = seed_checksum(workload_id);
    for sequence in 0..output_chunks {
        // A genuine suspension point: `yield_now` returns `Pending` exactly
        // once before completing (`worker-inprocess-adapter/spec.md` — "the
        // execute call suspends at least once before returning").
        tokio::task::yield_now().await;

        checksum = fnv1a_step(checksum, &sequence.to_le_bytes());
        let data = checksum.to_le_bytes().to_vec();
        channel
            .emit(ExecutionEvent::OutputChunk(OutputChunk { data, sequence }))
            .await?;
        let fraction_complete = (sequence + 1) as f64 / output_chunks as f64;
        channel
            .emit(ExecutionEvent::Progress(Progress {
                fraction_complete,
                message: format!("chunk {sequence}"),
            }))
            .await?;

        if guard.is_cancelled() {
            guard.set_phase(ExecutionPhase::Cancelled);
            channel
                .emit(ExecutionEvent::Warning(Warning {
                    message: "execution cancelled".to_string(),
                }))
                .await?;
            channel
                .emit(ExecutionEvent::EndOfStream(EndOfStream))
                .await?;
            return Ok(build_report(
                &context,
                ExecutionPhase::Cancelled,
                start,
                "execution cancelled".to_string(),
            ));
        }
        if start.elapsed() >= max_duration {
            guard.set_phase(ExecutionPhase::Failed);
            channel
                .emit(ExecutionEvent::Warning(Warning {
                    message: "execution exceeded its maximum duration".to_string(),
                }))
                .await?;
            channel
                .emit(ExecutionEvent::EndOfStream(EndOfStream))
                .await?;
            return Ok(build_report(
                &context,
                ExecutionPhase::Failed,
                start,
                "execution exceeded its maximum duration".to_string(),
            ));
        }
    }

    let mut metrics = BTreeMap::new();
    metrics.insert("chunks_emitted".to_string(), output_chunks as f64);
    channel
        .emit(ExecutionEvent::MetricsSnapshot(MetricsSnapshot { metrics }))
        .await?;
    guard.set_phase(ExecutionPhase::Completed);
    channel
        .emit(ExecutionEvent::EndOfStream(EndOfStream))
        .await?;

    Ok(build_report(
        &context,
        ExecutionPhase::Completed,
        start,
        format!("completed {output_chunks} output chunks"),
    ))
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;
    use std::time::Duration;

    use runtime_allocation::AllocationContract;
    use runtime_primitives::{AllocationId, ContentHash, ObjectId, ObjectVersion, WorkloadId};
    use runtime_worker::{
        CancelAck, EndOfStream, ExecutionContext, ExecutionEvent, ExecutionPhase,
        ObservabilityContext, OutputChunk, Progress, ResolvedDependency, SecurityContext,
        WorkerCapability, WorkerError, WorkerService,
    };
    use tokio::sync::mpsc;

    use super::super::channel::MpscExecutionChannel;
    use super::InProcessWorker;

    fn context_with(
        workload_id: WorkloadId,
        allocation_contract: AllocationContract,
        execution_parameters: BTreeMap<String, String>,
    ) -> ExecutionContext {
        let dependency = ResolvedDependency::new(
            ObjectId::new(),
            ObjectVersion::initial(),
            ContentHash::new("sha256:af23"),
        );
        ExecutionContext::new(
            workload_id,
            AllocationId::new(),
            allocation_contract,
            vec![dependency],
            SecurityContext::new("tenant-1", "principal-1", vec!["scope-a".to_string()]),
            ObservabilityContext::new("trace-1", "span-1"),
            execution_parameters,
            WorkerCapability::new("chat.generate"),
        )
    }

    fn sample_context(workload_id: WorkloadId) -> ExecutionContext {
        context_with(
            workload_id,
            AllocationContract::new(Duration::from_secs(30)),
            BTreeMap::new(),
        )
    }

    fn generous_channel() -> (MpscExecutionChannel, mpsc::Receiver<ExecutionEvent>) {
        let (sender, receiver) = mpsc::channel(32);
        (MpscExecutionChannel::new(sender), receiver)
    }

    #[tokio::test]
    async fn cancel_immediately_after_execute_is_called_succeeds() {
        let worker = InProcessWorker::new();
        let workload_id = WorkloadId::new();
        let (channel, _receiver) = generous_channel();

        // Registration happens synchronously in `execute`'s own function
        // body, before the returned future is ever polled — calling
        // `execute` (without `.await`) already registers `workload_id`.
        let execute_future = worker.execute(sample_context(workload_id), channel);

        let cancel_result = worker.cancel(workload_id).await;
        assert_eq!(cancel_result, Ok(CancelAck));

        let report = execute_future
            .await
            .expect("execute must still complete after an immediate cancel");
        assert_eq!(report.final_phase, ExecutionPhase::Cancelled);
    }

    #[tokio::test]
    async fn pulse_returns_unknown_workload_after_a_successful_completion() {
        let worker = InProcessWorker::new();
        let workload_id = WorkloadId::new();
        let (channel, _receiver) = generous_channel();

        let report = worker
            .execute(sample_context(workload_id), channel)
            .await
            .expect("execute must complete successfully");
        assert_eq!(report.final_phase, ExecutionPhase::Completed);

        let pulse_result = worker.pulse(workload_id).await;
        assert!(matches!(
            pulse_result,
            Err(WorkerError::UnknownWorkload(id)) if id == workload_id
        ));
    }

    #[tokio::test]
    async fn pulse_returns_unknown_workload_after_a_cancelled_completion() {
        let worker = InProcessWorker::new();
        let workload_id = WorkloadId::new();
        let (channel, _receiver) = generous_channel();

        let execute_future = worker.execute(sample_context(workload_id), channel);
        worker
            .cancel(workload_id)
            .await
            .expect("cancel on a freshly registered workload must succeed");
        let report = execute_future
            .await
            .expect("a cancelled execution still returns a report, not an error");
        assert_eq!(report.final_phase, ExecutionPhase::Cancelled);

        let pulse_result = worker.pulse(workload_id).await;
        assert!(matches!(
            pulse_result,
            Err(WorkerError::UnknownWorkload(id)) if id == workload_id
        ));
    }

    #[tokio::test]
    async fn pulse_returns_unknown_workload_after_a_failed_completion() {
        let worker = InProcessWorker::new();
        let workload_id = WorkloadId::new();
        let (channel, _receiver) = generous_channel();
        // A zero-duration contract is breached at the first post-chunk
        // check (`elapsed() >= Duration::ZERO` is always true), forcing the
        // `Failed` path deterministically, with no timing race.
        let context = context_with(
            workload_id,
            AllocationContract::new(Duration::ZERO),
            BTreeMap::new(),
        );

        let report = worker
            .execute(context, channel)
            .await
            .expect("a duration breach still returns a report, not an error");
        assert_eq!(report.final_phase, ExecutionPhase::Failed);

        let pulse_result = worker.pulse(workload_id).await;
        assert!(matches!(
            pulse_result,
            Err(WorkerError::UnknownWorkload(id)) if id == workload_id
        ));
    }

    #[tokio::test]
    async fn cancel_and_pulse_reject_an_unregistered_workload() {
        let worker = InProcessWorker::new();
        let workload_id = WorkloadId::new();

        let cancel_result = worker.cancel(workload_id).await;
        assert!(matches!(
            cancel_result,
            Err(WorkerError::UnknownWorkload(id)) if id == workload_id
        ));

        let pulse_result = worker.pulse(workload_id).await;
        assert!(matches!(
            pulse_result,
            Err(WorkerError::UnknownWorkload(id)) if id == workload_id
        ));
    }

    #[tokio::test]
    async fn execute_rejects_a_duplicate_in_flight_workload_id_without_starting_a_second_run() {
        let worker = InProcessWorker::new();
        let workload_id = WorkloadId::new();
        let (first_channel, _first_receiver) = generous_channel();
        let (second_channel, mut second_receiver) = generous_channel();

        let first_execute = worker.execute(sample_context(workload_id), first_channel);
        let duplicate_result = worker
            .execute(sample_context(workload_id), second_channel)
            .await;
        assert!(matches!(
            duplicate_result,
            Err(WorkerError::DuplicateWorkload(id)) if id == workload_id
        ));
        // No second run started: nothing was ever emitted on the second
        // channel.
        assert!(second_receiver.try_recv().is_err());

        let report = first_execute
            .await
            .expect("the first, still-registered execution must complete normally");
        assert_eq!(report.final_phase, ExecutionPhase::Completed);
    }

    #[tokio::test]
    async fn full_event_sequence_reaches_a_real_channel_receiver() {
        let worker = InProcessWorker::new();
        let workload_id = WorkloadId::new();
        let (channel, mut receiver) = generous_channel();
        let mut execution_parameters = BTreeMap::new();
        execution_parameters.insert("output_chunks".to_string(), "3".to_string());
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
        assert_eq!(report.trace_id, "trace-1");

        let mut events = Vec::new();
        while let Ok(event) = receiver.try_recv() {
            events.push(event);
        }

        assert!(matches!(
            events.first(),
            Some(ExecutionEvent::Progress(Progress { fraction_complete, .. })) if *fraction_complete == 0.0
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

    #[tokio::test]
    async fn mid_run_cancellation_still_returns_a_cancelled_report_with_events_on_the_real_channel()
    {
        let worker = InProcessWorker::new();
        let workload_id = WorkloadId::new();
        let (channel, mut receiver) = generous_channel();

        let execute_future = worker.execute(sample_context(workload_id), channel);
        worker
            .cancel(workload_id)
            .await
            .expect("cancel on a freshly registered workload must succeed");
        let report = execute_future
            .await
            .expect("a cancelled execution still returns a report, not an error");
        assert_eq!(report.final_phase, ExecutionPhase::Cancelled);

        let mut events = Vec::new();
        while let Ok(event) = receiver.try_recv() {
            events.push(event);
        }
        assert!(matches!(
            events.last(),
            Some(ExecutionEvent::EndOfStream(EndOfStream))
        ));
    }
}
