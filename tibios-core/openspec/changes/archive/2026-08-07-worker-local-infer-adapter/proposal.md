# Proposal: Local Inference Worker — Module Boundary and Adapter Shape

> **No new crate.** `runtime-worker` already carries zero `tokio` (`runtime-composition-root/spec.md`), and a sync-only engine port + blocking pool + reference engine need none either — so there is no technical reason to isolate them in a separate crate. The engine lives in `runtime-worker`; the async boundary stays in `runtime`. This removes the naming-convention question, the guard's 17-member growth, the `Cargo.toml` member addition, and the `02-project-structure.md` layout amendment entirely.

> **⚠ One placement blocker — needs an `sdd-design` decision.** The directed path `crates/runtime-worker/src/adapters/local/` is **not reachable from `runtime`**. `lib.rs:8` declares `mod adapters;` *private*, `adapters/mod.rs:1-2` states "Nothing in this module tree is re-exported", and two guard tests machine-enforce it. See "D0 — Where the engine module actually goes".

## Intent

A local inference Worker is already named in four architecture docs (`05-async-concurrency.md:37`, `07-performance.md:93`, `25-ai-runtime.md:42`, `18-worker-model.md:132`) and the Worker port was *designed around it* — `channel` is taken by value and bounded `Send + 'static` specifically so it can be moved into its mandated `spawn_blocking` closure (`worker_service.rs:24-28,78-81`; `execution_channel.rs:9-13`). Nothing implements it.

Three things stay unproven until it exists:

1. The Golden Rule has never been tested against a **CPU-bound** implementation. `worker-inprocess-adapter` is pure async; a blocking thread pool is the first real pressure on "`runtime` is the sole crate permitted `tokio`".
2. The `AnyWorker` enum-dispatch recipe (`worker_service.rs:36-53`) is documented but **never exercised** — there is only one Worker.
3. The O1-O4 conformance harness was **deliberately deferred to this change** (`worker-inbound-port/design.md:227,409`: "named here so the `local-infer` change knows to build it rather than rediscover the obligations").

Success: a second, structurally different Worker exists; both pass one shared O1-O4 harness; the engine module is provably tokio-free.

## Scope

### In Scope

- A private engine module in `runtime-worker`: the inference-engine port (`TextGenerationBackend` analogue), a dedicated blocking thread pool, and **one deterministic reference engine** proving the pool. Zero `tokio`, zero `unsafe`, zero llama.cpp, zero new dependencies.
- `runtime/src/worker/local_infer.rs` (**unchanged from the prior draft**): `LocalInferWorker: WorkerService`, `pub(super)`, exposed only via `local_infer_worker() -> impl WorkerService`, owning `spawn_blocking` + `Handle::block_on(channel.emit(chunk))`, reusing the existing `pub(super) Registry` for O1-O4.
- `AnyWorker` enum dispatch in `runtime`, wiring both Workers behind one `impl WorkerService`.
- Shared O1-O4 conformance harness; `InProcessWorker` and `LocalInferWorker` both run through it.
- A guard scan proving the engine module names no `tokio::` path.
- Terminology amendment across four architecture docs: "crate" → "module", plus the `05-async-concurrency.md:37` rewording below.

### Out of Scope

- llama.cpp FFI, `candle`, model loading, tokenization, real inference, GPU/Metal.
- The `llama.cpp` vs `candle` benchmark (`07-performance.md:93`).
- Scheduling-side capability matching; any routing between Workers.
- Any new workspace crate, `Cargo.toml` member change, or guard member-count growth.

## Capabilities

### New Capabilities

- `worker-local-infer-adapter`: the `runtime`-side `WorkerService` implementation, its factory, and the blocking boundary.

### Modified Capabilities

- `runtime-worker`: adds the local engine module — its placement, visibility, containment, and tokio-free obligation.
- `worker-inbound-port`: adds the O1-O4 conformance-harness requirement (D11's deferred obligation).
- `runtime-composition-root`: adds the `AnyWorker` multi-Worker binding requirement.
- `worker-inprocess-adapter`: adds the requirement that it passes the shared harness.

## Approach

**Split at the blocking boundary, not the async boundary — and not at a crate boundary.**

| Piece | Owns | Forbidden |
|---|---|---|
| `runtime-worker` engine module | Engine port, thread pool, synchronous engine API | `tokio::`, `unsafe`, transport |
| `runtime/src/worker/local_infer.rs` | `spawn_blocking`, channel move, O1-O4, factory | naming the engine above the port |

### D0 — Where the engine module actually goes

`crates/runtime-worker/src/adapters/local/` cannot work as directed. The evidence:

- `lib.rs:8` — `mod adapters;`, with no `pub`. The tree is private to the crate.
- `adapters/mod.rs:1-2` — "Private adapter layer. Nothing in this module tree is re-exported."
- `runtime_worker_never_reexports_the_adapter_module` asserts the identifier `adapters` appears **exactly once** outside `src/adapters/` and that it is the literal `mod adapters;`. Making it `pub mod adapters;` fails the literal check; adding `pub use crate::adapters::local::…` fails the occurrence count. That test exists precisely to close "the `pub use crate::adapters::…` hole".

So `runtime` could never call `runtime_worker::adapters::local::…`. Two viable placements remain:

| Option | Shape | Cost |
|---|---|---|
| **D0-a (recommended)** | New public module `crates/runtime-worker/src/engine/`, sibling to `execution/` and `ports/` — *not* under `adapters/` | Keeps the engine in `runtime-worker` as directed; leaves the transport-containment guard untouched |
| **D0-b** | Engine submodules inside `runtime/src/worker/local_infer/` | Zero `runtime-worker` change at all; but puts the engine in the composition root |

D0-a preserves the directed intent. `adapters/` is reserved for transport containment (its guard, its doc comment, its `grpc` child all say so); a CPU-bound inference engine is not transport, so it does not belong there even setting reachability aside. **`sdd-design` must confirm D0-a or D0-b before spec work fixes the path.**

### D1 — The engine module exposes a blocking API; `runtime` makes it async

*(Approved by the maintainer.)* The candidate `futures::channel::oneshot` split was evaluated and **rejected as unnecessary**. `oneshot` *is* genuinely executor-agnostic, so the split would work — but it buys nothing here. `ExecutionChannel::emit` is `async`, and a blocking closure cannot `.await`; a oneshot carries one final value, whereas token-by-token generation is a *stream*. The shape the port was actually designed for is `spawn_blocking(move || { …; Handle::block_on(channel.emit(chunk)) })` — which is exactly why `channel` is by-value and `Send + 'static`. That keeps the engine module dependency-free rather than adding `futures-channel` where it is not needed.

The apparent conflict with `05-async-concurrency.md:37` ("the crate's own API is async at the boundary") is resolved by amending that line to exactly:

> The Runtime-facing boundary is asynchronous. Internal implementations may be synchronous provided they never block the Runtime executor.

### D2 — The engine choice stays inside the module

*(Approved by the maintainer.)* The engine port is private to the `runtime-worker` engine module, mirroring `tibios-ray`'s `LlamaCppTextBackend` / `TextGenerationBackend` (commit `a698aaf`). No engine name is reachable above the Worker abstraction — this is the `25-ai-runtime.md:120` anti-pattern ("a routing component choosing between Worker implementations") enforced structurally, not by review.

### D3 — `unsafe_code = "deny"` is preserved, not relaxed

*(Approved by the maintainer.)* `Cargo.toml:53-54` denies `unsafe_code` workspace-wide via `[lints] workspace = true`, and `runtime-worker` opts in. The follow-up FFI change MUST satisfy it by depending on an **external** bindings crate that owns the `unsafe` (as `runtime-worker` already delegates codegen to `prost`/`tonic`), never by relaxing the lint. Unaffected by the crate-to-module move either way.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `crates/runtime-worker/src/engine/` | New | Engine port, blocking pool, reference engine (path pending D0) |
| `crates/runtime-worker/src/lib.rs` | Modified | Declares the engine module |
| `runtime/src/worker/local_infer.rs` | New | `LocalInferWorker` |
| `runtime/src/worker/mod.rs` | Modified | `local_infer_worker()` factory, `AnyWorker` |
| `runtime/src/main.rs` | Modified | Binds via `AnyWorker` |
| `runtime/tests/architecture_guard.rs` | Modified | Adds a `tokio::` token scan over `runtime-worker/src`; **no** member-count or table growth |
| `docs/architecture/05-async-concurrency.md:37` | Modified | Reworded to the exact sentence in D1 |
| `docs/architecture/07-performance.md:93` | Modified | "the `local-infer` crate" → module |
| `docs/architecture/18-worker-model.md:132` | Modified | "crate" → module |
| `docs/architecture/25-ai-runtime.md:19,42` | Modified | "crate" → module; `:19` already says these belong to `runtime-worker`, which this change makes literally true |

Unchanged, explicitly: `Cargo.toml`, `docs/architecture/02-project-structure.md`, and the guard's `ALLOWED` / `EXTERNAL_ALLOWED` / `EXPECTED_MEMBERS` tables. Non-normative mentions (`README.md:63`, `proto/…/worker.proto`, `13-object-model.md:188`, `27-sdk.md:15`) are catalogued for `sdd-tasks`; archived artifacts under `openspec/changes/archive/` MUST NOT be rewritten.

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `adapters/local/` is unreachable from `runtime`; the directed path cannot compile | **Certain** | Documented in D0 with the two guard tests that enforce it. `sdd-design` picks D0-a (recommended) or D0-b before spec work. |
| `05-async-concurrency.md:37` semantic conflict with D1 | **Resolved** | Maintainer-approved replacement wording quoted verbatim in D1. |
| Crate naming convention | **Removed** | No new crate exists. |
| Guard member-count growth / `Cargo.toml` churn / layout amendment | **Removed** | No new crate exists. |
| The engine port becomes public API of `runtime-worker`, so the port crate now ships an implementation | Med | Tension with `02-project-structure.md`'s Ports/Adapters split and design D9's "the port crate depending on its own adapters" rejection. Mitigate by keeping the engine module's surface minimal and the reference engine `pub(crate)` wherever `runtime` does not need it. Revisit if the surface grows. |
| A dedicated thread pool inside the domain crate reads as a "hidden background thread" (`05-async-concurrency.md:125` anti-pattern) | Med | Pool is explicitly owned, bounded, and constructed only via the `runtime`-side factory — never spawned implicitly at module load. Cover with a test asserting no thread exists before the factory is called. |
| `Handle::block_on` inside `spawn_blocking` deadlocks if misused | Med | Only legal off-executor; `spawn_blocking` guarantees that. Cover with a backpressure test (bounded channel, more chunks than capacity). |
| A stub engine makes this a near-clone of `InProcessWorker` | Med | The value is the *boundary*, the `AnyWorker` recipe, and the harness — none of which exist today. Keep the reference engine deliberately trivial. |
| `25-ai-runtime.md:19` says AI Worker implementations "belong to `runtime-worker`" | **Resolved** | Under D0-a this becomes literally true rather than needing reinterpretation. |

## Rollback Plan

Fully additive; no crate, manifest, or guard-table change to unwind. Revert in order: delete the `runtime-worker` engine module and its `lib.rs` declaration; delete `runtime/src/worker/local_infer.rs`; revert `mod.rs` to the `in_process_worker()`-only factory and `main.rs` to binding it directly; drop the added guard scan; revert the four architecture-doc amendments. `runtime-worker`'s dependency list is untouched throughout. One `git revert` of the change's commits restores a green `cargo test`.

## Dependencies

- `worker-inbound-port` and `worker-inprocess-adapter` — both landed.
- No new external crates, and no new workspace-crate edges.

## Success Criteria

- [ ] `cargo test` green; guard member count and dependency tables **unchanged** at 16.
- [ ] `crates/runtime-worker/Cargo.toml` is byte-identical before and after.
- [ ] A token scan proves no `tokio::` path anywhere in `crates/runtime-worker/src/`.
- [ ] `unsafe_code = "deny"` holds workspace-wide; no crate opts out.
- [ ] One shared O1-O4 harness; both `InProcessWorker` and `LocalInferWorker` pass every obligation.
- [ ] `main.rs` names neither concrete Worker — only `AnyWorker` behind `impl WorkerService`.
- [ ] Inference runs on a non-executor thread, verified by a test asserting the executor is never blocked.
- [ ] No engine name (llama.cpp, candle) appears outside the engine module.
- [ ] `05-async-concurrency.md:37` reads exactly: "The Runtime-facing boundary is asynchronous. Internal implementations may be synchronous provided they never block the Runtime executor."
