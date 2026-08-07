# Tasks: Local Inference Worker — Blocking Boundary, Enum Dispatch, Conformance Harness

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~860 (S1 ~230, S2 ~300, S3 ~330) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 (engine domain) -> PR2 (blocking boundary) -> PR3 (dispatch/harness/docs) |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Engine port + `DeterministicEngine` + engine-scan guards | PR 1 | base `main`; pure sync, no tokio; independently green |
| 2 | `Registry::should_stop` + `LocalInferWorker` blocking boundary | PR 2 | base = PR 1's merge commit on `main`; gated on spike (task 2.1) |
| 3 | `AnyWorker`, conformance harness, `main.rs` rebind, docs | PR 3 | base = PR 2's merge commit on `main`; final integration |

auto-chain resolution: proceed directly with PR1 as the next autonomous slice; no user decision pending. Each PR must independently compile and pass its own tests before the next PR starts.

---

## PR 1 — Engine domain (no Runtime, no dispatch, no tokio) — ~230 lines

### Phase 1.1: Engine port (RED -> GREEN)

- [x] 1.1 Write failing unit tests in `runtime/src/worker/local_infer/engine/port.rs` (or a `#[cfg(test)]` module) asserting: generation method is not `async fn`/returns no `Future` (compile-shape test via direct sync call), and is callable from a plain `#[test]` with no async runtime (spec scenarios "not async and returns no Future", "callable with no async runtime present")
- [x] 1.2 Create `runtime/src/worker/local_infer/engine/port.rs`: `GenerationRequest`, `Token`, `GenerationSummary`, `EngineError`, `SinkVerdict`, `TokenSink` trait, `TextGenerationEngine` trait (`&mut dyn TokenSink`, no generics, `Send + Sync`) per design D6 — all `std`-only, no `tokio`, no `runtime_worker` import
- [x] 1.3 Create `runtime/src/worker/local_infer/engine/mod.rs`: module docs stating the tokio-free/sync-only rule; re-export `port` and `reference` items

### Phase 1.2: DeterministicEngine (RED -> GREEN)

- [x] 1.4 Write failing unit tests: determinism (same request -> identical token sequence across two runs), no real inference / no sleep (source inspection or behavioral proxy), spin count is caller-supplied and does not affect output content, engine stops immediately on `SinkVerdict::Stop` (spec scenarios: reference-engine determinism, no-sleep/no-real-inference, spin-cost caller-configured, stop-on-sink-verdict)
- [x] 1.5 Implement `runtime/src/worker/local_infer/engine/reference.rs`: `DeterministicEngine` — FNV-1a rolling hash over prompt+token-index, spun `cpu_spin_iterations` times, no `std::thread::sleep`, respects `max_tokens` and `SinkVerdict::Stop`
- [x] 1.6 Run `cargo test -p runtime worker::local_infer::engine` and confirm all Phase 1.1/1.2 tests pass

### Phase 1.3: Architecture guard — engine containment scans (RED -> GREEN)

- [x] 1.7 Write failing guard tests in `runtime/tests/architecture_guard.rs`: `local_infer_engine_names_no_async_runtime` (no `tokio` under `local_infer/engine/`) and `local_infer_engine_declares_no_async_surface` (no `async`/`await` under same subtree) — both should pass immediately once 1.2/1.5 land, since the subtree is std-only by construction; write them first to prove the invariant is enforced, not incidental
- [x] 1.8 Generalize the existing `rust_files_excluding_adapters` (architecture_guard.rs:447) into a new `rust_files(dir)` helper (walk without adapter exclusion); keep `contains_identifier` (architecture_guard.rs:475) reused as-is for whole-identifier, comment-skipping matching
- [x] 1.9 Confirm zero `Cargo.toml` changes (workspace and `runtime` manifests untouched) and run `cargo test -p runtime --test architecture_guard`

---

## PR 2 — LocalInferWorker, the blocking boundary, cancellation — ~300 lines
**Base: PR 1's merge commit on `main`. Depends on PR 1.**

### Phase 2.0: Spike — MUST run first, before any other PR2 task

- [x] 2.1 **Spike (gate)**: write a ~20-line throwaway-or-keep proof that `tokio::runtime::Handle::block_on` called from inside `tokio::task::spawn_blocking` does not panic or deadlock on this toolchain/tokio version. Run it under `#[tokio::test(flavor = "multi_thread")]`.
  - **Decision point (do not silently improvise)**: if the spike is GREEN, proceed to 2.2 with the `Handle::block_on` design (D8) as specified. If the spike FAILS (panics or deadlocks), STOP and swap in **Fallback A** before any other PR2 task: a bounded `std::sync::mpsc::sync_channel` bridge — the blocking thread pushes events into the sync channel, and an async task on the runtime side owns the `ExecutionChannel` and drains it with `.await`. No port-level (`TextGenerationEngine`/`TokenSink`) change is needed either way; only `ChannelSink::emit`'s internals change. Record which path was taken in the PR description.

### Phase 2.1: Registry::should_stop (RED -> GREEN)

- [x] 2.2 Write a failing unit test in `runtime/src/worker/registry.rs` for `should_stop(workload_id)`: true when cancelled, true when the registration is absent (deregistered/never existed), false when present and not cancelled
- [x] 2.3 Implement `Registry::should_stop` (registry.rs, `pub(super)`, ~5 lines) per design D9: `state.get(&workload_id).is_none_or(|r| r.cancelled)`

### Phase 2.2: LocalInferWorker + blocking boundary (RED -> GREEN)

- [x] 2.4 Write failing unit tests (using a real `MpscExecutionChannel`) for `LocalInferWorker::execute`: full event sequence (`Progress("received")`, `OutputChunk`/`Progress` pairs, `MetricsSnapshot`, `EndOfStream`, terminal `ExecutionReport`); duplicate-in-flight rejected synchronously before any blocking task is queued (O1/O4 timing, spec scenario); dropping the future deregisters immediately even though the blocking task keeps running (spec scenario); `ChannelClosed` mid-run is survivable and reported distinctly (spec scenario)
- [x] 2.5 Write failing tests for cancellation/deadline polling order: explicit cancel stops at next token boundary -> `Cancelled` phase; abandoned execution (future dropped, no cancel) also stops via `should_stop`'s `is_none` half; zero-duration `max_execution_duration` fails before the first token (spec scenarios)
- [x] 2.6 Write a failing test for panic propagation: an engine that panics inside the blocking closure causes `execute`'s future to re-panic with the same payload once awaited, no `WorkerError` variant invented (spec scenario)
- [x] 2.7 Implement `runtime/src/worker/local_infer/mod.rs`: `LocalInferWorker::execute` — sync O1/O4 prologue (`RegistrationGuard::try_acquire`, guard held on async side, NOT moved into closure), `start` stamped before `spawn_blocking`, `Handle::current()` captured on async side, `tokio::task::spawn_blocking` running `run_off_executor`, `join.await` with `Err -> std::panic::resume_unwind`, `ChannelSink` implementing `TokenSink` with check order `ChannelClosed -> should_stop -> deadline` after each successful emit and once before the first token (per D8/D9, or Fallback A if 2.1 failed)
- [x] 2.8 Implement a factory in `runtime/src/worker/local_infer/mod.rs` obtaining the engine only via a type-erased handle (never naming `DeterministicEngine` outside the engine module) — deviation: named `build_local_infer_worker() -> LocalInferWorker` (concrete return type, `pub(super)`) rather than a `local_infer_worker() -> impl WorkerService` this task literally names, because `any.rs`'s `AnyWorker::LocalInfer` variant (PR3) must hold the concrete type to wrap it; the spec's "exposed only through a factory returning `impl WorkerService`" requirement is upheld one level up, by `worker::any_worker` (see 3.15 Deviations, same rationale as the removed `in_process_worker()`)
- [x] 2.9 Run `cargo test -p runtime worker::local_infer` and confirm all Phase 2.1/2.2 tests pass

### Phase 2.3: LocalInferWorker-only behavioral tests (RED -> GREEN)

- [x] 2.10 Write and pass executor-liveness test: `#[tokio::test(flavor = "multi_thread", worker_threads = 1)]` — spawn a ticker task looping `yield_now().await` + `AtomicU64` counter; run an execution with a large `cpu_spin_iterations`; assert the counter advanced throughout (proposal success criterion, spec scenario)
- [x] 2.11 Write and pass boundary-backpressure test: `#[tokio::test(flavor = "multi_thread")]`, capacity-4 channel, `max_tokens` well above capacity, drain spawned concurrently; assert every chunk delivered and `execute` returns a terminal `ExecutionReport` without panic/hang (spec scenario)
- [x] 2.12 Run `cargo test -p runtime --lib` for the whole `worker` module and confirm PR2 is fully green in isolation (no dependency on PR3 code)

---

## PR 3 — Dispatch, harness, docs, integration — ~330 lines
**Base: PR 2's merge commit on `main`. Depends on PR 2 (and transitively PR 1).**

### Phase 3.1: Conformance harness (RED -> GREEN)

- [x] 3.1 Create `runtime/src/worker/conformance.rs`, `#[cfg(test)]`-gated: move shared fixtures out of `in_process.rs`'s test module (`context_with(..)`, `sample_context(..)`, `generous_channel()` — capacity must exceed max events one fixture execution emits, `Receiver` bound and never `_`)
- [x] 3.2 Implement six generic async assertions in `conformance.rs`, each `async fn(worker: W) where W: WorkerService`: O1 (cancel-immediately-after-execute), O2 x3 (completed/cancelled/duration-breached -> subsequent `pulse` is `UnknownWorkload`), O3 (unknown id on both `cancel` and `pulse`), O4 (duplicate in-flight rejected, second channel silent)
- [x] 3.3 Implement `worker_conformance_suite!(name, factory)` macro emitting the six `#[tokio::test]` wrappers (all-or-nothing conformance) — deviation: macro takes `($factory:expr)` only, no `$name`, and emits bare items rather than a wrapping `mod` (see Deviations)
- [x] 3.4 Invoke `worker_conformance_suite!` for `InProcessWorker` in `in_process.rs` (replacing its old bespoke O1-O4 tests but keeping the 8 existing behavioral tests per spec's "supplementary coverage" requirement) and for `LocalInferWorker` in `local_infer/mod.rs`
- [x] 3.5 Run `cargo test -p runtime` and confirm the harness passes for both concrete workers before adding `AnyWorker`

### Phase 3.2: AnyWorker eager dispatch (RED -> GREEN)

- [x] 3.6 Write a failing test: a cancel issued between an `AnyWorker::execute` call and its first suspension point is accepted (`Ok(CancelAck)`), proving eager registration (spec scenario, `runtime-composition-root` delta)
- [x] 3.7 Implement `runtime/src/worker/any.rs`: `AnyWorker` enum (`InProcess(InProcessWorker)`, `LocalInfer(LocalInferWorker)`), `pub(super)`; `WorkerService` impl with eager `match self { .. => Box::pin(w.execute(..)) }` for `execute`/`cancel`/`pulse` — the match runs before any `async` block is entered, never `Box<dyn WorkerService>`, never `Either`/lazily-evaluated wrapper
- [x] 3.8 Invoke `worker_conformance_suite!` for both `AnyWorker::InProcess` and `AnyWorker::LocalInfer` arms in `any.rs` (or a `#[cfg(test)]` module there) — this is the invocation that would catch an eagerness regression
- [x] 3.9 In `runtime/src/worker/mod.rs`: add `WorkerKind` enum (`InProcess`, `LocalInfer`), `any_worker(kind: WorkerKind) -> impl WorkerService` factory, module declarations for `local_infer`, `any`, `conformance`

### Phase 3.3: Engine-name containment scan (RED -> GREEN)

- [x] 3.10 Write a failing guard test `engine_names_stay_inside_the_engine_module` in `architecture_guard.rs`: scans `crates/runtime-worker/src/` and `runtime/src/` excluding `runtime/src/worker/local_infer/engine/` for whole identifiers `llama`, `llama_cpp`, `ggml`, `candle` (using the `rust_files` helper from PR1 task 1.8, with the engine subtree excluded) — should be green once 3.7/3.9 land without naming the reference engine outside the engine module
- [x] 3.11 Run `cargo test -p runtime --test architecture_guard` and confirm all guard tests (existing + PR1's two + this one) are green, zero table edits to `EXPECTED_MEMBERS`/`ALLOWED`/`EXTERNAL_ALLOWED`

### Phase 3.4: Composition-root rebind + docs

- [x] 3.12 Update `runtime/src/main.rs`: rebind from `in_process_worker()` to `worker::any_worker(WorkerKind::LocalInfer)`; confirm no concrete Worker struct or engine type is named in the file (spec scenario)
- [x] 3.13 Fix the doc-comment defect in `crates/runtime-worker/src/ports/worker_service.rs` (lines ~36-53): replace the `Either`-based lazy dispatch sketch with the eager-match-then-`Box::pin` shape, and add the O1 hazard note (a lazily-evaluated wrapper defers registration to first poll, silently breaking O1) — doc-comment-only edit, no new spec requirement per the spec's own note
- [x] 3.14 Amend `docs/architecture/05-async-concurrency.md:37` to the maintainer-approved text: "This is a hard requirement for `local-infer`: llama.cpp inference is CPU-bound and must never run directly on a Tokio task. It runs on a dedicated blocking thread pool. The Runtime-facing boundary is asynchronous. Internal implementations may be synchronous provided they never block the Runtime executor."
- [x] 3.15 Run full `cargo test --workspace` and `cargo clippy --all-targets -- -D warnings`; confirm `InProcessWorker`'s 8 existing tests still pass unmodified except the fixture import, and `unsafe_code = "deny"` holds — deviation: `in_process_worker()`/`local_infer_worker()` top-level factories (superseded by `any_worker`) were removed as genuinely dead code once `main.rs` rebound to `any_worker` (see Deviations)

---

## Rollback Notes

- Each PR reverts independently via `git revert`, in reverse order (PR3 -> PR2 -> PR1).
- Reverting PR3 alone restores `main.rs` to `in_process_worker()` and leaves the (still-compiling) engine/worker subtree dead but green.
- Reverting PR2 requires PR3 already reverted (PR3 depends on `LocalInferWorker`).
- PR1 has no runtime-facing behavior change; it is inert until PR2 references it.
