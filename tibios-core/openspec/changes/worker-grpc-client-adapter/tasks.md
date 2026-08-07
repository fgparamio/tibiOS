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

- [ ] 3.1 `Cargo.toml` (runtime-worker): add `[features] test-support = []`
- [ ] 3.2 GREEN: `fake_server.rs` — `WorkerExecution` impl with `Mutex<HashSet<WorkloadId>>` (dedup/unknown) + cancel delivery, `#[cfg(feature = "test-support")]`
- [ ] 3.3 GREEN: `ray_worker_with_fake_server()` — duplex-connected `RayWorker` + spawned fake server, `#[cfg(feature = "test-support")]` `pub`
- [ ] 3.4 `runtime/Cargo.toml`: `[dev-dependencies]` `runtime-worker` with `test-support`
- [ ] 3.5 `runtime/src/worker/ray_dispatch.rs`: `ErasedWorker` trait + `RayDispatch<W>` blanket impl (D1)
- [ ] 3.6 `runtime/src/worker/mod.rs`: `WorkerKind::Ray(String)` + `any_worker` match arm
- [ ] 3.7 `runtime/src/worker/any.rs`: `AnyWorker::Ray(Box<dyn ErasedWorker>)` + 3 match arms
- [ ] 3.8 `runtime/src/main.rs`: read `TIBIOS_RAY_ENDPOINT`, fail fast if unset
- [ ] 3.9 `runtime/src/worker/conformance.rs`: invoke `worker_conformance_suite!` for `RayWorker` and `AnyWorker::Ray` (5th/6th invocation)
- [ ] 3.10 Verify: `cargo test --workspace` and `cargo clippy --all-targets -- -D warnings` clean
- [ ] 3.11 Manual (not CI): `main.rs` completes one execution against a real `tibios-ray` instance
