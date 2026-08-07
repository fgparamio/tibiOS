//! An in-process test harness: a real `tonic` gRPC server implementing the
//! Worker contract, served over a real loopback TCP port, that `runtime`'s
//! conformance tests point `runtime_worker::new_ray_worker` at instead of a
//! real `tibios-ray` process. Exercises the exact same network path
//! production traffic will take (`worker-grpc-client-adapter/design.md` D3).
//!
//! This crate is deliberately excluded from the workspace (see the root
//! `Cargo.toml`'s `[workspace] exclude`): it exists solely to drive
//! `runtime-worker`'s public API through a real transport in tests, and may
//! freely depend on `tokio` — something `runtime-composition-root/spec.md`
//! forbids every production crate except `runtime` itself from doing. Test
//! harness crates like this one are exempt from that rule by design.

use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use runtime_primitives::WorkloadId;
use tonic::codegen::tokio_stream::wrappers::ReceiverStream;
use tonic::transport::server::TcpIncoming;
use tonic::{Request, Response, Status};

include!(concat!(env!("OUT_DIR"), "/tibios_worker_grpc.rs"));

mod convert;

use convert::parse_workload_id;
use tibios::worker::v1 as worker_proto;
use tibios::worker::v1::worker_execution_server::{WorkerExecution, WorkerExecutionServer};

/// The number of cooperative suspension points `run_to_completion` gives the
/// executor to observe a `cancel` call before declaring the run `Completed`.
const CANCELLATION_WINDOW_STEPS: u32 = 20;

struct Registration {
    cancelled: bool,
}

/// `Mutex<HashMap<WorkloadId, Registration>>` backing O1/O3/O4 — same shape
/// `runtime`'s own `Registry` uses for `InProcessWorker`.
#[derive(Clone, Default)]
struct FakeWorkerExecution {
    registrations: Arc<Mutex<HashMap<WorkloadId, Registration>>>,
}

async fn run_to_completion(
    registrations: Arc<Mutex<HashMap<WorkloadId, Registration>>>,
    workload_id: WorkloadId,
    max_execution_duration: Duration,
    tx: tokio::sync::mpsc::Sender<Result<worker_proto::ExecutionResponse, Status>>,
) {
    let start = Instant::now();
    let final_phase = 'run: {
        for _ in 0..CANCELLATION_WINDOW_STEPS {
            tokio::task::yield_now().await;
            let cancelled = registrations
                .lock()
                .expect("registrations mutex poisoned")
                .get(&workload_id)
                .is_none_or(|registration| registration.cancelled);
            if cancelled {
                break 'run worker_proto::ExecutionPhase::Cancelled;
            }
            if start.elapsed() >= max_execution_duration {
                break 'run worker_proto::ExecutionPhase::Failed;
            }
        }
        worker_proto::ExecutionPhase::Completed
    };
    registrations
        .lock()
        .expect("registrations mutex poisoned")
        .remove(&workload_id);

    let duration = start.elapsed();
    let report = worker_proto::ExecutionResponse {
        payload: Some(worker_proto::execution_response::Payload::Report(
            worker_proto::ExecutionReport {
                final_phase: final_phase as i32,
                duration: Some(google::protobuf::Duration {
                    seconds: duration.as_secs() as i64,
                    nanos: duration.subsec_nanos() as i32,
                }),
                trace_id: "fake-server-trace".to_string(),
                summary: format!("{final_phase:?}"),
            },
        )),
    };
    let _ = tx.send(Ok(report)).await;
}

#[tonic::async_trait]
impl WorkerExecution for FakeWorkerExecution {
    type SubmitJobStream = ReceiverStream<Result<worker_proto::ExecutionResponse, Status>>;

    async fn submit_job(
        &self,
        request: Request<worker_proto::ExecutionContext>,
    ) -> Result<Response<Self::SubmitJobStream>, Status> {
        let context: runtime_worker::ExecutionContext = request
            .into_inner()
            .try_into()
            .map_err(Status::from)?;
        let workload_id = context.workload_id();
        let max_execution_duration = context.allocation_contract().max_execution_duration();

        {
            let mut registrations = self
                .registrations
                .lock()
                .expect("registrations mutex poisoned");
            if registrations.contains_key(&workload_id) {
                return Err(Status::already_exists("workload already in flight"));
            }
            registrations.insert(workload_id, Registration { cancelled: false });
        }

        let (tx, rx) = tokio::sync::mpsc::channel(4);
        tokio::spawn(run_to_completion(
            Arc::clone(&self.registrations),
            workload_id,
            max_execution_duration,
            tx,
        ));
        Ok(Response::new(ReceiverStream::new(rx)))
    }

    async fn cancel(
        &self,
        request: Request<worker_proto::CancelRequest>,
    ) -> Result<Response<worker_proto::CancelAck>, Status> {
        let workload_id = parse_workload_id(request.into_inner().workload_id)?;
        let mut registrations = self
            .registrations
            .lock()
            .expect("registrations mutex poisoned");
        match registrations.get_mut(&workload_id) {
            Some(registration) => {
                registration.cancelled = true;
                Ok(Response::new(worker_proto::CancelAck {}))
            }
            None => Err(Status::not_found("unknown workload")),
        }
    }

    async fn pulse(
        &self,
        request: Request<worker_proto::PulseRequest>,
    ) -> Result<Response<worker_proto::ExecutionPulse>, Status> {
        let workload_id = parse_workload_id(request.into_inner().workload_id)?;
        let registrations = self
            .registrations
            .lock()
            .expect("registrations mutex poisoned");
        match registrations.get(&workload_id) {
            Some(registration) => Ok(Response::new(worker_proto::ExecutionPulse {
                phase: worker_proto::ExecutionPhase::Running as i32,
                healthy: !registration.cancelled,
            })),
            None => Err(Status::not_found("unknown workload")),
        }
    }
}

/// Binds a fake `tibios-ray` gRPC server to an OS-assigned loopback port and
/// serves it on a spawned task, returning the endpoint URL
/// `runtime_worker::new_ray_worker` can connect to (e.g.
/// `http://127.0.0.1:53214`). The spawned task runs for the lifetime of the
/// calling test's Tokio runtime.
///
/// # Panics
///
/// Panics if the ephemeral port cannot be bound — treated as a test
/// environment failure, not a case callers need to handle.
pub async fn spawn_fake_ray_server() -> String {
    let incoming =
        TcpIncoming::bind("127.0.0.1:0".parse().unwrap()).expect("bind an ephemeral port");
    let addr = incoming.local_addr().expect("bound address");

    tokio::spawn(async move {
        tonic::transport::Server::builder()
            .add_service(WorkerExecutionServer::new(FakeWorkerExecution::default()))
            .serve_with_incoming(incoming)
            .await
            .expect("the fake server should serve without error");
    });

    format!("http://{addr}")
}
