# Design: Local Inference Worker — Blocking Boundary, Enum Dispatch, Conformance Harness

## Technical Approach

Zero new crates, zero new external dependencies, zero workspace-manifest churn. Everything lands inside `runtime`'s existing `src/worker/` module tree plus one sentence of canon.

The change has exactly one novel mechanism — **an execution that runs off the executor and writes back into an async `ExecutionChannel` from a blocking thread** — and two structural artifacts that mechanism finally makes buildable: the `AnyWorker` enum-dispatch recipe (`worker_service.rs:36-53`, documented since `worker-inbound-port`, never exercised) and the shared O1-O4 conformance harness (`worker-inbound-port/design.md:227`, deliberately deferred to this change).

Decision numbering continues this change's **local** scheme — the proposal used D0–D3, so this document opens at D4, matching `worker-contract-capability-field` (proposal D1–D5 → design D6+). `worker-composition-root` restarted at D1 only because its proposal numbered nothing.

D4 settles the proposal's open **D0**. D1–D3 are confirmed unchanged and are not reopened.

---

## D4 — Engine placement: `runtime/src/worker/local_infer/engine/` (settles proposal D0)

**Choice: D0-b.** The engine port, the reference engine, and every synchronous line of inference code live inside the Composition Root, as plain modules under `runtime/src/worker/local_infer/`. `runtime-worker` gains **nothing** — not a module, not a trait, not a line.

```
runtime/src/worker/
├── mod.rs             # factories + AnyWorker wiring (modified)
├── channel.rs         # MpscExecutionChannel (unchanged)
├── registry.rs        # + one method (D9)
├── in_process.rs      # unchanged except its test module (D11)
├── conformance.rs     # NEW, #[cfg(test)] — the shared O1-O4 harness (D11)
├── any.rs             # NEW — AnyWorker enum dispatch (D10)
└── local_infer/
    ├── mod.rs         # NEW — LocalInferWorker, spawn_blocking, Handle::block_on, ChannelSink.
    │                  #       THE ONLY FILE IN THIS SUBTREE PERMITTED TO NAME `tokio`.
    └── engine/
        ├── mod.rs     # NEW — module docs stating the tokio-free/sync-only rule; re-exports
        ├── port.rs    # NEW — TextGenerationEngine, TokenSink, SinkVerdict, Token, GenerationRequest, EngineError
        └── reference.rs # NEW — DeterministicEngine (placeholder, D7)
```

### Why not D0-a (`crates/runtime-worker/src/engine/`)

Four independent reasons, in descending force:

| # | Argument | Detail |
|---|---|---|
| 1 | **The future external dependency lands in the wrong crate** | D3 mandates the llama.cpp follow-up satisfies `unsafe_code = "deny"` by depending on an *external bindings crate*. Under D0-a that dependency is declared by `runtime-worker` — the Worker **domain** crate that `runtime-api`, `runtime-state` and every future consumer of `ExecutionContext`/`ExecutionEvent` link against. Every one of them would then transitively build llama.cpp. Placement must be chosen for where the engine's dependency eventually lands, not for where a zero-dependency stub is convenient today. |
| 2 | **Consumer-Owned Contracts puts the port with its consumer** | `02-project-structure.md:198` — "Outbound Ports are defined by the consuming domain." The consumer of "generate text" is `LocalInferWorker`, which lives in `runtime`. The Worker *domain* does not require text generation; it requires "execute a Workload". Under D0-a the port would sit in `runtime-worker` while its only consumer sits in `runtime`. |
| 3 | **Direct precedent, already argued** | `worker-inbound-port/design.md:104` rejected enum dispatch in `runtime-worker` as "the port crate depending on its own adapters, an outright inversion of `02-project-structure.md`'s Ports/Adapters split." A reference inference engine is a stronger form of the same inversion. `worker-inprocess-adapter/spec.md:5` put the *first* real Worker in `runtime` "never `runtime-worker`" for the same family of reasons. |
| 4 | **`adapters/` is structurally closed anyway** | Verified: `lib.rs` declares a bare `mod adapters;`, `adapters/mod.rs:1-3` says "Nothing in this module tree is re-exported", and `architecture_guard.rs:565` (`runtime_worker_never_reexports_the_adapter_module`) asserts the identifier `adapters` occurs *exactly once* outside the tree. D0-a therefore requires a **new public** `engine` module, not a private one — a larger public-API expansion than it appears. |

### The counter-arguments, answered honestly

- **`25-ai-runtime.md:19`: "AI Worker implementations (`local-infer`, `tibios-ray`) belong to `runtime-worker`."** This is domain ownership, not crate placement, and the sentence proves it itself: `tibios-ray` is a **separate repository** and cannot literally live in a `tibios-core` crate, yet the sentence names it. `25-ai-runtime.md:15` further declines to assign a crate at all ("currently owns no crate of its own"). What the line *does* bind is that both implementations obey `18-worker-model.md` — which D6-D9 do.
- **`02-project-structure.md:470`: "The Composition Root owns no business behavior. Its responsibility is assembly only."** Real tension, and D0-b bends it — but `InProcessWorker` already bent it identically (`in_process.rs` ships an FNV checksum loop and contract enforcement), under the same justification: a reference implementation whose purpose is to prove wiring. The correct long-term home for a *real* engine is its own crate, which is what the FFI follow-up should create — at the moment it has an external dependency to justify one (`02-project-structure.md`'s Architecture Review Checklist, echoed by `25-ai-runtime.md:15`'s "should such a language emerge").
- **D0-b loses the crate-boundary proof that the engine is tokio-free.** True, and it is the one real cost. A `Cargo.toml` + `EXTERNAL_ALLOWED` row would have made it structural. D12 replaces it with a source-token containment scan over `local_infer/engine/` — the same technique `worker-grpc-adapter` D7 already uses to contain transport code, inverted.

### Reversibility settles it

D0-b is the **cheaper mistake**. If wrong, `runtime/src/worker/local_infer/engine/*.rs` → `crates/local-infer/src/*.rs` is a file move plus a manifest entry, because the subtree has zero dependencies on anything (D6). If D0-a is wrong, the fix additionally requires deleting public API from a domain crate and retiring a published spec requirement.

**Named follow-up (not this change):** when the FFI engine arrives with its bindings dependency, extract `local_infer/engine/` into `crates/local-infer/` — and only then answer the `local-infer` vs `runtime-local-infer` naming question, which D0-b makes moot today.

## D5 — `05-async-concurrency.md:37` amendment (maintainer-approved)

The conflict this change was escalated to resolve: line 37 says "the crate's own API is async at the boundary", and D1 makes the inference core synchronous.

**Independent finding — the doc's protected property survives D1 intact.** Line 37 protects two things: (i) inference never runs on a Tokio task, and (ii) the executor is never blocked. D1 preserves both — the work runs on tokio's blocking pool, and every `.await` the executor sees is on a `JoinHandle`. What breaks is only the *locus* of the async boundary. Line 37 assumed `local-infer` was one artifact the Runtime awaits directly; the Runtime never calls it directly, and cannot — the Runtime's only entry point is `WorkerService::execute`, which **is** async-returning. The async boundary did not disappear; it moved to the Worker boundary, one layer out.

Three alternatives were evaluated for achieving literal compliance without an amendment, and all three were rejected:

| Alternative | Why rejected |
|---|---|
| **Hand-rolled `std::thread` pool + hand-written `Future`/`Waker`** — genuinely possible with zero dependencies (`Future`, `Waker`, `Context` are `core`, not tokio) | Requires reimplementing a bounded two-sided-backpressure queue, a waker slot, cancellation, thread lifecycle and panic propagation — ~200 lines of the most error-prone code category in Rust, owing stress tests under `05-async-concurrency.md:117`, to reproduce `tokio::sync::mpsc` + `spawn_blocking`. A crate-owned pool spun up implicitly is also close to `05-async-concurrency.md:125`'s "hidden background threads" and weakens the ownership story `:87` demands. |
| **Inject a `BlockingExecutor` outbound port** (`run_blocking(f) -> impl Future`), implemented in `runtime` by `spawn_blocking` | Buys literal async-boundary syntax and nothing else — the work still runs on tokio's blocking pool, `Handle::block_on` still appears in `runtime`. And `run_blocking` is a technology concept, not domain language: `02-project-structure.md:200-208` forbids exactly this ("Ports express domain language. Ports never expose technology"). |
| **Let the engine depend on `tokio` directly** | The frozen corpus never states the Golden Rule (`05-async-concurrency.md:17` only forbids *exposing* Tokio types); the Golden Rule is this project's own `runtime-composition-root/spec.md` invariant. But relaxing it for the first CPU-bound consumer is precisely the failure this change exists to test, and it deletes a machine check (`async_runtime_is_allowlisted_for_exactly_one_crate`) whose value evaporates on first exception. |

**Amendment (maintainer-approved; the second sentence is the maintainer's verbatim wording).** Replace line 37 with:

> This is a hard requirement for `local-infer`: llama.cpp inference is CPU-bound and must never run directly on a Tokio task. It runs on a dedicated blocking thread pool. The Runtime-facing boundary is asynchronous. Internal implementations may be synchronous provided they never block the Runtime executor.

Two edits, both minimal: "the `local-infer` crate" → "`local-infer`" (D0-b means no such crate exists yet), and the async-at-the-boundary clause → the approved sentence. The hard requirement and the dedicated-pool clause survive verbatim. **No other frozen document changes** — `02-project-structure.md`'s Project Layout is untouched (no new crate), and `18-worker-model.md:132`, `25-ai-runtime.md:42`, `07-performance.md:93` all remain true as written.

This amendment is *enforced*, not aspirational: D12's scan machine-checks that the engine subtree names neither `tokio` nor `async`/`await`.

## D6 — The engine port: the engine produces tokens; the adapter owns every policy

`local_infer/engine/port.rs`, entirely `std`, no `async`, no `tokio`, no `runtime_worker` import:

```rust
pub struct GenerationRequest { pub prompt: String, pub max_tokens: u64, pub cpu_spin_iterations: u32 }
pub struct Token { pub sequence: u64, pub bytes: Vec<u8> }
pub struct GenerationSummary { pub tokens_produced: u64, pub stopped_early: bool }
pub enum EngineError { Rejected(String) }

/// The adapter's answer to "keep going?" — the only channel through which
/// cancellation, deadlines and channel closure reach the engine.
pub enum SinkVerdict { Continue, Stop }

pub trait TokenSink { fn accept(&mut self, token: Token) -> SinkVerdict; }

pub trait TextGenerationEngine: Send + Sync {
    fn generate(&self, request: &GenerationRequest, sink: &mut dyn TokenSink)
        -> Result<GenerationSummary, EngineError>;
}
```

**The load-bearing property is the direction of the `SinkVerdict`.** The engine knows nothing about cancellation, allocation contracts, `ExecutionEvent`, `WorkloadId`, or channels; it produces tokens and stops when told. All policy — cooperative cancellation (D9), `max_execution_duration`, `ChannelClosed` — lives in the adapter's `TokenSink` impl. That is what keeps the engine subtree dependency-free and therefore extractable (D4), and it is the seam a real llama.cpp loop plugs into unchanged.

`&mut dyn TokenSink` rather than a generic parameter: keeps `TextGenerationEngine` dyn-compatible, so `LocalInferWorker` can hold `Arc<dyn TextGenerationEngine>` and a future multi-engine build can hold a map of them. No monomorphization is wanted here — this is a once-per-execution call, not a hot path.

**Engine selection stays inside (D2).** `LocalInferWorker` holds one `Arc<dyn TextGenerationEngine>`; no engine name is reachable from `mod.rs`, from `any.rs`, or from `main.rs`. Capability-keyed dispatch (`ExecutionContext::worker_capability()` → engine) is **deliberately not built here**: a capability miss has no representable failure, and inventing `WorkerError::UnsupportedCapability` is a `runtime-worker` + spec change out of this change's scope. Named as a follow-up in Open Questions.

## D7 — `DeterministicEngine`: trivially small, genuinely CPU-bound, obviously a placeholder

```rust
/// NOT an inference engine, and never will be. A placeholder that exists to
/// prove the blocking boundary end-to-end: it burns a bounded, caller-chosen
/// amount of CPU per token and emits a deterministic byte sequence derived
/// from the prompt. The llama.cpp engine replaces this file wholesale.
pub struct DeterministicEngine;
```

Per token: fold `prompt` bytes and the token index into an FNV-1a rolling hash (the same construction `in_process.rs:31-41` already proved), then spin that fold `cpu_spin_iterations` more times, then hand `hash.to_le_bytes()` to the sink. Stops at `max_tokens` or on the first `SinkVerdict::Stop`.

Two constraints that are not arbitrary:

- **No `std::thread::sleep`.** Forbidden outright by `05-async-concurrency.md:29`, and it would be a lie: sleeping proves a thread was parked, not that CPU-bound work left the executor. A spin loop is the only honest stand-in for llama.cpp.
- **The spin count is caller-supplied**, read from `execution_parameters["cpu_spin_iterations"]` (default small enough that the whole suite stays fast). D11's executor-liveness test needs a run long enough to observe, and hardcoding a duration would make the suite timing-fragile.

## D8 — The blocking boundary: `spawn_blocking` + a captured `Handle`

`local_infer/mod.rs` is the only tokio-aware file in the subtree.

```rust
fn execute<C>(&self, context: ExecutionContext, channel: C)
    -> impl Future<Output = Result<ExecutionReport, WorkerError>> + Send
where C: ExecutionChannel
{
    let workload_id = context.workload_id();
    let start = Instant::now();
    // O1 + O4, synchronously in this function body — identical to
    // in_process.rs:88, and for the identical reason.
    let acquired = RegistrationGuard::try_acquire(Arc::clone(&self.registry), workload_id);
    let registry = Arc::clone(&self.registry);
    let engine = Arc::clone(&self.engine);
    async move {
        let guard = acquired.ok_or(WorkerError::DuplicateWorkload(workload_id))?;
        let handle = tokio::runtime::Handle::current();
        let join = tokio::task::spawn_blocking(move || {
            run_off_executor(&*engine, &registry, &handle, start, context, channel)
        });
        let outcome = match join.await {
            Ok(outcome) => outcome,
            Err(join_error) => std::panic::resume_unwind(join_error.into_panic()),
        };
        drop(guard); // O2 — explicit, though Drop would do it on every path anyway
        outcome
    }
}
```

Five decisions packed in here, each with a failure mode if reversed:

1. **The `RegistrationGuard` is NOT moved into the closure.** A `spawn_blocking` task cannot be aborted; if the guard travelled with it, dropping `execute`'s future would leave the registration alive until the blocking task finished — O2 violated on the drop path. The guard stays on the async side; only `Arc<Registry>` crosses (D9).
2. **`Handle::current()` is captured on the async side**, then moved in. Capturing inside the closure also works (blocking-pool threads carry the runtime context), but the explicit capture makes the dependency visible and fails loudly at the right place.
3. **`Handle::block_on` is legal in a `spawn_blocking` thread and nowhere else in this codebase.** A blocking-pool thread is *not* an asynchronous execution context, so `enter_runtime` does not panic there. `tokio::task::block_in_place` is explicitly **not** used: it blocks a *worker* thread, requires the multi-thread flavor, and defeats the entire purpose.
4. **`start` is stamped before `spawn_blocking`**, so blocking-pool queueing counts against `max_execution_duration`. A saturated pool cannot silently extend a lease.
5. **A panicking engine re-panics via `resume_unwind`**, reproducing exactly what would have happened had the engine run inline. No `WorkerError` variant is invented for it — adding one is a `runtime-worker` change this doesn't need, and "the engine has a bug" is not a classifiable execution failure. Revisit when a real engine can panic in the field.

**Every event is emitted from the blocking thread** — `Progress("received")`, each `OutputChunk`/`Progress` pair, `MetricsSnapshot`, `EndOfStream`, and the terminal `ExecutionReport` construction. The async side does registration, spawn, and await, nothing else. This maximizes what the boundary actually proves.

```rust
struct ChannelSink<'a, C: ExecutionChannel> {
    channel: C, handle: &'a Handle, registry: &'a Registry,
    workload_id: WorkloadId, deadline: Instant, stop: Option<StopReason>,
}
impl<C: ExecutionChannel> ChannelSink<'_, C> {
    fn emit(&self, event: ExecutionEvent) -> Result<(), ChannelClosed> {
        self.handle.block_on(self.channel.emit(event))   // the ONE block_on
    }
}
impl<C: ExecutionChannel> TokenSink for ChannelSink<'_, C> {
    fn accept(&mut self, token: Token) -> SinkVerdict { /* emit; then the three D9 checks */ }
}
```

**Verification gate for `sdd-apply`:** the very first task must be a ~20-line spike proving `Handle::block_on(async {})` inside `spawn_blocking` does not panic on this toolchain, before anything else is built. If it does, **Fallback A** applies without touching the port: the blocking thread pushes events into a bounded `std::sync::mpsc::sync_channel`, and an async task on the runtime side owns the `ExecutionChannel` and drains it with `.await`. Backpressure survives (the sync channel is bounded); what is lost is the by-value channel move into the closure, which is a rationale in the port's doc comment, not a compile-time requirement.

## D9 — Cancellation crosses the boundary as one new synchronous `Registry` method

The blocking thread cannot `.await` a cancellation signal and cannot be aborted, so it must **poll**. One new method on the existing `Registry` (`registry.rs`), five lines, no struct change:

```rust
/// True when the runtime side no longer wants this execution to continue:
/// either `cancel` was accepted, or the registration is gone entirely —
/// which means `execute`'s future was dropped and nobody is waiting.
pub(super) fn should_stop(&self, workload_id: WorkloadId) -> bool {
    self.with_registry(|state| state.get(&workload_id).is_none_or(|r| r.cancelled))
}
```

The `is_none()` half is the part that matters and the part a naive `is_cancelled()` reuse would miss: when `execute`'s future is dropped, `RegistrationGuard::Drop` deregisters, and the still-running blocking task would otherwise never learn it has been abandoned. One `std::sync::Mutex` acquisition per token, uncontended, on a non-executor thread — free, and provably free of the "`MutexGuard` across an `.await`" hazard because there is no `.await`.

`ChannelSink::accept` therefore runs three checks after each successful emit, in this order: `ChannelClosed` → `should_stop` → `Instant::now() >= deadline`. Each sets a distinct `StopReason`, which selects the terminal `ExecutionPhase` (`Cancelled` / `Failed`) and the report summary. The deadline is also checked once before the first token, so a pool-queued execution that already blew its contract fails immediately.

**Rejected:** minting a per-registration `Arc<AtomicBool>` from the `Registry`. It is the same information behind more machinery, and it forces `Registration` to lose `Copy`, churning `pulse`/`is_cancelled` for nothing.

## D10 — `AnyWorker`: the dispatch must be **eager**, or O1 breaks silently

`runtime/src/worker/any.rs`, `pub(super)`:

```rust
pub(super) enum AnyWorker { InProcess(InProcessWorker), LocalInfer(LocalInferWorker) }

impl WorkerService for AnyWorker {
    fn execute<C>(&self, context: ExecutionContext, channel: C)
        -> impl Future<Output = Result<ExecutionReport, WorkerError>> + Send
    where C: ExecutionChannel
    {
        // The match runs NOW. Wrapping it in `async move { … .await }` would
        // defer the inner `execute` call to first poll — and both inner
        // implementations do their O1 registration in the *call*, not in the
        // returned future. A cancel issued between `execute(..)` and the first
        // `.await` would then be answered `UnknownWorkload`. The dispatch layer
        // would silently break the obligation its own workers uphold.
        let future: Pin<Box<dyn Future<Output = Result<ExecutionReport, WorkerError>> + Send>> =
            match self {
                Self::InProcess(w)  => Box::pin(w.execute(context, channel)),
                Self::LocalInfer(w) => Box::pin(w.execute(context, channel)),
            };
        future
    }
    // cancel / pulse: same eager-match-then-box shape.
}
```

**Boxing instead of `Either`.** The port's doc sketch (`worker_service.rs:44-50`) uses `Either`, which would mean a new external dependency (`either`/`futures`) — or a hand-rolled one, which needs `Pin` projection, which needs `unsafe`, which `Cargo.toml:53-54` denies workspace-wide. `Box::pin` is safe, dependency-free, one allocation per port call against an inference run, and the port's own doc comment already blesses it: "If a boxing/type-erasure wrapper … is ever needed instead, it also belongs in the Composition Root" (`worker_service.rs:59-63`). **`worker_service.rs`'s doc sketch should be amended** to show the eager-match-plus-box shape and carry the O1 warning — the current sketch, read literally by a future implementer, is a trap.

**Factories in `mod.rs`** — `AnyWorker` is `pub(super)` and never named outside `worker/`:

```rust
pub enum WorkerKind { InProcess, LocalInfer }              // a *selection*, not a worker type
pub fn in_process_worker() -> impl WorkerService { … }     // unchanged (spec-bound)
pub fn local_infer_worker() -> impl WorkerService { LocalInferWorker::new() }
pub fn any_worker(kind: WorkerKind) -> impl WorkerService  { /* AnyWorker */ }
```

`main.rs` calls `worker::any_worker(WorkerKind::LocalInfer)` — naming an implementation *selection*, which `02-project-structure.md:291` assigns to the Composition Root, and never a worker type or a transport.

## D11 — The conformance harness lives *inside* the binary crate, and is macro-emitted

**Hard constraint, easy to trip over:** `runtime` is binary-only (`Cargo.toml:10-12`, no `src/lib.rs`). An integration test in `runtime/tests/` links against a library target that does not exist, so it can reach neither `InProcessWorker`, `LocalInferWorker`, nor `AnyWorker` — all `pub(super)`. `architecture_guard.rs` only works there because it imports nothing from `runtime`.

The harness is therefore `runtime/src/worker/conformance.rs`, gated `#[cfg(test)]`:

- **Shared fixtures**, moved out of `in_process.rs`'s test module: `context_with(..)`, `sample_context(..)`, `generous_channel()`.
- **Six generic async assertions**, each `async fn(worker: W) where W: WorkerService`, one per spec scenario: O1 (cancel-immediately-after-execute), O2 × 3 (completed / cancelled / duration-breached → `pulse` is `UnknownWorkload`), O3 (unknown id on both `cancel` and `pulse`), O4 (duplicate in-flight rejected, second channel silent).
- **`worker_conformance_suite!(name, factory)`** — a `macro_rules!` emitting the six `#[tokio::test]` wrappers. The macro is the point: conformance becomes **all-or-nothing**, so no Worker can quietly adopt five obligations out of six.

Invoked three times — `in_process.rs`, `local_infer/mod.rs`, and `any.rs` (both arms). The third is not ceremony: D10 is exactly where O1 would break unobserved.

**Two fixture rules that keep the suite from hanging**, both consequences of `Handle::block_on`:

1. `generous_channel()` capacity MUST exceed the maximum events one fixture execution emits, and the `Receiver` MUST stay bound (`_receiver`, never `_`). If the channel fills with no drainer, the blocking thread parks forever and the test hangs rather than fails. `InProcessWorker` tolerates a small channel; `LocalInferWorker` does not.
2. `#[tokio::test]`'s default `current_thread` flavor is fine for all six obligations (nothing needs a concurrent drain), but the two tests below need explicit flavors.

**Two `LocalInferWorker`-only tests, outside the shared suite:**

| Test | Shape |
|---|---|
| Executor liveness (proposal success criterion) | `#[tokio::test(flavor = "multi_thread", worker_threads = 1)]`. Spawn a ticker task looping `yield_now().await` and bumping an `AtomicU64`; run an execution with a large `cpu_spin_iterations`; assert the counter advanced. With exactly one worker thread, an inline engine would freeze it. |
| Backpressure across the boundary (proposal risk mitigation) | `#[tokio::test(flavor = "multi_thread")]`, capacity-4 channel, `max_tokens` well above it, drain spawned concurrently. Proves `Handle::block_on(emit)` genuinely parks the blocking thread against a full bounded channel and resumes — the exact `Handle::block_on` deadlock the proposal flagged. |

`InProcessWorker`'s existing seven tests stay as-is; the three that duplicate O2/O3/O4 coverage are **not deleted** — they assert phase and event-sequence detail the harness deliberately does not (the harness asserts obligations, per-worker tests assert behavior). Regression-free by construction.

## D12 — Architecture guard: zero table edits, three new containment scans

D0-b means **no** `EXPECTED_MEMBERS`, `ALLOWED`, or `EXTERNAL_ALLOWED` change — the workspace stays at 16 members and `runtime` keeps `&["tokio"]`. That deletes the proposal's "guard churn touches three tables at once" risk entirely.

What replaces the crate boundary is source containment, reusing the file-walk and whole-identifier helpers already in `architecture_guard.rs:447-494`. One generalization is needed: a plain `rust_files(dir)` walker beside the existing `rust_files_excluding_adapters`.

| New test | Invariant | Scope |
|---|---|---|
| `local_infer_engine_names_no_async_runtime` | identifier `tokio` never appears | `runtime/src/worker/local_infer/engine/` |
| `local_infer_engine_declares_no_async_surface` | identifiers `async` / `await` never appear — machine-checks D1 and D5's amended wording | same |
| `engine_names_stay_inside_the_engine_module` | `llama`, `llama_cpp`, `ggml`, `candle` never appear | `crates/runtime-worker/src/`, `runtime/src/` **excluding** `worker/local_infer/engine/` |

All three skip comment lines (the existing convention) — the engine's own module docs will explain *why* tokio is absent, and must not trip the scan. All three use `contains_identifier` (whole-identifier), stricter than the transport scan's substring match. The first two are the direct, machine-checked stand-in for the `EXTERNAL_ALLOWED` row a separate crate would have earned, and they are what makes D5's amendment enforceable rather than aspirational.

## D13 — Three slices, one PR

| Slice | Contents | Depends on | Est. lines |
|---|---|---|---|
| **S1** | `local_infer/engine/` (port + `DeterministicEngine` + unit tests, pure sync); D12's two engine scans | — | ~230 |
| **S2** | `Registry::should_stop` + test; `local_infer/mod.rs` (`LocalInferWorker`, `ChannelSink`, `spawn_blocking`); `local_infer_worker()` factory; the two `LocalInferWorker`-only tests; the `Handle::block_on` spike **first** | S1 | ~300 |
| **S3** | `conformance.rs` harness + macro; three invocations; `any.rs` + `WorkerKind` + `any_worker()`; `main.rs` rebind; `worker_service.rs` doc-sketch amendment; `05-async-concurrency.md:37`; D12's engine-name scan | S2 | ~330 |

Each slice compiles, tests, and reverts independently (`worker-composition-root`'s standing norm).

**Review Workload Forecast** — estimated changed lines ≈ **860**. 400-line budget risk: **High**. Chained PRs recommended: **Yes**. Decision needed before apply: **Yes**. Recommendation: three chained PRs on the S1 → S2 → S3 boundaries, which are already dependency-ordered and individually green. S1 alone is reviewable as "a deterministic token generator with no dependencies"; S2 as "the blocking boundary"; S3 as "dispatch + conformance + canon". Merging S2 and S3 would put the doc amendment in the same diff as the mechanism it describes, which is a real benefit — but at ~630 lines it needs a `size:exception`.

---

## Data Flow

```
main.rs — worker::any_worker(WorkerKind::LocalInfer)  →  impl WorkerService
   │
   ▼  AnyWorker::execute  (eager match + Box::pin — D10)
LocalInferWorker::execute
   │  ① sync prologue: RegistrationGuard::try_acquire  (O1/O4)  ── async side ──
   │  ② Handle::current()
   ▼
tokio::task::spawn_blocking ─────────── executor boundary ───────────────────┐
   │                                                                          │
   │  ExecutionContext + C: ExecutionChannel  (by value, Send + 'static)      │
   ▼                                                            blocking pool │
run_off_executor                                                              │
   │  emit Progress("received")  ──┐                                          │
   ▼                               │                                          │
DeterministicEngine::generate      │ every emit:                              │
   │  token ──► ChannelSink::accept ── handle.block_on(channel.emit(event))   │
   │              │  then: ChannelClosed? → should_stop? → past deadline?     │
   │              ◄── SinkVerdict::{Continue, Stop}                           │
   ▼                                                                          │
emit MetricsSnapshot, EndOfStream; build ExecutionReport                      │
   └──────────────────────────────────────────────────────────────────────────┘
   │  JoinHandle resolves (panic → resume_unwind)
   ▼  guard dropped (O2, every path)
Result<ExecutionReport, WorkerError>
```

## File Changes

| File | Action | Description |
|---|---|---|
| `runtime/src/worker/local_infer/engine/mod.rs` | New | D4 subtree docs (tokio-free/sync-only rule), re-exports |
| `runtime/src/worker/local_infer/engine/port.rs` | New | D6 — `TextGenerationEngine`, `TokenSink`, `SinkVerdict`, `Token`, `GenerationRequest`, `EngineError` |
| `runtime/src/worker/local_infer/engine/reference.rs` | New | D7 — `DeterministicEngine` |
| `runtime/src/worker/local_infer/mod.rs` | New | D8/D9 — `LocalInferWorker`, `ChannelSink`, the sole `spawn_blocking` + `Handle::block_on` |
| `runtime/src/worker/any.rs` | New | D10 — `AnyWorker` |
| `runtime/src/worker/conformance.rs` | New | D11 — `#[cfg(test)]` harness + `worker_conformance_suite!` |
| `runtime/src/worker/registry.rs` | Modify | D9 — `should_stop` + unit test |
| `runtime/src/worker/mod.rs` | Modify | D10 — `WorkerKind`, `local_infer_worker()`, `any_worker()`, new `mod` declarations |
| `runtime/src/worker/in_process.rs` | Modify | D11 — fixtures move to `conformance.rs`; one macro invocation |
| `runtime/src/main.rs` | Modify | D10 — binds via `any_worker(WorkerKind::…)` |
| `runtime/tests/architecture_guard.rs` | Modify | D12 — `rust_files`, three scans, three token tables. **No table edits.** |
| `crates/runtime-worker/src/ports/worker_service.rs` | Modify | D10 — doc-sketch correction (eager match + box, O1 warning). Doc comment only |
| `docs/architecture/05-async-concurrency.md` | Modify | D5 — line 37, maintainer-approved wording |
| `openspec/specs/{worker-inbound-port,worker-inprocess-adapter,runtime-composition-root}/spec.md` + new `worker-local-infer-adapter` | Modify/New | Spec deltas — owned by `sdd-spec` |

`Cargo.toml` (workspace and `runtime`): **unchanged**. No new members, no new dependencies.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit — `engine/` | Determinism (same request → same bytes), `max_tokens` respected, `SinkVerdict::Stop` halts immediately, `cpu_spin_iterations` does not change output | Plain `#[test]`, no runtime, no fakes — the subtree is pure sync |
| Spike — first task of S2 | `Handle::block_on` inside `spawn_blocking` does not panic | ~20 lines; gates D8, Fallback A if it fails |
| Unit — `local_infer/mod.rs` | Full event sequence on a real `MpscExecutionChannel`; `Cancelled` / `Failed(duration)` phases; `ChannelClosed` mid-run is survivable; the sink's thread id differs from the test's | `#[tokio::test]` |
| Behavioral | Executor liveness; boundary backpressure | D11's two flavored tests |
| Conformance | O1-O4 × {`InProcessWorker`, `LocalInferWorker`, `AnyWorker::InProcess`, `AnyWorker::LocalInfer`} | D11's macro-emitted suite |
| Regression | `InProcessWorker`'s seven existing tests still pass, unmodified except the fixture import | `cargo test --workspace` |
| Guard | Three new containment scans; all existing guards unchanged and green | `runtime/tests/architecture_guard.rs` |
| Lint | `cargo clippy --all-targets -- -D warnings`; `unsafe_code = "deny"` holds | CI command |

## Migration / Rollout

Nothing persists, nothing is deployed, no wire contract moves. Rollback is `git revert` of S3 → S2 → S1 in order; reverting S3 alone restores `main.rs` to `in_process_worker()` and leaves the engine subtree dead but green. The `05-async-concurrency.md` edit rides in S3 with the dispatch and conformance work, so a single revert removes both the mechanism and the canon change describing it.

## Open Questions

- [ ] **Confirm at review**: `worker_service.rs`'s `Either`-based doc sketch is amended rather than left standing. Read literally it produces a lazy `async move` wrapper that breaks O1 at the dispatch layer (D10). The design's position is that a doc comment which misleads a future implementer about an obligation is a defect worth fixing in this change.
- [ ] **Named follow-up, not a blocker**: capability-keyed engine dispatch (`ExecutionContext::worker_capability()` → engine). Needs a representable failure for a capability miss, i.e. a new `WorkerError` variant and its spec delta (D6).
- [ ] **Named follow-up, not a blocker**: extract `local_infer/engine/` to its own crate when the llama.cpp bindings dependency arrives, and answer the crate-naming question then (D4).
- [ ] **Not a blocker, disclosed**: with D0-b, no `EXTERNAL_ALLOWED` row proves the engine is tokio-free — D12's source scans do. The proposal's original Intent #1 ("pressure-test the Golden Rule with a CPU-bound *crate*") is therefore only partially served; the boundary is proven, the crate-level isolation is deferred to the extraction follow-up.
