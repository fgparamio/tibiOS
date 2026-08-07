//! `RayWorker`: the gRPC client `WorkerService` implementation that
//! forwards every call to a remote `tibios-ray` process over one shared
//! `tonic::transport::Channel` (`worker-grpc-client-adapter/design.md` D1).
//! Stays entirely private inside `runtime-worker`'s `adapters::grpc` tree —
//! same containment `convert.rs` already relies on.

use core::future::Future;
use std::sync::Arc;

use runtime_primitives::WorkloadId;
use tonic::transport::Channel;

use super::convert::ResponseFrame;
use super::pending_submission::{PendingSubmissionGuard, PendingSubmissions};
use super::tibios::worker::v1 as worker_proto;
use super::tibios::worker::v1::worker_execution_client::WorkerExecutionClient;
use crate::error::WorkerError;
use crate::execution::context::ExecutionContext;
use crate::execution::report::{CancelAck, ExecutionPhase, ExecutionPulse, ExecutionReport};
use crate::ports::execution_channel::ExecutionChannel;
use crate::ports::worker_service::WorkerService;

/// The `ExecutionReport` `execute()` synthesizes, without ever contacting
/// the server, when `cancel()` arrives before `SubmitJob` is sent
/// (`pending_submission.rs`): the workload never existed remotely, so there
/// is nothing to ask the server about.
fn cancelled_before_submission_report(context: &ExecutionContext) -> ExecutionReport {
    ExecutionReport {
        final_phase: ExecutionPhase::Cancelled,
        duration: core::time::Duration::ZERO,
        trace_id: context.observability_context().trace_id().to_string(),
        summary: "cancelled before submission".to_string(),
    }
}

/// Forwards `execute`/`cancel`/`pulse` to a remote `tibios-ray` process.
/// `channel` is cloned per call — cloning a `tonic::transport::Channel` is
/// cheap (a handle over a connection pool, not the connection itself),
/// which is what lets `RayWorker` implement `WorkerService` on `&self`.
///
/// Stays unnamed outside this module: `runtime`'s Composition Root never
/// sees `RayWorker` itself, only the opaque `impl WorkerService` that
/// `new_ray_worker()` returns (`runtime-worker/spec.md`'s Composition-Root
/// factory exception).
struct RayWorker {
    channel: Channel,
    /// O1/O4 bookkeeping for the window between `execute()` being called
    /// and its `SubmitJob` being acknowledged — see `pending_submission.rs`.
    /// Nothing tracks a workload here past that point; the server takes
    /// over as sole authority.
    pending: Arc<PendingSubmissions>,
}

impl WorkerService for RayWorker {
    /// Not an `async fn`: `PendingSubmissionGuard::try_acquire` runs
    /// synchronously in this function body, before the returned future is
    /// ever polled, so a `cancel` issued right after `execute` is called —
    /// even before its future is awaited even once — is never lost racing
    /// against registration (mirrors `InProcessWorker::execute`,
    /// `in_process.rs`).
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
        // constructing a guard, so no `Drop` runs here that could remove
        // the winning call's entry.
        let acquired = PendingSubmissionGuard::try_acquire(Arc::clone(&self.pending), workload_id);
        async move {
            let guard = acquired.ok_or(WorkerError::DuplicateWorkload(workload_id))?;

            // The cancel-before-submit path: nothing was ever sent to the
            // server, so nothing needs to be told to stop. Skips the
            // network entirely.
            if guard.is_cancel_requested() {
                return Ok(cancelled_before_submission_report(&context));
            }

            let wire_context: worker_proto::ExecutionContext = context.into();
            let mut client = WorkerExecutionClient::new(self.channel.clone());

            let mut stream = client
                .submit_job(wire_context)
                .await
                .map_err(|status| WorkerError::from_status(status, workload_id))?
                .into_inner();
            // `SubmitJob` acknowledged: the server has now registered this
            // workload (`pending_submission.rs`'s architectural rule) and
            // is the sole authority for the rest of its lifecycle. Drop the
            // guard early rather than holding it until this whole `async`
            // block ends, so a concurrent `cancel()` stops seeing a
            // (by-then-meaningless) local entry and falls through to the
            // real server round trip immediately.
            drop(guard);

            loop {
                let response = stream
                    .message()
                    .await
                    .map_err(|status| WorkerError::from_status(status, workload_id))?
                    .ok_or_else(|| WorkerError::Transport {
                        kind: runtime_primitives::ErrorClass::Transient,
                        message: "the SubmitJob response stream ended before a terminal \
                                  ExecutionReport arrived"
                            .to_string(),
                    })?;

                match ResponseFrame::try_from(response).map_err(WorkerError::from)? {
                    ResponseFrame::Event(event) => {
                        // A closed channel never forces `execute` to abort
                        // (`ports/execution_channel.rs`) — the terminal
                        // Report still arrives on the SubmitJob stream
                        // regardless of whether the Runtime is still
                        // listening for events.
                        let _ = channel.emit(event).await;
                    }
                    ResponseFrame::Report(report) => return Ok(report),
                }
            }
        }
    }

    /// The synchronous half — `mark_cancel_requested` — runs before the
    /// returned future is polled, same eagerness reasoning as `execute`:
    /// a `cancel` racing a not-yet-submitted `execute` must never be lost
    /// to a registration race, and marking the local entry synchronously,
    /// not from inside the `async move` block, is what guarantees that.
    fn cancel(
        &self,
        workload_id: WorkloadId,
    ) -> impl Future<Output = Result<CancelAck, WorkerError>> + Send {
        let cancelled_before_submission = self.pending.mark_cancel_requested(workload_id);
        async move {
            if cancelled_before_submission {
                // Nothing was ever sent to the server for this workload
                // (`pending_submission.rs`) — nothing to ask it to stop.
                return Ok(CancelAck);
            }
            let mut client = WorkerExecutionClient::new(self.channel.clone());
            let request = worker_proto::CancelRequest {
                workload_id: Some(workload_id.into()),
            };
            client
                .cancel(request)
                .await
                .map(|response| response.into_inner().into())
                .map_err(|status| WorkerError::from_status(status, workload_id))
        }
    }

    fn pulse(
        &self,
        workload_id: WorkloadId,
    ) -> impl Future<Output = Result<ExecutionPulse, WorkerError>> + Send {
        async move {
            let mut client = WorkerExecutionClient::new(self.channel.clone());
            let request = worker_proto::PulseRequest {
                workload_id: Some(workload_id.into()),
            };
            let pulse = client
                .pulse(request)
                .await
                .map_err(|status| WorkerError::from_status(status, workload_id))?
                .into_inner();
            ExecutionPulse::try_from(pulse).map_err(WorkerError::from)
        }
    }
}

/// Builds a `RayWorker` that talks to `endpoint` (e.g.
/// `http://127.0.0.1:50051`).
///
/// Connects lazily (`Endpoint::connect_lazy`): construction never blocks on
/// network I/O and never fails because the peer is unreachable — that
/// failure surfaces from the first `execute`/`cancel`/`pulse` call instead,
/// as `Err(WorkerError::Transport)`, same as every other transport failure
/// (design.md D1).
///
/// # Panics
///
/// Panics if `endpoint` is not a syntactically valid URI. `endpoint` is
/// Composition-Root configuration (`TIBIOS_RAY_ENDPOINT`), not
/// attacker-controlled input.
pub fn new_ray_worker(endpoint: String) -> impl WorkerService {
    let channel = Channel::from_shared(endpoint)
        .expect("TIBIOS_RAY_ENDPOINT must be a valid URI")
        .connect_lazy();
    RayWorker {
        channel,
        pending: Arc::new(PendingSubmissions::default()),
    }
}

#[cfg(test)]
mod tests {
    use runtime_allocation::AllocationContract;
    use runtime_primitives::{AllocationId, WorkloadId};
    use tonic::transport::Server;
    use tonic::transport::server::TcpIncoming;

    use super::super::tibios::worker::v1::worker_execution_server::{
        WorkerExecution, WorkerExecutionServer,
    };
    use super::{Arc, Channel, PendingSubmissions, RayWorker, new_ray_worker, worker_proto};
    use crate::error::WorkerError;
    use crate::execution::context::{
        ExecutionContext, ObservabilityContext, SecurityContext, WorkerCapability,
    };
    use crate::execution::event::ExecutionEvent;
    use crate::ports::execution_channel::{ChannelClosed, ExecutionChannel};
    use crate::ports::worker_service::WorkerService;

    struct NoopChannel;

    impl ExecutionChannel for NoopChannel {
        async fn emit(&self, _event: ExecutionEvent) -> Result<(), ChannelClosed> {
            Ok(())
        }
    }

    fn sample_context() -> ExecutionContext {
        ExecutionContext::new(
            WorkloadId::new(),
            AllocationId::new(),
            AllocationContract::new(core::time::Duration::from_secs(30)),
            vec![],
            SecurityContext::new("tenant-1", "principal-1", vec![]),
            ObservabilityContext::new("trace-1", "span-1"),
            std::collections::BTreeMap::new(),
            WorkerCapability::new("chat.generate"),
        )
    }

    #[tokio::test]
    async fn execute_against_an_unreachable_endpoint_returns_transport_error() {
        let worker = new_ray_worker("http://127.0.0.1:1".to_string());
        let result = worker.execute(sample_context(), NoopChannel).await;
        assert!(matches!(result, Err(WorkerError::Transport { .. })));
    }

    #[tokio::test]
    async fn cancel_against_an_unreachable_endpoint_returns_transport_error() {
        let worker = new_ray_worker("http://127.0.0.1:1".to_string());
        let result = worker.cancel(WorkloadId::new()).await;
        assert!(matches!(result, Err(WorkerError::Transport { .. })));
    }

    #[tokio::test]
    async fn pulse_against_an_unreachable_endpoint_returns_transport_error() {
        let worker = new_ray_worker("http://127.0.0.1:1".to_string());
        let result = worker.pulse(WorkloadId::new()).await;
        assert!(matches!(result, Err(WorkerError::Transport { .. })));
    }

    /// Serves exactly one `SubmitJob` call: one `Warning` event frame,
    /// followed by the terminal `Report` frame — the two-frame shape
    /// `RayWorker::execute`'s streaming loop must route.
    struct StubServer;

    #[tonic::async_trait]
    impl WorkerExecution for StubServer {
        type SubmitJobStream =
            tonic::codegen::tokio_stream::wrappers::ReceiverStream<
                Result<worker_proto::ExecutionResponse, tonic::Status>,
            >;

        async fn submit_job(
            &self,
            _request: tonic::Request<worker_proto::ExecutionContext>,
        ) -> Result<tonic::Response<Self::SubmitJobStream>, tonic::Status> {
            let (tx, rx) = tokio::sync::mpsc::channel(2);
            let event = worker_proto::ExecutionResponse {
                payload: Some(worker_proto::execution_response::Payload::Event(
                    worker_proto::ExecutionEvent {
                        arm: Some(worker_proto::execution_event::Arm::Warning(
                            worker_proto::Warning {
                                message: "careful".to_string(),
                            },
                        )),
                    },
                )),
            };
            let report = worker_proto::ExecutionResponse {
                payload: Some(worker_proto::execution_response::Payload::Report(
                    worker_proto::ExecutionReport {
                        final_phase: worker_proto::ExecutionPhase::Completed as i32,
                        duration: Some(super::super::google::protobuf::Duration {
                            seconds: 1,
                            nanos: 0,
                        }),
                        trace_id: "trace-1".to_string(),
                        summary: "done".to_string(),
                    },
                )),
            };
            tx.send(Ok(event)).await.expect("receiver still open");
            tx.send(Ok(report)).await.expect("receiver still open");
            Ok(tonic::Response::new(
                tonic::codegen::tokio_stream::wrappers::ReceiverStream::new(rx),
            ))
        }

        async fn cancel(
            &self,
            _request: tonic::Request<worker_proto::CancelRequest>,
        ) -> Result<tonic::Response<worker_proto::CancelAck>, tonic::Status> {
            Err(tonic::Status::unimplemented("not exercised by this test"))
        }

        async fn pulse(
            &self,
            _request: tonic::Request<worker_proto::PulseRequest>,
        ) -> Result<tonic::Response<worker_proto::ExecutionPulse>, tonic::Status> {
            Err(tonic::Status::unimplemented("not exercised by this test"))
        }
    }

    struct RecordingChannel(tokio::sync::mpsc::UnboundedSender<ExecutionEvent>);

    impl ExecutionChannel for RecordingChannel {
        async fn emit(&self, event: ExecutionEvent) -> Result<(), ChannelClosed> {
            self.0.send(event).map_err(|_| ChannelClosed)
        }
    }

    #[tokio::test]
    async fn execute_routes_event_frames_to_emit_and_returns_on_the_report_frame() {
        let incoming =
            TcpIncoming::bind("127.0.0.1:0".parse().unwrap()).expect("bind an ephemeral port");
        let addr = incoming.local_addr().expect("bound address");
        tokio::spawn(async move {
            Server::builder()
                .add_service(WorkerExecutionServer::new(StubServer))
                .serve_with_incoming(incoming)
                .await
                .expect("stub server should serve without error");
        });

        let channel = Channel::from_shared(format!("http://{addr}"))
            .expect("valid URI")
            .connect()
            .await
            .expect("connect to the stub server");
        let worker = RayWorker {
            channel,
            pending: Arc::new(PendingSubmissions::default()),
        };

        let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel();
        let result = worker
            .execute(sample_context(), RecordingChannel(tx))
            .await;

        let report = result.expect("the report frame should end the stream successfully");
        assert_eq!(report.summary, "done");

        let received = rx.try_recv().expect("the event frame should have been emitted");
        assert!(matches!(received, ExecutionEvent::Warning(_)));
        assert!(
            rx.try_recv().is_err(),
            "only the one event frame preceded the report frame"
        );
    }
}
