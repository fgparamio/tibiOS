# Design: Worker Composition Root — First Executable Slice

## Technical Approach

`runtime` is a **binary-only** crate (`[[bin]] path = "src/main.rs"`, no `src/lib.rs`). Every new item lives under a new `runtime/src/worker/` module tree declared from `main.rs`. `runtime-worker` stays free of tokio; `runtime` owns the executor, the concrete `ExecutionChannel`, and the concrete `WorkerService`, and exposes the latter only through a factory returning `impl WorkerService`.

Sections 1-3 below map one-to-one onto the proposal's three chained PR slices.

---

## Slice 1 — Dependency, Guard, Channel

### D1. `EXTERNAL_ALLOWED` edit (exact)

`runtime/tests/architecture_guard.rs:106`:

```rust
("runtime", &["tokio"]),
```

**No other guard in that file needs a parallel edit.** Verified against each:

| Guard | Needs edit? | Why |
|---|---|---|
| `ALLOWED` matrix | No | `runtime` is deliberately absent; `runtime_depends_on_all_domain_crates_without_violation` asserts that absence |
| `EXPECTED_MEMBERS` | No | No new workspace member; still 16 |
| `TRANSPORT_CRATES` | **No — must NOT be touched** | tokio is an async runtime, not transport. Adding it breaks `transport_dependencies_are_allowlisted_for_exactly_one_crate`, which asserts `owning_rows == vec!["runtime-worker"]` |
| `TRANSPORT_TOKENS` scans | No | Both walkers are rooted at `WORKER_SRC = "crates/runtime-worker/src"`. `runtime/src/**` is structurally outside their reach |
| `runtime_depends_on_all_domain_crates_without_violation` | No | Filters to workspace member names; `tokio` is external and filtered out |

`#[tokio::test]` needs **no** dev-dependency — tokio is already a normal dep with `macros`.

### D2. New guard: async runtime is single-owner

**Choice**: add the symmetric table-only guard, mirroring the transport one.

```rust
const ASYNC_RUNTIME_CRATES: &[&str] = &["tokio"];

#[test]
fn async_runtime_is_allowlisted_for_exactly_one_crate() { /* owning_rows == vec!["runtime"] */ }
```

**Alternatives**: rely on the prose spec delta; add a `tokio::` source-token scan across `crates/*/src`.
**Rationale**: directly mitigates the proposal's "normalizes editing the guard table" risk — turns a comment into a machine check. The token scan is redundant: the metadata allowlist already makes `tokio::` unreachable from any domain crate.

### D3. `MpscExecutionChannel` — `runtime/src/worker/channel.rs`

```rust
pub struct MpscExecutionChannel { sender: mpsc::Sender<ExecutionEvent> }

impl MpscExecutionChannel {
    pub const fn new(sender: mpsc::Sender<ExecutionEvent>) -> Self { Self { sender } }
}

impl ExecutionChannel for MpscExecutionChannel {
    fn emit(&self, event: ExecutionEvent)
        -> impl Future<Output = Result<(), ChannelClosed>> + Send
    { async move { self.sender.send(event).await.map_err(|_| ChannelClosed) } }
}
```

**Bounded**, not unbounded (`mpsc::channel(4)`): the demo emits 9+ events, so backpressure is exercised for real instead of decoratively. `SendError`'s payload is dropped — matching `ChannelClosed`'s documented "receiver is gone" semantics.

### D4. `ExecutionContext` accessors — the one deviation

**Discovered constraint**: `ExecutionContext` exposes exactly ONE accessor, `workload_id()`. A Worker literally cannot read its own inputs, so it cannot fill `ExecutionReport.trace_id` honestly.

**Choice**: add three accessor-only methods to `crates/runtime-worker/src/execution/context.rs` — `observability_context()`, `allocation_contract()`, `execution_parameters()`.
**Alternatives**: synthesize a fake trace_id (defeats "prove the port"); pass trace_id to the factory (wrong scope — per-execution, not per-worker).
**Rationale**: this IS the discovery the change exists to produce. Zero new deps, zero behavior change, no transport/tokio token, no guard impact (`adapters` identifier count unchanged). The proposal's success criterion "zero source changes" must be amended to "zero new dependencies, additive accessors only".

---

## Slice 2 — Worker Implementation and Factory

### D5. Module layout and factory signature

```
runtime/src/worker/mod.rs         pub fn in_process_worker() -> impl WorkerService   ← the ONLY namer of the concrete type
runtime/src/worker/channel.rs     MpscExecutionChannel                     (slice 1)
runtime/src/worker/in_process.rs  pub(super) struct InProcessWorker        (slice 2)
runtime/src/worker/registry.rs    pub(super) Registry, RegistrationGuard   (slice 2)
```

`in_process_worker()` takes **no arguments** — per-execution behavior comes from `ExecutionContext`, so there is nothing to configure. Edition 2024 RPIT capture rules mean no `use<>` is needed while the signature stays generic-free.

**Containment**: `InProcessWorker` is `pub(super)`, and `mod.rs` never re-exports it. `main.rs` (the crate root) therefore *cannot name it* — "no concrete worker type is named in the Composition Root's binding" becomes compiler-enforced, not review-enforced. The `runtime-worker` containment guards are irrelevant here because they only walk `crates/runtime-worker/src`; nothing in `runtime/src/` is ever scanned by them.

### D6. Synchronous registration (O1) + RAII deregistration (O2)

**Choice**: `execute` is **not** an `async fn`. Registration happens synchronously in the method body, before the returned future is ever polled; the guard is *constructed synchronously* and moved into the `async move` block.

```rust
fn execute<C>(&self, context: ExecutionContext, channel: C)
    -> impl Future<Output = Result<ExecutionReport, WorkerError>> + Send
where C: ExecutionChannel
{
    let workload_id = context.workload_id();
    // O1 + O4, both synchronous — before any suspension point exists.
    let acquired = RegistrationGuard::try_acquire(Arc::clone(&self.registry), workload_id);
    async move {
        let _guard = acquired.ok_or(WorkerError::DuplicateWorkload(workload_id))?;
        run_execution(context, channel, &_guard).await   // O2 via Drop, every path
    }
}
```

**Alternatives**: `async move { register(); ... }` (registration deferred to first poll — a `cancel` issued between `execute()` and the first `.await` is lost); explicit deregistration at each return site.
**Rationale**: the obligation is "before the first suspension point"; constructing the guard eagerly also covers the *never-polled-then-dropped* future, which no in-block `defer` can. Critical subtlety: on the `DuplicateWorkload` path `try_acquire` returns `None` **without** creating a guard — otherwise dropping it would deregister the *winner's* registration.

Machine-check for this decision: call `execute(..)` and, **without awaiting it**, assert `worker.cancel(id).await` is `Ok`. An `async fn` implementation fails this test.

### D7. Registry concurrency

**Choice**: one `Arc<Mutex<BTreeMap<WorkloadId, Registration>>>` (`std::sync::Mutex`, `Registration { phase, cancelled }`), accessed only through a `with_registry(|map| ..)` helper so no `MutexGuard` can cross an `.await`.
**Alternatives**: `tokio::sync::Mutex`; an actor task; per-entry `Arc<AtomicBool>`.
**Rationale**: every critical section is a few map operations with zero awaits — a std mutex is correct and cheaper. The rule is compiler-enforced for free: `MutexGuard` is `!Send`, so a guard held across an await makes the future non-`Send` and the trait bound fails to compile.

`cancel` and `pulse` compute their `Result` synchronously, then return `async move { result }`, keeping them trivially `Send`. `cancel` is idempotent while registered (O3: absent id ⇒ `UnknownWorkload`).

### D8. What "real work" means

Not a sleep, not a stub. Per execution, driven by `execution_parameters["output_chunks"]` (default 3):

1. `Progress { 0.0, "received" }`, phase → `Prepared` → `Running`
2. per chunk: `tokio::task::yield_now().await` (a genuine suspension that returns `Pending` once) → FNV-1a rolling checksum over bytes seeded from `workload_id` (data-dependent, not constant) → `emit(OutputChunk)` → `emit(Progress)` → check `cancelled` and `allocation_contract().max_execution_duration()` against `Instant::elapsed()`; on breach emit `Warning` and finish `Failed`
3. `emit(MetricsSnapshot)`, `emit(EndOfStream)`
4. return `ExecutionReport { final_phase, duration: start.elapsed(), trace_id: observability_context().trace_id(), summary }`

9 events against a capacity-4 channel ⇒ `emit` genuinely blocks on the receiver, so the wiring is proven by backpressure, not by assertion.

---

## Slice 3 — `main.rs` Wiring and Smoke

### D9. Drain concurrently with `tokio::spawn`, never `join!`

```rust
#[tokio::main]
async fn main() {
    let (sender, mut receiver) = mpsc::channel::<ExecutionEvent>(CHANNEL_CAPACITY);
    let channel = MpscExecutionChannel::new(sender);       // the ONLY Sender is moved in
    let worker = worker::in_process_worker();

    let drain = tokio::spawn(async move {
        let mut seen = 0usize;
        while let Some(event) = receiver.recv().await { println!("event: {event:?}"); seen += 1; }
        seen
    });

    let report = worker.execute(demo_context(), channel).await;   // channel dropped here
    let seen = drain.await.expect("drain task must not panic");
    println!("report: {report:?} ({seen} events)");
}
```

**Alternatives considered — `tokio::join!(execute, drain_loop)`: this DEADLOCKS.** `join!` pins both futures in place and does not drop the completed `execute` future until the whole macro returns; the `Sender` lives inside that future, so the channel never closes, `recv()` never yields `None`, and the drain branch never finishes. Spawning the drain and awaiting `execute` on the main task drops the channel at a well-defined point.

**Second load-bearing rule**: `main` must move the *only* `Sender` into `MpscExecutionChannel`. Keeping a clone hangs the program for the same reason.

Spawning the *drain* (not `execute`) also avoids forcing a `+ 'static` bound onto the factory's return type.

### D10. Smoke test without a lib target

**Choice**: keep `runtime` binary-only; `runtime/tests/smoke.rs` runs the built binary via `Command::new(env!("CARGO_BIN_EXE_runtime"))` and asserts stdout carries `EndOfStream` and a `Completed` report.
**Alternatives**: add `src/lib.rs` so `tests/` can import the modules.
**Rationale**: `tests/` integration tests cannot import a bin crate — but adding a lib target would make `runtime` importable and *weaken* the Golden Rule ("no crate may depend on `runtime`") from compiler-enforced to guard-enforced. Everything else is a `#[cfg(test)] mod tests` unit test inside its own module, which `cargo test --workspace` runs for bin targets. This also makes the e2e prove the actual `cargo run -p runtime` success criterion, not a library approximation.

---

## Data Flow

```
main (#[tokio::main])
  │ mpsc::channel(4) ──── Receiver ──> tokio::spawn(drain) ──> println!(event)
  │        └── Sender (moved, sole copy)
  │              └──> MpscExecutionChannel ──┐
  └──> in_process_worker() -> impl WorkerService
                 │ .execute(context, channel).await
                 ▼
          InProcessWorker
            ├─ RegistrationGuard::try_acquire   [sync: O1, O4]
            ├─ loop { yield_now → checksum → emit(OutputChunk) → emit(Progress) }  ← backpressure
            ├─ emit(MetricsSnapshot) → emit(EndOfStream)
            └─ Drop(guard) → deregister         [O2, every path]
                 │
                 ▼ ExecutionReport ──> println!   (channel dropped ⇒ recv() ⇒ None ⇒ drain ends)
```

## File Changes

| File | Action | Slice |
|---|---|---|
| `Cargo.toml` (workspace) | Modify | 1 — `tokio = { version = "1", features = ["rt-multi-thread","macros","sync"] }` |
| `runtime/Cargo.toml` | Modify | 1 — `tokio = { workspace = true }` |
| `runtime/tests/architecture_guard.rs` | Modify | 1 — D1 row + D2 guard |
| `crates/runtime-worker/src/execution/context.rs` | Modify | 1 — D4 accessors + their unit tests |
| `runtime/src/worker/mod.rs` | Create | 1 (skeleton) / 2 (factory) |
| `runtime/src/worker/channel.rs` | Create | 1 |
| `runtime/src/worker/registry.rs` | Create | 2 |
| `runtime/src/worker/in_process.rs` | Create | 2 |
| `runtime/src/main.rs` | Modify | 1 (`mod worker;`) / 3 (wiring) |
| `runtime/tests/smoke.rs` | Create | 3 |
| `openspec/specs/runtime-composition-root/spec.md` | Modify | 3 — retire "No Public Traits In This Change" |

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit — `channel.rs` | emit delivers; emit after receiver drop ⇒ `Err(ChannelClosed)`; capacity-1 backpressure pends until `recv` | `#[tokio::test]` |
| Unit — `in_process.rs` | **O1** `cancel` right after an unpolled `execute` ⇒ `Ok`; **O2** post-completion and post-drop-unpolled `cancel` ⇒ `UnknownWorkload`; **O3** unknown id on `cancel`/`pulse`; **O4** second `execute` ⇒ `DuplicateWorkload` while the first still deregisters | `#[tokio::test]` |
| Unit — `in_process.rs` | full event sequence reaches a real receiver; cancellation mid-run still returns a `Cancelled` report | `#[tokio::test]` + real `MpscExecutionChannel` |
| Integration | `cargo run -p runtime` prints an `EndOfStream` and a `Completed` report | `tests/smoke.rs` via `CARGO_BIN_EXE_runtime` |
| Guard | tokio allowlisted for exactly `runtime` | `async_runtime_is_allowlisted_for_exactly_one_crate` |

Run `cargo clippy --all-targets -- -D warnings` — a plain `--workspace` run silently skips `#[cfg(test)]` code.

## Migration / Rollout

No migration. Each slice compiles, tests, and reverts independently; full rollback returns `main.rs` to `fn main() {}`, drops both tokio entries, and restores `("runtime", &[])`.

## Open Questions

- [ ] D4 contradicts the proposal's "`runtime-worker` has zero source changes" success criterion. Design's position: amend the criterion to "zero new dependencies, additive accessors only". Needs sign-off before slice 1.
- [ ] Honest caveat: `runtime-worker` already pulls tokio *transitively* through `tonic`. The "no async runtime" property it claims is "names no tokio type / declares no tokio dependency", not "tokio is absent from the build graph". Worth stating plainly in the spec delta.
