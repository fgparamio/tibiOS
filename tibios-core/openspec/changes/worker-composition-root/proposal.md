# Proposal: Worker Composition Root — First Executable Slice

## Intent

`ports::{WorkerService, ExecutionChannel}` exist but **nothing implements them**. No crate depends on an async runtime, and `runtime/src/main.rs` is `fn main() {}`. The Worker port is therefore unproven: we have a contract nobody has ever run. This change closes the loop end-to-end in-process — one real `execute` call, through a real channel, printing a real `ExecutionReport` — so the port's shape is validated by execution, not by review.

Why now: both prerequisite changes (`worker-grpc-adapter`, `worker-inbound-port`) are archived. The gRPC path is blocked externally (below), so the in-process slice is the only way to move.

## Scope

### In Scope
- A concrete `tokio::sync::mpsc`-backed `ExecutionChannel` implementation, owned by `runtime`.
- One concrete in-process `WorkerService` implementation doing real async work (real awaits, real event emission, honoring obligations O1–O4: register-before-suspend, always-deregister, `DuplicateWorkload`, `UnknownWorkload`). Not a test double.
- Exposure via a **factory function** returning `impl WorkerService` — never naming a concrete/transport type — establishing the pattern the future gRPC worker is forced into.
- `runtime/Cargo.toml` gains `tokio`; `EXTERNAL_ALLOWED` in `runtime/tests/architecture_guard.rs` gains `("runtime", &["tokio"])` as a deliberate, reviewed table edit.
- `runtime/src/main.rs` wiring: build worker + channel, submit one job, drain events, print the terminal `ExecutionReport`. `cargo run -p runtime` succeeds.

### Out of Scope
- **The gRPC-client `WorkerService` adapter to `tibios-ray` — blocked on an external dependency.** Confirmed 2026-08-06: `tibios-ray`'s `worker.py`/`server.py` are docstring stubs with zero `grpc` usage, so no live server exists to build or test against. Deferred until `tibios-ray` serves `WorkerExecution`.
- `enum AnyWorker` dispatch (`worker_service.rs:37`) — meaningless with one implementation.
- A `local-infer` worker; real inference of any kind.
- `runtime-allocation`'s single-field `AllocationContract`, and the `runtime-object` / `runtime-scheduler` stubs. The smoke path hand-constructs everything it needs.
- Cancellation/pulse *wiring* in `main.rs` (the implementation must still honor them; only the demo path is single-happy-path).

## Capabilities

### New Capabilities
- `worker-inprocess-adapter`: the concrete in-process `WorkerService` and `mpsc`-backed `ExecutionChannel`, the factory-function exposure rule, and the obligation guarantees they must uphold.

### Modified Capabilities
- `runtime-composition-root`: the "No Public Traits In This Change" requirement (`main.rs` MUST be a stub, no cross-domain wiring) is retired and replaced by a real-wiring requirement, plus `runtime` becoming the sole owner of the async-runtime dependency.

## Approach

**Adapters live in `runtime`, not `runtime-worker`.** This is spec-forced, not preference: `worker-inbound-port/spec.md` — "The Domain Surface Names No Transport Type And No Tokio Type" — forbids any `tokio::` path in `runtime-worker`'s public surface, and its "zero async runtime in `cargo test`" requirement forbids pulling tokio into that crate at all. `runtime` is the only crate that may own an executor.

**Factory function over exported struct.** The Composition Root receives `impl WorkerService`, never a named concrete type. `WorkerService` is permanently `dyn`-incompatible (generic `execute<C>`), so this is the only composition shape that survives the future gRPC worker without leaking a transport type past `runtime-worker`'s `adapters` containment guard.

**Prove it by running it.** Success is `cargo run -p runtime` printing a real report, plus tests asserting emitted events reached the receiver through the real channel.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `runtime/src/` | New | mpsc `ExecutionChannel`, in-process `WorkerService`, factory fn |
| `runtime/src/main.rs` | Modified | Stub → real wiring, `#[tokio::main]` |
| `runtime/Cargo.toml` | Modified | Adds `tokio` |
| `Cargo.toml` (workspace) | Modified | Adds `tokio` to `[workspace.dependencies]` |
| `runtime/tests/architecture_guard.rs` | Modified | `EXTERNAL_ALLOWED` gains `("runtime", &["tokio"])` |
| `openspec/specs/runtime-composition-root/` | Modified | Stub requirement retired |
| `crates/runtime-worker/` | **Untouched** | Domain stays runtime-agnostic |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Estimated diff ~500-700 lines with tests — exceeds the 400-line review budget | High | **Chained PRs recommended**: (1) tokio dep + guard row + mpsc channel, (2) worker impl + factory, (3) `main.rs` wiring + smoke. Each slice compiles, tests, and rolls back independently |
| Punching `tokio` into `EXTERNAL_ALLOWED` normalizes editing the guard table | Medium | Spec delta records *why* `runtime` alone may own an executor; guard row is one crate, one dep |
| Adapters in `runtime` blur Composition Root vs adapter layer | Medium | Accepted for one slice; open design question — a dedicated crate would break `workspace_has_exactly_the_expected_members` (16 members), a bigger guard edit than one allowlist row. Revisit when the second worker lands |
| Factory-fn pattern designed against a hypothetical (gRPC) consumer | Medium | Constraint is concrete (`dyn`-incompatible trait + adapters containment guard), not speculative |
| Obligations O1–O4 hard to prove without a second implementation | Low | Test them directly against this implementation; they become the conformance suite the gRPC worker inherits |

## Rollback Plan

Each chained slice is independently revertible. Full rollback = revert the three commits: `main.rs` returns to `fn main() {}`, `tokio` leaves both `Cargo.toml`s, the `EXTERNAL_ALLOWED` row returns to `("runtime", &[])`. `runtime-worker` is never touched, so nothing downstream of the domain crate can break.

## Dependencies

- `worker-inbound-port` (archived) — provides the traits. Satisfied.
- `worker-grpc-adapter` (archived) — provides wire conversion. Satisfied, unused by this slice.
- **Blocked (out of scope)**: `tibios-ray` gRPC server implementation.

## Success Criteria

- [ ] `cargo run -p runtime` submits one job and prints a terminal `ExecutionReport`.
- [ ] `cargo test --workspace` green, including all architecture guard tests.
- [ ] `cargo clippy --all-targets -- -D warnings` clean.
- [ ] `runtime-worker` has zero new dependencies and zero source changes.
- [ ] No concrete worker type is named in the Composition Root's binding — only `impl WorkerService`.
- [ ] Obligations O1–O4 each covered by a test.
