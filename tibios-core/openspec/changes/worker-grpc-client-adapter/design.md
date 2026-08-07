# Design: Worker gRPC Client Adapter

## Technical Approach

`RayWorker` is built and stays entirely private inside `runtime-worker`'s `adapters::grpc` tree (Approach 1, per exploration). The one real design gap the proposal deferred — how `runtime`'s `AnyWorker` holds an opaque `impl WorkerService` it is spec-forbidden from naming, and how the shared harness gets a live server to talk to — is resolved below by type-erasing *inside `runtime`* (never widening `runtime-worker`'s privacy) and by exposing a feature-gated, test-only factory that bundles an in-process fake server.

## Architecture Decisions

### D1: AnyWorker::Ray holds a locally-defined `Box<dyn ErasedWorker>`, not the concrete RayWorker

**Choice**: `runtime` defines a private, object-safe `ErasedWorker` trait monomorphized to `MpscExecutionChannel` (the only `ExecutionChannel` impl `runtime` ever constructs), plus a generic `RayDispatch<W: WorkerService>(W)` blanket-implementing it. `any_worker(WorkerKind::Ray(endpoint))` calls `runtime_worker::ray_worker(endpoint)` (opaque `impl WorkerService`), wraps it in `RayDispatch`, boxes it, and stores `AnyWorker::Ray(Box<dyn ErasedWorker>)`.
**Alternatives considered**: (a) make `RayWorker` `pub` so `AnyWorker` can name it — breaks the spec's "never a public export any caller names directly" and needs a new guard scan; (b) `Box<dyn WorkerService>` — impossible, the trait isn't object-safe (`execute<C>` is generic).
**Rationale**: `WorkerService` can't be named as an enum field without either erasure or a pub leak; erasure defined *in `runtime`* around the one channel type it actually uses keeps `runtime-worker`'s privacy exactly as specced, and preserves eager dispatch — `ErasedWorker::execute` calls the wrapped worker's `execute()` synchronously before boxing the future, identical to every other `AnyWorker` arm today.

### D2: WorkerKind::Ray carries the endpoint as a String payload

**Choice**: `WorkerKind::Ray(String)`, not a bare variant. `main.rs` reads `TIBIOS_RAY_ENDPOINT` via `std::env::var`, fails fast (panic with a clear message) if unset, and passes it in.
**Alternatives considered**: `any_worker` reading the env var itself.
**Rationale**: Keeps `runtime-worker` and `worker/mod.rs` free of `std::env` — config-sourcing stays a `main.rs`-only concern, matching the composition-root delta's requirement text.

### D3: The fake server is a real (test-support-gated) tonic server, connected via an in-memory duplex, not a socket

**Choice**: Flip `build_server(false)` → `build_server(true)` in `build.rs` (server trait generated, still fully private). A `#[cfg(feature = "test-support")]` module implements it with a `Mutex<HashSet<WorkloadId>>` for O1/O3/O4 bookkeeping and a `Mutex<HashMap<WorkloadId, oneshot::Sender<()>>>` for cancel delivery. The client channel is wired via `tokio::io::duplex` + `Endpoint::connect_with_connector`, not a real TCP port.
**Alternatives considered**: loopback TCP (port collisions, slower, non-deterministic under parallel `cargo test`); mocking at the `tower::Service` level directly (loses realistic wire round-tripping through `convert.rs`).
**Rationale**: In-memory duplex is the standard tonic testing recipe — deterministic, no port exhaustion, still exercises real (de)serialization end-to-end.

### D4: Cross-crate test-only exposure via a Cargo feature, not `#[cfg(test)]`

**Choice**: `runtime-worker` gets a `test-support` feature gating `pub fn ray_worker_with_fake_server() -> impl WorkerService` (spins up the fake server on a background task, returns a connected `RayWorker`). `runtime/Cargo.toml` enables it only under `[dev-dependencies]`.
**Rationale**: `#[cfg(test)]` items never cross a crate boundary — `runtime`'s tests can't call a `#[cfg(test)]` function in `runtime-worker`. A Cargo feature, enabled only via `[dev-dependencies]`, is the standard fix: absent from release builds, present only when `runtime` is compiled for `cargo test`.

### D5: WorkerError::Transport classification maps by tonic::Status code, with two codes pre-empted to existing variants

**Choice**: `Status::not_found` → `WorkerError::UnknownWorkload`, `Status::already_exists` → `WorkerError::DuplicateWorkload` (reusing existing variants, not the new one). Everything else becomes `WorkerError::Transport { kind, message }`, classified `Transient` for `{Unavailable, DeadlineExceeded, Aborted, ResourceExhausted, Unknown}` and `Permanent` for `{InvalidArgument, PermissionDenied, Unauthenticated, FailedPrecondition, OutOfRange, Unimplemented, Internal, DataLoss}`.
**Rationale**: A blanket mapping risks retry-looping a request the server will never accept, or giving up on a fixable network blip — this follows gRPC's own documented code semantics (retriable vs. not) instead of guessing per code.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `crates/runtime-worker/build.rs` | Modify | `build_server(true)` |
| `crates/runtime-worker/src/adapters/grpc/ray_worker.rs` | Create | `RayWorker`, `ray_worker()`, `ray_worker_with_fake_server()` (test-support) |
| `crates/runtime-worker/src/adapters/grpc/fake_server.rs` | Create | test-support-only fake `WorkerExecution` |
| `crates/runtime-worker/src/adapters/grpc/convert.rs` | Modify | 2 new conversions |
| `crates/runtime-worker/src/error.rs` | Modify | `Transport` variant + `Classify` arm |
| `crates/runtime-worker/Cargo.toml` | Modify | `[features] test-support = []` |
| `runtime/Cargo.toml` | Modify | dev-dep on `runtime-worker/test-support` |
| `runtime/src/worker/mod.rs` | Modify | `WorkerKind::Ray(String)`, env var read in `main.rs` |
| `runtime/src/worker/any.rs` | Modify | `AnyWorker::Ray(Box<dyn ErasedWorker>)` |
| `runtime/src/worker/ray_dispatch.rs` | Create | `ErasedWorker` trait + `RayDispatch<W>` |
| `runtime/src/worker/conformance.rs` | Modify | harness invoked for Ray + `AnyWorker::Ray` |

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Status-code → `WorkerError` classification (D5) | table-driven test over every `tonic::Code` |
| Unit | New conversions (`convert.rs`) | round-trip + no-panic, per `worker-wire-adapter` delta |
| Integration | O1-O4 for `RayWorker` and `AnyWorker::Ray` | shared harness against `ray_worker_with_fake_server()` |
| Manual | Real `tibios-ray` process | operator-run, per proposal Success Criteria |

## Migration / Rollout

No migration required. Additive; `main.rs` keeps defaulting to `LocalInfer`.

## Open Questions

None — the fake-server mechanism, endpoint wiring, and error classification are all resolved above.
