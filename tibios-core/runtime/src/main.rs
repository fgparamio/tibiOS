//! `runtime` — the workspace's binary crate and Composition Root, per
//! `02-project-structure.md`'s "Composition Root" section.
//!
//! Concrete implementations are assembled only once, here. The `runtime`
//! crate creates concrete services, injects implementations, and wires the
//! Runtime graph; no other crate performs dependency composition. It is the
//! sole deliberate exception to the workspace's narrow-dependency rule: it
//! may depend on every other crate, and no crate may depend on it.
//!
//! This binding wires one real, end-to-end execution
//! (`runtime-composition-root/spec.md` — "Runtime Wires One Real Execution
//! End-To-End"): a concrete `ExecutionChannel`, a `WorkerService`
//! implementation obtained exclusively through the `worker::any_worker`
//! factory (only its `impl WorkerService` return type crosses into this
//! file — no concrete worker or transport type is ever named here; nor is
//! any engine type, since `any_worker` alone selects between them via
//! `WorkerKind`), one submitted execution, its drained events, and the
//! terminal `ExecutionReport`. Hand-wiring `runtime-allocation`,
//! `runtime-object`, or `runtime-scheduler` stays out of scope for this
//! change.

mod worker;

use std::collections::BTreeMap;
use std::time::Duration;

use runtime_allocation::AllocationContract;
use runtime_primitives::{AllocationId, ContentHash, ObjectId, ObjectVersion, WorkloadId};
use runtime_worker::{
    ExecutionContext, ObservabilityContext, ResolvedDependency, SecurityContext, WorkerCapability,
    WorkerService,
};
use tokio::sync::mpsc;
use worker::{MpscExecutionChannel, WorkerKind};

/// The bounded `mpsc` channel's capacity (design.md D8: "9 events against a
/// capacity-4 channel ⇒ `emit` genuinely blocks on the receiver, so the
/// wiring is proven by backpressure, not by assertion").
const CHANNEL_CAPACITY: usize = 4;

/// Builds one demonstration `ExecutionContext` from plain values — no
/// transport, no async runtime required to construct it.
fn demo_context() -> ExecutionContext {
    let dependency = ResolvedDependency::new(
        ObjectId::new(),
        ObjectVersion::initial(),
        ContentHash::new("sha256:demo"),
    );
    ExecutionContext::new(
        WorkloadId::new(),
        AllocationId::new(),
        AllocationContract::new(Duration::from_secs(30)),
        vec![dependency],
        SecurityContext::new(
            "tenant-demo",
            "principal-demo",
            vec!["scope-demo".to_string()],
        ),
        ObservabilityContext::new("trace-demo", "span-demo"),
        BTreeMap::new(),
        WorkerCapability::new("chat.generate"),
    )
}

// Drain concurrently with `tokio::spawn`, never `tokio::join!` (design.md
// D9): `join!` keeps `execute`'s future — and the `Sender` it owns — alive
// until both branches resolve, so the channel never closes, `recv()` never
// yields `None`, and the drain branch deadlocks forever. Spawning the
// drain and awaiting `execute` on the main task drops the sole `Sender` at
// a well-defined point instead.
#[tokio::main]
async fn main() {
    let (sender, mut receiver) = mpsc::channel(CHANNEL_CAPACITY);
    let channel = MpscExecutionChannel::new(sender); // the ONLY Sender, moved in
    let worker = worker::any_worker(WorkerKind::LocalInfer);

    let drain = tokio::spawn(async move {
        let mut seen = 0usize;
        while let Some(event) = receiver.recv().await {
            println!("event: {event:?}");
            seen += 1;
        }
        seen
    });

    let report = worker.execute(demo_context(), channel).await; // channel dropped here
    let seen = drain.await.expect("drain task must not panic");
    println!("report: {report:?} ({seen} events)");
}
