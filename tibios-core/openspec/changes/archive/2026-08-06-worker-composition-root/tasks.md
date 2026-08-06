# Tasks: Worker Composition Root — First Executable Slice

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~550-700 (PR1 ~150-200, PR2 ~250-300, PR3 ~150-200) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 |
| Delivery strategy | auto-chain (project default — no need to ask) |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|---|---|---|---|
| 1 | tokio dep + guard row + `MpscExecutionChannel` + `ExecutionContext` accessors | PR 1 | base `main`; independently revertible |
| 2 | `InProcessWorker` + `Registry` + factory fn | PR 2 | base = PR 1 branch |
| 3 | `main.rs` wiring + smoke test + spec sync | PR 3 | base = PR 2 branch |

## PR 1 — Dependency, Guard, Channel, Context Accessors

- [x] 1.1 (structural, exempt) Add `tokio = { version = "1", features = ["rt-multi-thread","macros","sync"] }` to workspace `Cargo.toml`; `tokio = { workspace = true }` to `runtime/Cargo.toml`.
- [x] 1.2 (structural, exempt) `architecture_guard.rs`: edit `EXTERNAL_ALLOWED` row to `("runtime", &["tokio"])`; add `ASYNC_RUNTIME_CRATES = &["tokio"]` + `async_runtime_is_allowlisted_for_exactly_one_crate` test (owning_rows == `["runtime"]`).
- [x] 1.3 (structural, exempt) Create `runtime/src/worker/mod.rs` skeleton + `mod worker;` in `runtime/src/main.rs`.
- [x] 1.4 RED — `runtime/src/worker/channel.rs`: `#[tokio::test]`s for `MpscExecutionChannel`: emit delivers; emit after receiver-drop ⇒ `Err(ChannelClosed)`; capacity-1 backpressure pends until `recv`.
- [x] 1.5 GREEN — implement `MpscExecutionChannel` (bounded `mpsc::Sender`, `impl ExecutionChannel`) to pass 1.4.
- [x] 1.6 RED — `crates/runtime-worker/src/execution/context.rs`: tests for `observability_context()`, `allocation_contract()`, `execution_parameters()` returning carried values verbatim.
- [x] 1.7 GREEN — add the three additive accessors (approved deviation, zero new deps) to pass 1.6.
- [x] 1.8 Verify: `cargo test -p runtime -p runtime-worker`, `cargo clippy --all-targets -- -D warnings`, `cargo fmt`.

## PR 2 — In-Process Worker + Factory (base: PR 1 branch)

- [x] 2.1 RED — `runtime/src/worker/registry.rs`: `Registry::try_acquire` succeeds for a fresh id, returns `None` for an already-registered id; `RegistrationGuard` drop deregisters.
- [x] 2.2 GREEN — implement `Registry`/`Registration`/`RegistrationGuard` (`Arc<Mutex<HashMap<WorkloadId, Registration>>>` — deviation from the design's `BTreeMap`: `WorkloadId` derives `Hash + Eq`, not `Ord`, so a literal `BTreeMap<WorkloadId, _>` does not compile; `HashMap` preserves the same single-mutex-guarded-map rationale — `with_registry` helper, no `MutexGuard` crosses `.await`).
- [x] 2.3 RED — O1: call `execute(..)` without awaiting, then `cancel` immediately ⇒ `Ok(CancelAck)`.
- [x] 2.4 RED — O2: after success/failure/cancelled completion, `pulse` ⇒ `Err(UnknownWorkload)`.
- [x] 2.5 RED — O3: `cancel`/`pulse` on unregistered id ⇒ `Err(UnknownWorkload)`.
- [x] 2.6 RED — O4: second `execute` for an in-flight id ⇒ `Err(DuplicateWorkload)` immediately, no second run starts.
- [x] 2.7 GREEN — `runtime/src/worker/in_process.rs`: `pub(super) struct InProcessWorker`; synchronous `RegistrationGuard::try_acquire` before the returned future to pass 2.3-2.6.
- [x] 2.8 RED — full event sequence (Progress → per-chunk OutputChunk+Progress → MetricsSnapshot → EndOfStream) reaches a real `MpscExecutionChannel` receiver; mid-run cancellation still returns a `Cancelled` report.
- [x] 2.9 GREEN — implement `run_execution` (`tokio::task::yield_now().await` per chunk, FNV-1a checksum seeded from `workload_id`, cancellation/duration-breach check, `ExecutionReport` with `trace_id` from `observability_context()`) to pass 2.8.
- [x] 2.10 (structural, exempt — compiler-enforced) Add `pub fn in_process_worker() -> impl WorkerService` to `runtime/src/worker/mod.rs`; keep `InProcessWorker`/`Registry` `pub(super)`, never re-exported.
- [x] 2.11 Verify: `cargo test -p runtime`, `cargo clippy --all-targets -- -D warnings`, `cargo fmt`.

## PR 3 — `main.rs` Wiring + Smoke (base: PR 2 branch)

- [x] 3.1 RED — `runtime/tests/smoke.rs`: run `Command::new(env!("CARGO_BIN_EXE_runtime"))`, assert stdout contains `EndOfStream` and a `Completed` report, exit success.
- [x] 3.2 GREEN — `runtime/src/main.rs`: `#[tokio::main]`, `mpsc::channel(CHANNEL_CAPACITY)`, `MpscExecutionChannel::new(sender)` (sole `Sender`, moved in), `worker::in_process_worker()`, `tokio::spawn` drain loop — **never `tokio::join!`** (deadlocks: it keeps `execute`'s `Sender` alive so `recv()` never sees `None`), await `execute`, then await drain, print report — to pass 3.1.
- [x] 3.3 (structural, exempt) Sync `openspec/specs/runtime-composition-root/spec.md`: retire "No Public Traits In This Change", add "Runtime Wires One Real Execution End-To-End" + "Runtime Is The Sole Crate Permitted An Async Runtime Dependency" (mirror the change's own spec delta).
- [x] 3.4 Verify: `cargo run -p runtime` prints terminal report; `cargo test --workspace`; `cargo clippy --all-targets -- -D warnings`; `cargo fmt`.
