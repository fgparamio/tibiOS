# Proposal: Worker gRPC Client Adapter

## Intent

`worker-grpc-adapter` compiled the frozen wire contract and wrote its conversions but deliberately deferred "gRPC client instantiation and lifecycle" (`tibios-core` is the client, `tibios-ray` the server). Two concrete Workers now run in-process; nothing yet lets `runtime` talk to a real `tibios-ray` over the network. This change is that third, network-backed `WorkerService` implementation — `RayWorker`, a name the codebase already sketches in `ports/worker_service.rs`'s own doc comment.

**Outcome**: after this change, the Runtime owns three interchangeable `WorkerService` implementations — `InProcessWorker` (reference/test), `LocalInferWorker` (local execution), `RayWorker` (remote execution over gRPC) — closing the Worker domain's architectural base. What follows this change is capability growth (more engines, more model families, scheduling, admission), not further port/adapter architecture.

## Scope

### In Scope
- `RayWorker`: a `WorkerService` implementation that calls `tibios-ray` over gRPC (`SubmitJob`/`Cancel`/`Pulse`), exposed via a factory returning `impl WorkerService` — no concrete type crosses the boundary that exposes it.
- Missing wire conversions: domain `ExecutionContext` → wire (for `SubmitJob`), wire `CancelAck` → domain.
- A new `WorkerError` variant for transport-level failures, classified per `04-error-handling.md`. Carries a domain-safe representation (status kind + message as plain data), never `tonic::Status` itself — `worker-inbound-port/spec.md:43` already names `WorkerError` among the types that MUST NOT surface a `tonic::` path.
- `WorkerKind::Ray` + `any_worker` wiring in the Composition Root, with an endpoint source (env var, minimal — no full config system).
- The shared O1-O4 conformance harness invoked against `RayWorker` and `AnyWorker::Ray(..)`, against an in-process fake `tibios.worker.v1.WorkerExecution` server (no live `tibios-ray` process in CI).
- A new `worker-inbound-port` requirement, "Worker Substitutability": any `WorkerService` implementation MUST be observationally substitutable — a caller MUST NOT need to distinguish `InProcessWorker`, `LocalInferWorker`, or `RayWorker` by streaming event ordering, terminal-state semantics, cancellation behavior, or the error classification `WorkerError` exposes. Includes an explicit corollary tying it to the existing `tonic::`-leak rule: transport-specific failures MUST be normalized into `WorkerError` without exposing transport-specific types or protocols. `RayWorker` is the first Worker with a genuinely distinct failure source (network) and the first real test of this invariant.

### Out of Scope
- Any change to `tibios-ray` itself (separate repo, separate session).
- mTLS/UDS credentials (`29-deployment.md` territory, already deferred once by `worker-grpc-adapter`).
- Retry/backoff policy on top of the new transport-failure classification — this change classifies, the Runtime decides policy later.
- A general-purpose config system for the endpoint address.
- A dedicated substitutability conformance suite (error-classification / event-sequence / terminal-state equivalence testing across Workers). The new requirement is backed by the existing O1-O4 harness plus each Worker's own tests for now; a purpose-built suite is future work, deliberately not this PR's job.

## Capabilities

### New Capabilities
- `worker-grpc-client-adapter`: the `RayWorker` implementation and its O1-O4 conformance via the shared harness against an in-process fake server.

### Modified Capabilities
- `runtime-worker`: widens the crate's purpose to also host this one concrete, network-backed `WorkerService` implementation (private `adapters::grpc` tree stays private; only a new factory becomes public).
- `worker-wire-adapter`: adds the two missing conversions (domain→wire `ExecutionContext`, wire→domain `CancelAck`).
- `worker-inbound-port`: adds the transport-failure `WorkerError` variant, raises the harness's minimum invocation count, and adds the "Worker Substitutability" requirement (observational equivalence across implementations; transport failures normalized, never leaked as transport-specific types).
- `runtime-composition-root`: adds `WorkerKind::Ray` and its wiring.

## Approach

`RayWorker` lives inside `runtime-worker`, reusing the already-private `adapters::grpc` tree instead of opening a new cross-crate privacy hole (exploration Approach 1) — `tonic` is already an allowed external dependency there, and doesn't require `runtime-worker` to add `tokio`. The O1-O4-against-a-fake-server mechanism is pinned down in `sdd-design`.

All wire↔domain conversion stays centralized in `adapters/grpc/convert.rs` — there is no separate "proto" layer distinct from "grpc" in this codebase (`tonic-build`'s single-file `include_file` generates messages and client together), so `RayWorker` has no path to hand-roll a conversion of its own; it can only call `convert.rs`'s existing `TryFrom`/`From` impls.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `crates/runtime-worker/src/worker/` (new) | New | `RayWorker` + factory |
| `crates/runtime-worker/src/adapters/grpc/convert.rs` | Modified | 2 new conversions |
| `crates/runtime-worker/src/error.rs` | Modified | New `WorkerError` variant |
| `runtime/src/worker/mod.rs` | Modified | `WorkerKind::Ray`, `any_worker` arm |
| `runtime/src/worker/any.rs` | Modified | `AnyWorker::Ray` variant + dispatch |
| `runtime/src/worker/conformance.rs` | Modified | Harness invoked for `RayWorker` |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Transport-error classification wrong (retry loop vs. giving up too early) | Med | Design phase maps every relevant `tonic::Status` code explicitly, not a catch-all |
| In-process fake server becomes real, nontrivial test surface | Med | Scope it to exactly O1-O4's needs, nothing else |
| Endpoint config choice foists a bigger decision than intended | Low | Env var only, explicitly out-of-scope for anything richer |

## Rollback Plan

`RayWorker` and `WorkerKind::Ray` are additive — `main.rs` keeps defaulting to `LocalInfer`. Revert is deleting the new module, the new `WorkerKind` arm, and the two new conversions; no existing Worker's behavior changes.

## Dependencies

None beyond what `worker-grpc-adapter` already vendored.

## Success Criteria

- [ ] `RayWorker` passes the shared O1-O4 harness against an in-process fake server
- [ ] `AnyWorker::Ray` invoked through the harness too (eagerness regression coverage)
- [ ] `cargo test --workspace` and `cargo clippy --all-targets -- -D warnings` clean
- [ ] `main.rs` can select `WorkerKind::Ray` and complete one execution against a real `tibios-ray` instance (manual/operator verification, not CI)
- [ ] `worker-inbound-port/spec.md` states the "Worker Substitutability" requirement, and no existing Worker's tests need to change to satisfy it
