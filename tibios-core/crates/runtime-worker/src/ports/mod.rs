//! The Worker domain's Inbound Port (`18-worker-model.md:52`;
//! `worker-inbound-port` capability): `WorkerService`, the trait a Runtime
//! calls, and `ExecutionChannel`, the trait a Worker calls back through.

pub mod execution_channel;
pub mod worker_service;

pub use execution_channel::{ChannelClosed, ExecutionChannel};
pub use worker_service::WorkerService;
