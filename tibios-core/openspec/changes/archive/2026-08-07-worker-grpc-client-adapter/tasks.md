# Tasks: Worker gRPC Client Adapter

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 650-750 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

```text
Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High
```

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Wire conversions + `WorkerError::Transport` + classification | PR 1 | base: `main`; ~150-200 lines; no `RayWorker` yet |
| 2 | `RayWorker` + production factory (`ray_worker`) | PR 2 | base: `main` (PR 1 merged first); ~250-300 lines |
| 3 | Fake server, `test-support` feature, harness wiring, Composition Root | PR 3 | base: `main` (PR 2 merged first); ~300-350 lines |

Chain strategy confirmed: **stacked-to-main** — each PR merges to `main` in order before the next starts. Confirmed safe: `tibios-ray`'s parallel work (implementing its own Ray worker server, not touching the already-frozen `proto/tibios/worker/v1/worker.proto`) lives in a separate repository/worktree — no branch overlap with `tibios-core`. Task 3.11 (manual verification against a real `tibios-ray`) is the only coupling point and is explicitly non-blocking for merge.

## Phase 1: Wire Boundary + Error Classification (PR 1)

- [x] 1.1 RED: `convert.rs` test — domain `ExecutionContext` → wire round-trips every field
- [x] 1.2 GREEN: `From<ExecutionContext> for proto::ExecutionContext` in `convert.rs`
- [x] 1.3 RED: `convert.rs` test — wire `CancelAck` → domain always succeeds
- [x] 1.4 GREEN: `From<proto::CancelAck> for CancelAck` in `convert.rs`
- [x] 1.5 RED: `error.rs` test — `NotFound`/`AlreadyExists` map to `UnknownWorkload`/`DuplicateWorkload`; every other `tonic::Code` classifies per D5's Transient/Permanent table
- [x] 1.6 GREEN: add `WorkerError::Transport { kind, message }` + `Classify` arm + `TryFrom<tonic::Status>` mapping in `error.rs`

## Phase 2: RayWorker (PR 2)

- [x] 2.1 `build.rs`: `build_server(true)`
- [x] 2.2 RED (in-crate): `ray_worker.rs` test — `execute`/`cancel`/`pulse` against an unreachable endpoint return `Err(WorkerError::Transport)`, no `tonic::` type in the error
- [x] 2.3 GREEN: `RayWorker` struct + `WorkerService` impl in `ray_worker.rs`, using `convert.rs`'s conversions exclusively
- [x] 2.4 GREEN: `pub fn ray_worker(endpoint: String) -> impl WorkerService` factory
- [x] 2.5 RED: test — `SubmitJob` response frames route events to `emit`, report frame ends the stream (mock `tower::Service` or minimal stub server)
- [x] 2.6 GREEN: streaming response loop in `RayWorker::execute`

## Phase 3: Fake Server, Harness, Composition Root (PR 3)

Tasks 3.1-3.4 were reworked during implementation (design.md D3, D4): the originally-planned in-process-duplex fake server behind a `runtime-worker` `test-support` feature was replaced by a separate, workspace-excluded `runtime-worker-test-harness` crate serving a real fake `tibios-ray` over a real TCP loopback socket — `runtime-worker` cannot carry even a feature-gated `tokio` dependency under `async_runtime_is_allowlisted_for_exactly_one_crate`.

- [x] 3.1 (reworked) Create `crates/runtime-worker-test-harness`, excluded from the workspace, depending on `runtime-worker`
- [x] 3.2 (reworked) `FakeWorkerExecution` in the harness crate — `WorkerExecution` impl with `Mutex<HashMap<WorkloadId, Registration>>` (dedup/unknown) + cancel delivery; `spawn_fake_ray_server() -> String` binds a loopback TCP port and returns its endpoint
- [x] 3.3 (reworked) Delete the no-longer-needed `test-support` feature and `ray_worker_with_fake_server()` from `runtime-worker`; `new_ray_worker()` stays the only public factory
- [x] 3.4 (reworked) `runtime/Cargo.toml`: `[dev-dependencies]` on `runtime-worker-test-harness`
- [x] 3.5 `runtime/src/worker/ray_dispatch.rs`: `ErasedWorker` trait + `RayDispatch<W>` blanket impl (D1)
- [x] 3.6 `runtime/src/worker/mod.rs`: `WorkerKind::Ray(String)` + `any_worker` match arm
- [x] 3.7 `runtime/src/worker/any.rs`: `AnyWorker::Ray(Box<dyn ErasedWorker>)` + 3 match arms
- [x] 3.8 `runtime/src/main.rs`: read `TIBIOS_RAY_ENDPOINT`, fail fast if unset
- [x] 3.9 `runtime/src/worker/ray_dispatch.rs` + `runtime/src/worker/any.rs`: invoke `worker_conformance_suite!` for `RayWorker` and `AnyWorker::Ray` (5th/6th invocation) — surfaced an O1/O4 gap in `RayWorker`, fixed via `PendingSubmissions` (design.md D6, not originally in this task list)
- [x] 3.10 Verify: `cargo test --workspace` and `cargo clippy --all-targets -- -D warnings` clean — also required updating `runtime/tests/smoke.rs` (fake-server deadlock via a blocking call on a current-thread `#[tokio::test]`, and a stale `EndOfStream` assertion left over from the pre-Ray `LocalInfer` wiring)
- [ ] 3.11 Manual (not CI): `main.rs` completes one execution against a real `tibios-ray` instance
