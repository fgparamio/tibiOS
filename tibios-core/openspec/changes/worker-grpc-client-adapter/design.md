# Design: Worker gRPC Client Adapter

## Technical Approach

`RayWorker` is built and stays entirely private inside `runtime-worker`'s `adapters::grpc` tree (Approach 1, per exploration). The one real design gap the proposal deferred — how `runtime`'s `AnyWorker` holds an opaque `impl WorkerService` it is spec-forbidden from naming, and how the shared harness gets a live server to talk to — is resolved below by type-erasing *inside `runtime`* (never widening `runtime-worker`'s privacy) and by exercising `new_ray_worker` against a real fake `tibios-ray` server over a real TCP loopback connection, served from a workspace-excluded test harness crate (D3, D4 — superseding this design's original in-process-duplex/`test-support`-feature plan; see "Implementation Notes" for why).

`RayWorker` also owns one piece of client-side state beyond the wire adapter itself: `PendingSubmissions` (D6), the mechanism that makes `execute()`/`cancel()` satisfy the inbound port's O1/O4 obligations against a *real* network transport, where registration is inherently server-side.

## Architecture Decisions

### D1: AnyWorker::Ray holds a locally-defined `Box<dyn ErasedWorker>`, not the concrete RayWorker

**Choice**: `runtime` defines a private, object-safe `ErasedWorker` trait monomorphized to `MpscExecutionChannel` (the only `ExecutionChannel` impl `runtime` ever constructs), plus a generic `RayDispatch<W: WorkerService>(W)` blanket-implementing it. `any_worker(WorkerKind::Ray(endpoint))` calls `runtime_worker::new_ray_worker(endpoint)` (opaque `impl WorkerService`), wraps it in `RayDispatch`, boxes it, and stores `AnyWorker::Ray(Box<dyn ErasedWorker>)`.
**Alternatives considered**: (a) make `RayWorker` `pub` so `AnyWorker` can name it — breaks the spec's "never a public export any caller names directly" and needs a new guard scan; (b) `Box<dyn WorkerService>` — impossible, the trait isn't object-safe (`execute<C>` is generic).
**Rationale**: `WorkerService` can't be named as an enum field without either erasure or a pub leak; erasure defined *in `runtime`* around the one channel type it actually uses keeps `runtime-worker`'s privacy exactly as specced, and preserves eager dispatch — `ErasedWorker::execute` calls the wrapped worker's `execute()` synchronously before boxing the future, identical to every other `AnyWorker` arm today.

### D2: WorkerKind::Ray carries the endpoint as a String payload

**Choice**: `WorkerKind::Ray(String)`, not a bare variant. `main.rs` reads `TIBIOS_RAY_ENDPOINT` via `std::env::var`, fails fast (panic with a clear message) if unset, and passes it in.
**Alternatives considered**: `any_worker` reading the env var itself.
**Rationale**: Keeps `runtime-worker` and `worker/mod.rs` free of `std::env` — config-sourcing stays a `main.rs`-only concern, matching the composition-root delta's requirement text.

### D3: The fake server is a real tonic server over a real loopback TCP socket, served from a workspace-excluded harness crate — not an in-memory duplex behind a `test-support` feature

**Choice**: A new crate, `crates/runtime-worker-test-harness`, is excluded from the workspace (root `Cargo.toml`'s `[workspace] exclude`) and depends on `runtime-worker` as a normal path dependency. It generates its own client-independent copy of the Worker proto types (its own `build.rs` + `tonic-build`), implements `WorkerExecution` (`FakeWorkerExecution`) with a `Mutex<HashMap<WorkloadId, Registration>>` for O1/O3/O4 bookkeeping, binds an OS-assigned loopback port via `TcpIncoming::bind`, serves it on a spawned `tokio` task, and returns the endpoint URL (`spawn_fake_ray_server() -> String`) for `runtime_worker::new_ray_worker` to connect to. `runtime/Cargo.toml` depends on it under `[dev-dependencies]` only.
**Alternatives considered (superseding this design's original plan)**: in-memory duplex via `tokio::io::duplex` + `Endpoint::connect_with_connector`, gated behind a `#[cfg(feature = "test-support")]` module inside `runtime-worker` itself (D3/D4 as originally written) — rejected once implementation started, because it would have forced `runtime-worker` to carry a `tokio` dependency (even if feature-gated), which `runtime-composition-root/spec.md`'s `async_runtime_is_allowlisted_for_exactly_one_crate` guard forbids for every crate except `runtime`. A workspace-excluded crate sidesteps the guard entirely (it's outside `cargo_metadata`'s scope) instead of needing an exception carved into it.
**Rationale**: Real TCP over a real tonic server, driven from outside `runtime-worker`, proves the exact wire path production traffic takes (D3's original goal) without ever widening what `runtime-worker` is allowed to depend on. Workspace-exclusion is the standard escape hatch this codebase already uses for test-only crates that need dependencies production code can't have.

### D4: Cross-crate test-only exposure via a separate crate, not a Cargo feature

**Choice**: `runtime-worker` exposes only its normal, always-present Composition-Root factory, `pub fn new_ray_worker(endpoint: String) -> impl WorkerService` — no `test-support` feature, no conditionally-compiled public item. The fake server and its `spawn_fake_ray_server()` entry point live entirely in `runtime-worker-test-harness`, which calls `new_ray_worker` like any other consumer.
**Rationale**: A Cargo feature would still have required `runtime-worker` to gain a `tokio` dependency under that feature — the same problem D3 hit. Moving the fake server to its own crate means `runtime-worker` never needs to know test infrastructure exists; `runtime`'s tests pull in the harness crate the same way they'd pull in any other test-only dependency.

### D5: WorkerError::Transport classification maps by tonic::Status code, with two codes pre-empted to existing variants

**Choice**: `Status::not_found` → `WorkerError::UnknownWorkload`, `Status::already_exists` → `WorkerError::DuplicateWorkload` (reusing existing variants, not the new one). Everything else becomes `WorkerError::Transport { kind, message }`, classified `Transient` for `{Unavailable, DeadlineExceeded, Aborted, ResourceExhausted, Unknown}` and `Permanent` for `{InvalidArgument, PermissionDenied, Unauthenticated, FailedPrecondition, OutOfRange, Unimplemented, Internal, DataLoss}`.
**Rationale**: A blanket mapping risks retry-looping a request the server will never accept, or giving up on a fixable network blip — this follows gRPC's own documented code semantics (retriable vs. not) instead of guessing per code.

### D6: `PendingSubmissions` — client-side identity ownership lasts only until `SubmitJob` is acknowledged

**Choice**: `RayWorker` holds an `Arc<PendingSubmissions>` (`crates/runtime-worker/src/adapters/grpc/pending_submission.rs`), a `Mutex<HashMap<WorkloadId, PendingState>>` where `PendingState` is `Pending | CancelRequested`. `execute()` is not an `async fn`: it calls `PendingSubmissionGuard::try_acquire` synchronously, in its own function body, before ever constructing the `async move` block it returns — mirroring `InProcessWorker::execute`'s eagerness (`runtime/src/worker/in_process.rs`). `try_acquire` returns `None` (no guard, no `Drop` to race) if the workload is already pending, satisfying O4 without a network round trip. `cancel()` does the same: it synchronously calls `mark_cancel_requested` before returning its future, so a `cancel` racing a not-yet-submitted `execute` is never lost (O1). Once `SubmitJob` is acknowledged (`Ok`), the guard is dropped early, inside the `async move` block — the server is now the sole authority, and `cancel`/`pulse` forward to it unmodified, exactly as if this mechanism didn't exist.
**Alternatives considered**: (a) weaken O1's contract to mean "the workload doesn't exist until the returned future is first polled" — rejected, since that changes the inbound port's semantics for every implementation, not just `RayWorker`'s. (b) A full client-side mirror of the server's lifecycle (`Pending → Submitted → Running → Completed/Cancelled/Failed`, i.e. a second `runtime/src/worker/registry.rs`-shaped registry) — rejected as over-scoped: it would require synchronizing two independent state machines (client and server) for the entire execution lifetime, when the only obligation actually forcing client-side state is the brief window before the server has registered the workload at all.
**Rationale**: Two authorities over the same resource must never coexist. Before `SubmitJob` succeeds, only `PendingSubmissions` knows about the workload (the server doesn't yet); the fake harness's `submit_job` registers a workload into its own map synchronously, before returning its response stream, so there is no race window *after* the client's `submit_job(...).await` resolves `Ok` — the server is already authoritative by then. `WorkerError::from_status` already maps `AlreadyExists`/`NotFound` → `DuplicateWorkload`/`UnknownWorkload` (`convert.rs`), so once a workload is genuinely submitted, the server alone — via existing error-mapping — correctly handles every further duplicate/unknown-workload case with zero additional client-side state. `pulse()` is untouched: no O1-O4 obligation ever calls `pulse()` during the pending-submission window, so extending it would be designing for a hypothetical, unrequested case.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `crates/runtime-worker/build.rs` | Modify | `build_server(true)` |
| `crates/runtime-worker/src/adapters/grpc/ray_worker.rs` | Create | `RayWorker`, `new_ray_worker()` |
| `crates/runtime-worker/src/adapters/grpc/pending_submission.rs` | Create | `PendingSubmissions`, `PendingSubmissionGuard` (D6) |
| `crates/runtime-worker/src/adapters/grpc/convert.rs` | Modify | 2 new conversions |
| `crates/runtime-worker/src/error.rs` | Modify | `Transport` variant + `Classify` arm |
| `crates/runtime-worker-test-harness/` (new crate) | Create | `FakeWorkerExecution`, `spawn_fake_ray_server()` — workspace-excluded (D3, D4) |
| `Cargo.toml` (root) | Modify | `[workspace] exclude = ["crates/runtime-worker-test-harness"]` |
| `runtime/Cargo.toml` | Modify | dev-dep on `runtime-worker-test-harness` |
| `runtime/src/worker/mod.rs` | Modify | `WorkerKind::Ray(String)` + `any_worker` match arm |
| `runtime/src/worker/any.rs` | Modify | `AnyWorker::Ray(Box<dyn ErasedWorker>)` |
| `runtime/src/worker/ray_dispatch.rs` | Create | `ErasedWorker` trait + `RayDispatch<W>` |
| `runtime/src/main.rs` | Modify | reads `TIBIOS_RAY_ENDPOINT`, fails fast if unset |
| `runtime/tests/smoke.rs` | Modify | spawns the fake server, passes its endpoint via env var to the spawned binary |

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Status-code → `WorkerError` classification (D5) | table-driven test over every `tonic::Code` |
| Unit | New conversions (`convert.rs`) | round-trip + no-panic, per `worker-wire-adapter` delta |
| Unit | `PendingSubmissions`/`PendingSubmissionGuard` (D6) | direct unit tests — acquire/duplicate/drop/cancel-flag, no transport involved |
| Integration | O1-O4 for `RayWorker` and `AnyWorker::Ray` | shared harness (`worker_conformance_suite!`) against `runtime-worker-test-harness::spawn_fake_ray_server()` |
| Integration | `main.rs` end-to-end (smoke test) | spawns the fake server + the real binary, asserts a `Completed` terminal report |
| Manual | Real `tibios-ray` process | operator-run, per proposal Success Criteria (task 3.11) |

## Migration / Rollout

No migration required, but not purely additive at the Composition Root: `main.rs` now unconditionally wires `WorkerKind::Ray` and requires `TIBIOS_RAY_ENDPOINT` to be set (task 3.8 — "fail fast if unset"), replacing its previous default of `WorkerKind::LocalInfer`. Running `cargo run -p runtime` without a live `tibios-ray` endpoint no longer works; running the workspace's own tests does not need one, since `runtime-worker-test-harness` supplies a fake one.

## Open Questions

None — the harness-crate mechanism, endpoint wiring, error classification, and pending-submission bookkeeping are all resolved above.

## Implementation Notes (Post Verification)

Captured after `cargo test --workspace` and `cargo clippy --all-targets -- -D warnings` both passed clean — these are outcomes of building against this design and discovering real constraints, not new decisions:

- The fake-server harness ended up as a separate, workspace-excluded crate with a real TCP loopback server, not the in-memory-duplex/`test-support`-feature plan D3/D4 originally described (see D3, D4 above for why: `runtime-worker` cannot carry even a feature-gated `tokio` dependency under `async_runtime_is_allowlisted_for_exactly_one_crate`).
- `PendingSubmissions` (D6) exists solely to preserve the inbound port's O1 ("register before first suspension") and O4 (duplicate-in-flight rejection) obligations against a transport where registration is inherently server-side. It is not a general-purpose client-side registry.
- Its rule: the client owns workload identity only until `SubmitJob` succeeds; after that, the server is the sole authority for the workload's lifecycle. `cancel`/`pulse` forward straight to the server, unmodified, once that point is reached.
- Manual verification against a real `tibios-ray` instance (task 3.11) stays outside CI by design — it depends on an external, operator-run process this repository doesn't control.
