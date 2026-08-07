//! `RayWorker`: the gRPC client `WorkerService` implementation that
//! forwards every call to a remote `tibios-ray` process over one shared
//! `tonic::transport::Channel` (`worker-grpc-client-adapter/design.md` D1).
//! Stays entirely private inside `runtime-worker`'s `adapters::grpc` tree —
//! same containment `convert.rs` already relies on.

use core::future::Future;

use runtime_primitives::WorkloadId;
use tonic::transport::Channel;

use super::convert::ResponseFrame;
use super::tibios::worker::v1 as worker_proto;
use super::tibios::worker::v1::worker_execution_client::WorkerExecutionClient;
use crate::error::WorkerError;
use crate::execution::context::ExecutionContext;
use crate::execution::report::{CancelAck, ExecutionPulse, ExecutionReport};
use crate::ports::execution_channel::ExecutionChannel;
use crate::ports::worker_service::WorkerService;

/// Forwards `execute`/`cancel`/`pulse` to a remote `tibios-ray` process.
/// `channel` is cloned per call — cloning a `tonic::transport::Channel` is
/// cheap (a handle over a connection pool, not the connection itself),
/// which is what lets `RayWorker` implement `WorkerService` on `&self`.
///
/// `dead_code` is allowed here (not at module scope): `runtime`'s
/// Composition Root (a later phase of `worker-grpc-client-adapter`, out of
/// scope for this slice) is `ray_worker()`'s real caller; today it is
/// exercised only by this module's own unit tests.
#[allow(dead_code)]
struct RayWorker {
    channel: Channel,
}

impl WorkerService for RayWorker {
    fn execute<C>(
        &self,
        context: ExecutionContext,
        channel: C,
    ) -> impl Future<Output = Result<ExecutionReport, WorkerError>> + Send
    where
        C: ExecutionChannel,
    {
        async move {
            let workload_id = context.workload_id();
            let wire_context: worker_proto::ExecutionContext = context.into();
            let mut client = WorkerExecutionClient::new(self.channel.clone());

            let mut stream = client
                .submit_job(wire_context)
                .await
                .map_err(|status| WorkerError::from_status(status, workload_id))?
                .into_inner();

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

    fn cancel(
        &self,
        workload_id: WorkloadId,
    ) -> impl Future<Output = Result<CancelAck, WorkerError>> + Send {
        async move {
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
#[allow(dead_code)]
pub fn ray_worker(endpoint: String) -> impl WorkerService {
    let channel = Channel::from_shared(endpoint)
        .expect("TIBIOS_RAY_ENDPOINT must be a valid URI")
        .connect_lazy();
    RayWorker { channel }
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
    use super::{Channel, RayWorker, ray_worker, worker_proto};
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
        let worker = ray_worker("http://127.0.0.1:1".to_string());
        let result = worker.execute(sample_context(), NoopChannel).await;
        assert!(matches!(result, Err(WorkerError::Transport { .. })));
    }

    #[tokio::test]
    async fn cancel_against_an_unreachable_endpoint_returns_transport_error() {
        let worker = ray_worker("http://127.0.0.1:1".to_string());
        let result = worker.cancel(WorkloadId::new()).await;
        assert!(matches!(result, Err(WorkerError::Transport { .. })));
    }

    #[tokio::test]
    async fn pulse_against_an_unreachable_endpoint_returns_transport_error() {
        let worker = ray_worker("http://127.0.0.1:1".to_string());
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
        let worker = RayWorker { channel };

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
