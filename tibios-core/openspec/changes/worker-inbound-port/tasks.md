# Tasks: Worker Inbound Port (the Worker domain's public language)

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines (total, all slices) | **~1,350**, refined down from design.md's ~1,600. Breakdown: S0 (`architecture_guard.rs` comment-skip fix) ~40; S1 (`Classify` + `convert.rs` cleanup) ~100; S2 (`AllocationContract`) ~100; S3a (context family) ~250; S3b (event/report family + `WorkerError`) ~360; S4 (ports + zero-infrastructure integration test) ~280; S5a (`convert.rs` retarget) ~200; S5b (spec confirmation + full-workspace gate) ~20. |
| Why the estimate dropped from design.md's ~1,600 | Design.md's S5b assumed ~250 lines of **spec authoring** (`runtime-worker`, `runtime-allocation`, `runtime-primitives`, `worker-wire-adapter` deltas + the new `worker-inbound-port` capability). Direct inspection of `openspec/specs/{runtime-worker,runtime-allocation,runtime-primitives,worker-wire-adapter,worker-inbound-port}/spec.md` at task-planning time shows **all five are already fully written**, matching D9-D12 exactly (`Classify` already public, `AllocationContract` already defined with the single `max_execution_duration` field, `ExecutionPhase`'s six-variant/no-`Default` requirement already stated, the `worker-inbound-port` capability already carries all five cross-cutting requirements). This project's `sdd-spec` phase runs **after** `sdd-design` (the orchestrator's DAG: `design -> specs -> tasks`), so by the time `sdd-tasks` runs, spec authoring is already done — S5b's real remaining work is confirmation-only, exactly the pattern the prior change's tasks.md used for its own spec deltas ("Already modified in sdd-spec — no new edits needed, confirmation only"). |
| New slice not in D12 | **S0** — a fix to `runtime/tests/architecture_guard.rs`'s `runtime_worker_never_reexports_the_adapter_module` test, discovered as a Gotcha in design.md (not present in D12's seven-slice table): that test does not skip comment lines before scanning for the `adapters` identifier, unlike its sibling transport-token scan. This change adds substantial new public source under `runtime-worker/src/`, where a doc comment mentioning "adapters" in prose is newly plausible (S3a, S3b, S4 all add files there). Independent, ~40 lines, zero dependencies — added as its own slice so the fix lands before any new `src/` file is authored, not discovered as a CI false-positive mid-slice. |
| 400-line budget risk | **High**, unchanged from design.md's verdict. S3b (~360) is the largest single slice and the one to watch — design.md's own pre-agreed sub-split (`ExecutionEvent` + its six payloads / everything else) applies unchanged if it drifts past 400 during apply. |
| Chained PRs recommended | **Yes** — mandatory, not advisory (design.md D12). **Eight** slices now (seven from D12 plus S0), none exceeding ~360 lines. |
| Decision needed before apply | **Yes.** `delivery_strategy` is `ask-on-risk` — the orchestrator must ask the user: (a) accept eight chained PRs as scoped below, or (b) record a maintainer-approved `size:exception` and ship fewer, larger PRs. This mirrors the prior `worker-grpc-adapter` change's own resolution of the same guard. |
| Delivery strategy | `ask-on-risk` (cached) — **triggered**, see above |

---

## Sequencing Notes

Four waves, matching design.md D12 with S0 inserted ahead of Wave 2:

```
Wave 1:  S0 ∥ S1 ∥ S2
Wave 2:  S3a ∥ S3b      (both should land after S0; S3a depends on S2, S3b depends on S1)
Wave 3:  S4 ∥ S5a       (both depend on S3a + S3b)
Wave 4:  S5b            (depends on S4 + S5a)
```

- **S0** has no dependency on anything and blocks nothing structurally, but should be merged before S3a/S3b begin authoring new `src/` files, since it is the fix that prevents a false-positive CI failure the moment a doc comment in a new module mentions "adapters" in prose. It is independently mergeable and independently revertible.
- **S1** and **S2** remain independently mergeable exactly as the proposal promised: each touches one crate, each is ~100 lines, each is consumed only by code introduced later in this same change (proposal.md Risks table).
- **S3a** (context family: `ExecutionContext`, `ResolvedDependency`, `SecurityContext`, `ObservabilityContext`) depends on S2 for `AllocationContract`, and on nothing else.
- **S3b** (event/report family: `ExecutionEvent` + six payloads, `ExecutionReport`, `ExecutionPhase`, `ExecutionPulse`, `CancelAck`, `WorkerError`) depends on S1 for `Classify`, and on nothing else. S3a and S3b touch disjoint files (`execution/context.rs` vs. `execution/{event,report}.rs` + `error.rs`) and can be authored, reviewed, and merged in parallel.
- **S4** (`ports/` + the zero-infrastructure integration test) depends on both S3a and S3b — `execute`'s signature names `ExecutionContext` (S3a) and returns `ExecutionReport`/`WorkerError` (S3b); `emit` takes `ExecutionEvent` (S3b).
- **S5a** (`convert.rs` retarget) depends on both S3a and S3b for the same reason, but **not on S4** — `convert.rs` converts data, never `WorkerService` or `ExecutionChannel`. S4 and S5a can be authored, reviewed, and merged in parallel once Wave 2 lands, which is what turns a five-wave chain into four.
- **S5b** is confirmation-and-gate only: it depends on every prior slice being merged, since it re-reads the already-final spec text and diffs it against the shipped surface, then runs the full-workspace check (`cargo fmt --check`, `cargo clippy --workspace -- -D warnings`, `cargo test --workspace`).
- Two natural stopping points exist where the tree is coherent and shippable: after Wave 1 (guard fixed, two independently-owned data contracts landed, nothing yet depends on them) and after Wave 3 (the port exists and is proven testable; only the confirmation gate remains) — same shape design.md D12 already identified.

---

## S0 — `architecture_guard.rs`: fix the comment-blind `adapters`-identifier scan

*(no dependencies; independently mergeable; should land before S3a/S3b)*

- [x] 0.1 In `runtime/tests/architecture_guard.rs`, update `runtime_worker_never_reexports_the_adapter_module` (~line 507-540) to skip comment lines the same way `runtime_worker_transport_types_stay_inside_the_private_adapter_module` (~line 479-481) already does: `if line.trim_start().starts_with("//") { continue; }` before calling `contains_identifier(line, "adapters")`.
- [x] 0.2 Extract the per-line classification (comment-skip + `contains_identifier` call) into a small, directly-unit-testable helper if it is not already trivially testable inline, and add a `#[test]` proving a synthetic line like `"/// converted in the adapters/ tree, see docs"` is now correctly ignored, while the literal `"mod adapters;"` line is still counted.
- [x] 0.3 Update the test's doc comment (~line 502-506) to state the comment-skip behavior now matches the transport-token scan, for symmetry — reference this task's rationale (a doc comment in a new public module mentioning "adapters" in prose must not trip the guard).
- [x] 0.4 Self-review: `cargo test -p runtime --test architecture_guard` passes; confirm the existing exactly-one-occurrence assertion still holds unchanged against the current (unmodified) `runtime-worker/src/` tree, i.e. this is a pure false-positive fix with zero change in verdict on today's code.

---

## S1 — `Classify` Public In `runtime-primitives`; Retire The Private Copy

*(no dependencies; independently mergeable; satisfies `runtime-primitives/spec.md` — "Classify Trait Is Public"; design.md D-carried-forward)*

- [x] 1.1 In `crates/runtime-primitives/src/error.rs`, add `pub trait Classify { fn classify(&self) -> ErrorClass; }` with a doc comment citing `04-error-handling.md:146`. Remove the module doc comment's "no public traits in this change" deferral language (`:4-6`), replacing it with a statement that `Classify` is now defined here and is the explicit follow-up the deferral promised.
- [x] 1.2 Export `Classify` from `crates/runtime-primitives/src/lib.rs`'s public API (alongside the existing `pub use error::ErrorClass;`).
- [x] 1.3 Add a unit test in `error.rs`'s existing `#[cfg(test)] mod tests`: a minimal local test type implementing `Classify`, exercised for each `ErrorClass` variant, confirming the trait's single-method shape is usable exactly as documented.
- [x] 1.4 In `crates/runtime-worker/src/adapters/grpc/convert.rs`, delete the private `trait Classify` (`:77-79`) and its `impl Classify for ConversionError` (`:81-91`); replace with `impl runtime_primitives::Classify for ConversionError`, preserving every match arm and its `ErrorClass::Permanent` result verbatim.
- [x] 1.5 Update `convert.rs`'s module doc comment (`:1-17`) to drop the "no public traits yet" framing it references implicitly through its own private-copy comment; update the `#[cfg(test)] mod tests` import (`:258`) from `super::Classify` to `runtime_primitives::Classify`.
- [x] 1.6 Self-review: grep `crates/runtime-worker/src` for `trait Classify` and confirm zero matches; run `cargo test -p runtime-worker --lib` and confirm `every_conversion_error_variant_classifies_permanent` and every other existing `convert.rs` test still passes with unchanged assertions (only the `impl` target changed, not the behavior).
- [x] 1.7 Confirm no new external dependency: `runtime-primitives`'s allowlist stays `{serde, ulid}` (`Classify` needs neither); `runtime-worker` needed no new dependency (it already depends on `runtime-primitives`).
- [x] 1.8 Confirmation-only: `openspec/specs/runtime-primitives/spec.md`'s "Classify Trait Is Public" requirement (already committed) is read against the shipped trait shape — exact method signature, exact crate, exact "no private copy remains" scenario. No spec edit expected; if a mismatch is found, treat the spec as normative and reconcile the code, not the other way around.

---

## S2 — `AllocationContract` In `runtime-allocation`

*(no dependencies; independently mergeable; satisfies `runtime-allocation/spec.md` — "AllocationContract Is A Public Data Contract, Intentionally Partial")*

- [x] 2.1 In `crates/runtime-allocation/src/lib.rs`, define `pub struct AllocationContract { max_execution_duration: core::time::Duration }` (private field) with a public constructor (`pub fn new(max_execution_duration: core::time::Duration) -> Self`) and a public accessor (`pub fn max_execution_duration(&self) -> core::time::Duration`). Derive `Debug, Clone, Copy, PartialEq, Eq`.
- [x] 2.2 Doc comment on `AllocationContract`: cites `02-project-structure.md`'s Ownership Boundaries table (`Allocation -> AllocationContract -> Worker`), states the struct is **intentionally partial** pending `15-allocation-model.md`'s own future change, and names the five deferred facets (exclusive/shared, renewable lease, preemptible, migration allowed, checkpoint required).
- [x] 2.3 Confirm the crate doc comment still cites `15-allocation-model.md` (existing requirement, unchanged) and that no public trait is declared alongside `AllocationContract` in this file.
- [x] 2.4 Add a `#[cfg(test)] mod tests` block: constructor + accessor round-trip; `Clone`/`Copy`/`PartialEq`/`Eq` semantics hold for two equal and two differing `Duration` values.
- [x] 2.5 Self-review: `crates/runtime-allocation/Cargo.toml`'s `[dependencies]` table is unchanged (still empty — `core::time::Duration` needs no crate); `cargo check -p runtime-allocation` succeeds.
- [x] 2.6 Confirmation-only: `openspec/specs/runtime-allocation/spec.md`'s "AllocationContract..." requirement (already committed) matches the shipped struct's single field, its doc-commented partiality statement, and the "no behavior beyond trivial constructors/accessors" scenario. No spec edit expected.

---

## S3a — Context Family (`ExecutionContext`, `ResolvedDependency`, `SecurityContext`, `ObservabilityContext`)

*(depends on S2; satisfies `runtime-worker/spec.md`'s "ExecutionContext Is Immutable Data..." and `worker-inbound-port/spec.md`'s "ExecutionContext Carries No Channel And No Cancellation Signal"; design.md D10)*

- [ ] 3a.1 Create `crates/runtime-worker/src/execution/mod.rs` with `pub mod context;` — leave room for S3b to add its own `pub mod event; pub mod report;` lines without conflict (each slice adds only the line(s) it owns).
- [ ] 3a.2 Create `crates/runtime-worker/src/execution/context.rs`. Define `ResolvedDependency` (public struct: `object_id: runtime_primitives::ObjectId`, `object_version: runtime_primitives::ObjectVersion`, `content_hash: runtime_primitives::ContentHash`) mirroring the wire `ResolvedModelRef` field-for-field; doc comment cites proposal Decision #1 ("a resolved reference is not an `Object`") and `18-worker-model.md:52`.
- [ ] 3a.3 Define `SecurityContext` exactly per design.md D9/D10's shape: private fields `tenant_id: String, principal_id: String, grant_scope: Vec<String>`; public constructor; accessors `tenant_id(&self) -> &str`, `principal_id(&self) -> &str`, `grant_scope(&self) -> &[String]`. Doc comment states every field is **carried, never interpreted**, cites `18-worker-model.md:136` and `20-admission-control.md:47` for why the Worker never branches on them, and names `runtime-security` as the future owner of the whole envelope (D10 Consequences — re-typing happens as one unit, not field-by-field).
- [ ] 3a.4 Define `ObservabilityContext` (public struct: `trace_id: String, span_id: String`), doc comment citing `09-observability.md:47` and stating the message wins over any transport-derived header if the two disagree.
- [ ] 3a.5 Define `ExecutionContext`: `workload_id: runtime_primitives::WorkloadId`, `allocation_id: runtime_primitives::AllocationId`, `allocation_contract: runtime_allocation::AllocationContract`, `dependencies: Vec<ResolvedDependency>`, `security_context: SecurityContext`, `observability_context: ObservabilityContext`, `execution_parameters: std::collections::BTreeMap<String, String>` (D10 Consequences — `BTreeMap`, not `HashMap`, for determinism per `18-worker-model.md:13`). Derive `Debug, Clone, PartialEq`; provide a public constructor and a `workload_id(&self) -> WorkloadId` accessor (needed by S4's O1-O4 registry logic).
- [ ] 3a.6 Verify by construction (no field of any kind added for it): `ExecutionContext` contains no `ExecutionChannel`/channel/sender field and no cancellation-token/flag field — satisfied structurally, confirmed by code review since this is not runtime-assertable.
- [ ] 3a.7 Doc comment on every public item in this file (`missing_docs = "warn"` + `clippy -D warnings` requires it).
- [ ] 3a.8 Unit tests in `context.rs`'s `#[cfg(test)] mod tests`: `ExecutionContext` constructs from plain values in a handful of lines and satisfies `Clone`/`PartialEq`; `SecurityContext`'s accessors return the carried strings verbatim (D10); a round-trip through `Clone` produces an equal value.
- [ ] 3a.9 Update `crates/runtime-worker/src/lib.rs`: add `pub mod execution;`, re-export `ExecutionContext`, `ResolvedDependency`, `SecurityContext`, `ObservabilityContext`. Update the crate doc comment to drop "Stub for the Worker domain" (coordinate with S3b/S4 — whichever slice lands second finishes this edit without reverting the first's re-exports).
- [ ] 3a.10 Self-review against S0's fixed guard: no doc comment in this file uses the plural word "adapters" — write "the private adapter module" if the concept needs naming (design.md Gotchas).

---

## S3b — Event/Report Family (`ExecutionEvent`, `ExecutionReport`, `ExecutionPhase`, `ExecutionPulse`, `CancelAck`, `WorkerError`)

*(depends on S1; satisfies `runtime-worker/spec.md`'s "ExecutionEvent Is A Closed Six-Arm Enum" and "ExecutionPhase Has Exactly Six States And No Placeholder"; `runtime-primitives/spec.md`'s "WorkerError implements Classify"; design.md D11 Consequences)*

- [ ] 3b.1 Extend `crates/runtime-worker/src/execution/mod.rs` with `pub mod event; pub mod report;` (additive alongside S3a's `pub mod context;`).
- [ ] 3b.2 Create `crates/runtime-worker/src/execution/event.rs`: six Worker-owned payload structs — `OutputChunk { data: Vec<u8>, sequence: u64 }`, `Progress { fraction_complete: f64, message: String }`, `Warning { message: String }`, `CheckpointCreated { checkpoint_object_id: runtime_primitives::ObjectId }`, `MetricsSnapshot { metrics: std::collections::BTreeMap<String, f64> }` (D10 Consequences — `BTreeMap`, not `HashMap`), `EndOfStream` (unit struct). Never the generated wire structs (Carried Forward — this is precisely the private-mirror debt this change retires).
- [ ] 3b.3 Define `ExecutionEvent` as a closed 6-arm enum wrapping the six payloads one-to-one: `OutputChunk(OutputChunk)`, `Progress(Progress)`, `Warning(Warning)`, `CheckpointCreated(CheckpointCreated)`, `MetricsSnapshot(MetricsSnapshot)`, `EndOfStream(EndOfStream)`.
- [ ] 3b.4 Create `crates/runtime-worker/src/execution/report.rs`: `ExecutionPhase` — exactly six variants `Received, Prepared, Running, Completed, Failed, Cancelled`; no `Unspecified`/`Unknown`/placeholder variant; do **not** implement `Default` for it.
- [ ] 3b.5 Define `ExecutionReport { final_phase: ExecutionPhase, duration: core::time::Duration, trace_id: String, summary: String }`.
- [ ] 3b.6 Define `ExecutionPulse { phase: ExecutionPhase, healthy: bool }`.
- [ ] 3b.7 Define `CancelAck` as a named unit struct (`pub struct CancelAck;`, not `()`), doc comment mirroring `worker.proto:213-220`'s "accepted, not terminated" semantics and its evolvability rationale.
- [ ] 3b.8 Create `crates/runtime-worker/src/error.rs`: `WorkerError` enum with, at minimum, `UnknownWorkload(runtime_primitives::WorkloadId)` and `DuplicateWorkload(runtime_primitives::WorkloadId)` (D11 Consequences — both classify `Permanent`). Doc comment on the enum states, verbatim in spirit: "The Worker classifies the nature of the failure; the Runtime decides what to do about it" (D11 Rationale) — so `Classify` becoming public does not read as the Worker prescribing recovery policy.
- [ ] 3b.9 `impl runtime_primitives::Classify for WorkerError` — `UnknownWorkload` and `DuplicateWorkload` both return `ErrorClass::Permanent` (a Worker cannot distinguish "never existed" from "already completed"; `Transient` would invite an infinite retry loop against a workload that finished successfully).
- [ ] 3b.10 `impl core::fmt::Display for WorkerError` (hand-written, no `thiserror`, matching the `ConversionError`/`IdentityParseError` precedent already in the codebase).
- [ ] 3b.11 On `execute`/`cancel`/`pulse`'s eventual home (`ports/worker_service.rs`, authored in S4) will carry the full O1-O4 doc comments; here, document on `WorkerError::UnknownWorkload`/`DuplicateWorkload` themselves the concrete obligation each variant enforces (O3: unregistered id -> `UnknownWorkload`; O4: already-registered id at a new `execute` call -> `DuplicateWorkload`, without starting a second execution) — design.md D11.
- [ ] 3b.12 Doc comment on every public item added in this slice.
- [ ] 3b.13 Unit tests: an exhaustive `match` over `ExecutionEvent`'s variants in a `#[cfg(test)]` fn (a seventh arm added later breaks the build, per the Testing Strategy table); an exhaustive `match` over `ExecutionPhase`'s variants likewise; `WorkerError::classify()` returns the documented `ErrorClass` for every variant, mirroring `convert.rs`'s existing `every_conversion_error_variant_classifies_permanent` pattern; confirm (by code review, not a runtime assertion) that `ExecutionPhase` implements no `Default`.
- [ ] 3b.14 Update `crates/runtime-worker/src/lib.rs`: re-export `ExecutionEvent`, `OutputChunk`, `Progress`, `Warning`, `CheckpointCreated`, `MetricsSnapshot`, `EndOfStream`, `ExecutionReport`, `ExecutionPhase`, `ExecutionPulse`, `CancelAck`; add `mod error;` and re-export `WorkerError`. Coordinate with S3a's edit to the same file (additive, disjoint re-export lists).
- [ ] 3b.15 Self-review against S0's fixed guard: no doc comment in this slice's files uses the plural word "adapters"; `cargo clippy -p runtime-worker -- -D warnings` is clean for the files this slice owns.

---

## S4 — `ports/` (`WorkerService`, `ExecutionChannel`, `ChannelClosed`) And The Zero-Infrastructure Integration Test

*(depends on S3a and S3b; satisfies `runtime-worker/spec.md`'s "WorkerService..." and "ExecutionChannel..." requirements, and all five `worker-inbound-port/spec.md` requirements end-to-end; design.md D9, D11)*

- [ ] 4.1 Create `crates/runtime-worker/src/ports/mod.rs`, `worker_service.rs`, `execution_channel.rs`. Define `ExecutionChannel: Send + 'static` with `fn emit(&self, event: ExecutionEvent) -> impl core::future::Future<Output = Result<(), ChannelClosed>> + Send;` — RPITIT with an explicit `+ Send` bound, not bare `async fn` (D9).
- [ ] 4.2 Define `WorkerService: Send + Sync` (deliberately **without** `'static` — D9 Rationale, "the port states what the contract requires; the wiring states what its storage requires") with three methods, each RPITIT + `Send`:
  - `fn execute<C>(&self, context: ExecutionContext, channel: C) -> impl Future<Output = Result<ExecutionReport, WorkerError>> + Send where C: ExecutionChannel;` — generic over `C`, taken **by value** (D9 — required for `local-infer`'s mandated `spawn_blocking` move).
  - `fn cancel(&self, workload_id: WorkloadId) -> impl Future<Output = Result<CancelAck, WorkerError>> + Send;`
  - `fn pulse(&self, workload_id: WorkloadId) -> impl Future<Output = Result<ExecutionPulse, WorkerError>> + Send;`
- [ ] 4.3 Doc comment on `WorkerService` states, explicitly: the trait is permanently `dyn`-incompatible because `execute` is generic (independent of the async question); the Composition-Root recipe for runtime selection (`enum AnyWorker { .. }` with a hand-written `impl WorkerService for AnyWorker` matching in each method, defined in `runtime/`, zero changes required here); that a boxing/type-erasure wrapper remains available in the Composition Root if ever needed (D9 Consequences) — so the next reader finds the answer, not the obstacle.
- [ ] 4.4 Doc comments on `execute`, `cancel`, `pulse` state D11's four obligations verbatim in spirit: **O1** — a Worker MUST register `context.workload_id()` before the first suspension point in `execute`, so a `cancel` issued immediately after `execute` is called is never lost; **O2** — a Worker MUST deregister before `execute` returns, on every path (success, failure, cancellation); **O3** — `cancel`/`pulse` for an unregistered `WorkloadId` MUST return `WorkerError::UnknownWorkload`; **O4** — `execute` for an already-registered `WorkloadId` MUST return `WorkerError::DuplicateWorkload` without starting a second execution. State explicitly that the port mandates the obligation and **not** the mechanism (`02-project-structure.md:194` — "Ports never expose implementation details"); an actor, a `Mutex`-guarded map, or (for `tibios-ray`) forwarding to the remote process's own bookkeeping are all conforming.
- [ ] 4.5 Doc comment on `cancel` states it is **idempotent** while the execution is registered (a second `cancel` returns `CancelAck` again), and that `CancelAck` means "request accepted", never "execution terminated" (mirrors `worker.proto:213-220`).
- [ ] 4.6 Define `ChannelClosed` in `execution_channel.rs` — a tiny, doc-commented error type (hand-written `Display`, no `thiserror`) meaning the Runtime's `Receiver` is gone; doc comment states the Worker still owes an `ExecutionReport` via `execute`'s return value, so a closed channel never prevents reporting (D9 Consequences).
- [ ] 4.7 Add `impl From<ChannelClosed> for WorkerError` in `crates/runtime-worker/src/error.rs` (extends S3b's file; additive, no conflict with 3b.8-3b.10's content) for the case where a Worker chooses to abort after a failed `emit`.
- [ ] 4.8 Update `crates/runtime-worker/src/lib.rs`: add `pub mod ports;`, re-export `WorkerService`, `ExecutionChannel`, `ChannelClosed`. This is the slice that should finish dropping "Stub for the Worker domain" from the crate doc comment if S3a/S3b have not already (coordinate to avoid a redundant edit).
- [ ] 4.9 Create `crates/runtime-worker/tests/port_is_testable_without_infrastructure.rs` (an **integration** test — outside `#[cfg(test)]` — so it can only reach the crate's public API, per design.md's own rationale). Implement:
  - `RecordingChannel` — a newtype over `std::sync::mpsc::Sender<ExecutionEvent>`, `Send + 'static`; `emit` always returns `Ready(Ok(()))` immediately (an unbounded `std` send never blocks, so the fake never pends).
  - `poll_to_completion` — a ~12-line helper built from `core::task::Waker::noop()` (stable since 1.85; pinned toolchain is 1.93) + `core::pin::pin!` + a bounded poll-count loop that panics with a message naming the cause ("the fake channel must never pend") if the cap is exceeded, rather than hanging.
  - `EchoWorker` — a test-only `impl WorkerService`, with an internal registry (interior-mutable, e.g. `std::sync::Mutex<std::collections::HashSet<WorkloadId>>`) that registers `context.workload_id()` before emitting anything (O1) and deregisters before returning on every path (O2).
- [ ] 4.10 Integration test `execute_runs_to_completion_with_fake_context_and_in_memory_channel`: build an `ExecutionContext` by hand (D10 opaque `SecurityContext` strings, `BTreeMap` `execution_parameters`, a real `AllocationContract` from S2), drive `EchoWorker::execute` to completion via `poll_to_completion`, assert the events recorded by `RecordingChannel`'s `Receiver` (`try_iter().collect()`) are in the expected order, and assert `final_phase == ExecutionPhase::Completed`. Satisfies `worker-inbound-port/spec.md`'s "execute runs against a fake context and an in-memory channel with zero runtime, zero transport, zero I/O" scenario.
- [ ] 4.11 Integration test `pulse_returns_unknown_workload_after_execute_completes`: after 4.10's execution completes, call `pulse(workload_id)` on the same `EchoWorker` and assert `Err(WorkerError::UnknownWorkload(_))` — the concrete, observable assertion for O2 (design.md D9 Consequences: "O1/O2 are observable from outside the Worker... That turns D11's obligations into assertions rather than documentation").
- [ ] 4.12 Integration test `cancel_and_pulse_reject_an_unregistered_workload`: a fresh `EchoWorker` (nothing ever executed), call `cancel(random_id)` and `pulse(random_id)` and assert both return `Err(WorkerError::UnknownWorkload(_))` — O3, and satisfies `worker-inbound-port/spec.md`'s "cancel and pulse run under the same constraints" scenario using only fakes and test doubles.
- [ ] 4.13 Integration test `cancel_is_idempotent_while_registered` (O1 + cancel idempotency, D11 Decision): this needs a fixture that genuinely yields `Poll::Pending` at least once — `RecordingChannel`'s always-`Ready` `emit` cannot demonstrate a live in-flight registration window. Use a small, hand-rolled `Future` (a counter that returns `Pending` exactly once before completing) distinct from the happy-path fixture, poll `execute` once to land inside the registration window, call `cancel` twice from the test body and assert `Ok(CancelAck)` both times, then resume polling to completion. **Flag for `sdd-apply`:** the exact fixture shape is an implementation choice, not prescribed here — this is the single highest-friction task in S4.
- [ ] 4.14 Optional, include only if 4.13's fixture makes it a small addition: `execute_rejects_a_duplicate_in_flight_workload_id` (O4), using the same yielding-fixture technique — start one execution, poll it once (still registered), call `execute` again with the same `workload_id`, assert `Err(WorkerError::DuplicateWorkload(_))` without a second execution having started. If omitted here, note explicitly that the `local-infer` change's own conformance harness (D11 Consequences — "deliberately unbuilt here") is where O4 gets its first real exercise.
- [ ] 4.15 Self-review: `cargo test -p runtime-worker` (unit + integration) is green; grep the new integration test file for `tokio::`, `async-trait`, `futures::` and confirm none; confirm `crates/runtime-worker/Cargo.toml` gained **no** new dependency (D9 — `Cargo.toml` and `EXTERNAL_ALLOWED` are "Not modified", full stop); `cargo clippy -p runtime-worker -- -D warnings` is clean.

---

## S5a — `convert.rs` Retarget: Delete Mirrors, `TryFrom` Targets Real Domain Types

*(depends on S3a and S3b, not on S4; satisfies `worker-wire-adapter/spec.md`'s "Conversions Target Real Domain Types, No Local Mirror Remains" and preserves every prior scenario in that spec)*

- [ ] 5a.1 Delete `ExecutionEventArm` (`convert.rs:207-215`) and its `TryFrom` impl (`:217-233`). Retarget: `TryFrom<worker_proto::ExecutionEvent> for runtime_worker::execution::event::ExecutionEvent` (or the crate-internal path, since this file lives inside `runtime-worker`), matching all six arms exhaustively. Each payload conversion: `OutputChunk`, `Progress`, `Warning`, `MetricsSnapshot`, `EndOfStream` are infallible (`From`); `CheckpointCreated` stays fallible (`TryFrom`, since it resolves a required `ObjectId`).
- [ ] 5a.2 Delete local `CheckpointCreated` (`:179-200`) and its impl. Retarget `TryFrom<worker_proto::CheckpointCreated> for runtime_worker::execution::event::CheckpointCreated` (the real domain payload from S3b), preserving the `MissingField("checkpoint_object_id")` rejection verbatim.
- [ ] 5a.3 Delete `ExecutionResponseArm` (`:236-240`) and its impl (`:242-254`). The domain has **no** `ExecutionResponse`-shaped type (D10 Consequences — the Report travels as `execute`'s return value, not the channel), so this boundary's own routing type (an adapter-local enum distinguishing "this frame is an event" vs. "this frame is the terminal report") is genuinely adapter-only, not a mirror of any domain type — confirm this reading does not trip `worker-wire-adapter/spec.md`'s "no local mirror type" requirement (that requirement is scoped to types that duplicate a domain type's shape; there is no domain `ExecutionResponse` to duplicate). **Flag for `sdd-apply`:** the exact output shape of this routing step (a small enum vs. two independent `TryFrom` impls consumed separately) is an implementation choice; either satisfies the spec.
- [ ] 5a.4 Add `TryFrom<worker_proto::ExecutionPhase> for runtime_worker::execution::report::ExecutionPhase` — exhaustive match over the six mapped values; wire `EXECUTION_PHASE_UNSPECIFIED` (proto value `0`) is rejected with a new `ConversionError` variant, classified `Permanent` (satisfies `runtime-primitives/spec.md`'s "An unset wire ExecutionPhase classifies Permanent" scenario).
- [ ] 5a.5 Add a `google.protobuf.Duration -> core::time::Duration` conversion helper: negative `seconds`/`nanos` is rejected with a new `ConversionError::NegativeDuration` variant, classified `Permanent` (Carried Forward — `core::time::Duration` cannot represent negative values, and `google.protobuf.Duration` permits them). Used by both `AllocationContract.max_execution_duration` and `ExecutionReport.duration`.
- [ ] 5a.6 Add `TryFrom<worker_proto::AllocationContract> for runtime_allocation::AllocationContract`. A missing (`None`) `allocation_contract` at the containing message level is a `Permanent` rejection, not a default (Carried Forward — a Worker with no contract can enforce nothing).
- [ ] 5a.7 Add `TryFrom<worker_proto::ResolvedModelRef> for runtime_worker::execution::context::ResolvedDependency`.
- [ ] 5a.8 Add `From<worker_proto::SecurityContext> for runtime_worker::execution::context::SecurityContext` — infallible per D10 (verbatim carry: no ULID parse, no non-empty check, no normalization on any of the three fields).
- [ ] 5a.9 Add `From<worker_proto::ObservabilityContext> for runtime_worker::execution::context::ObservabilityContext` — infallible.
- [ ] 5a.10 Add `TryFrom<worker_proto::ExecutionContext> for runtime_worker::execution::context::ExecutionContext`, composing 5a.6-5a.9 plus `WorkloadId`/`AllocationId`/`dependencies` conversion; `execution_parameters` converts the wire's `HashMap<String, String>` into the domain's `BTreeMap<String, String>` (D10 Consequences) — infallible.
- [ ] 5a.11 Add `TryFrom<worker_proto::ExecutionReport> for runtime_worker::execution::report::ExecutionReport`.
- [ ] 5a.12 Add `TryFrom<worker_proto::ExecutionPulse> for runtime_worker::execution::report::ExecutionPulse`.
- [ ] 5a.13 Extend `ConversionError` with every new variant introduced by 5a.4-5a.6 (`UnspecifiedExecutionPhase` or equivalent name, `NegativeDuration`, and any additional `MissingField` call site for `allocation_contract`); extend `impl runtime_primitives::Classify for ConversionError` to classify every new variant `Permanent`.
- [ ] 5a.14 Retarget every existing test whose assertion previously checked a mirror type (`ExecutionEventArm`, `ExecutionResponseArm`, local `CheckpointCreated`) to check the real domain type instead — update only `use` imports and the type named in `matches!`/`assert_eq!`; preserve every existing test function's name and assertion intent verbatim (`worker-wire-adapter/spec.md`: "Every prior rejection scenario still passes... producing a value of the real domain type on success and the same classified rejection on failure").
- [ ] 5a.15 Add new tests: wire `EXECUTION_PHASE_UNSPECIFIED` -> `Permanent`; negative `Duration` -> `Permanent`; missing `allocation_contract` -> `Permanent`.
- [ ] 5a.16 Re-examine `#![allow(dead_code)]` (`convert.rs:18`, design.md Open Question #2). Expected outcome: it can be removed entirely, since every `TryFrom`/`From` impl now converts a genuinely cross-crate public type and is exercised by 5a.14-5a.15's tests. If a residue remains, narrow the allow to the specific item — never re-apply it at module scope.
- [ ] 5a.17 Self-review: grep `convert.rs` and confirm no local enum/struct duplicates the shape of a domain type that now exists, and no private `Classify` remains (re-confirming S1's removal, since S5a is the last slice to touch this file); `cargo test -p runtime-worker --lib` is green.
- [ ] 5a.18 Confirmation-only: `openspec/specs/worker-wire-adapter/spec.md` (already committed) matches the shipped `convert.rs` exactly, including the "No local mirror type stands in for a domain type" and "No private Classify copy remains" scenarios.

---

## S5b — Spec Confirmation And Full-Workspace Gate

*(depends on S4 and S5a; the five spec files are already committed — see Review Workload Forecast — so this slice is confirmation-and-gate, not authoring)*

- [ ] 5b.1 Confirm `openspec/specs/runtime-primitives/spec.md`'s "Classify Trait Is Public" requirement (already committed) matches S1's shipped trait exactly.
- [ ] 5b.2 Confirm `openspec/specs/runtime-allocation/spec.md`'s `AllocationContract` requirement matches S2's shipped struct exactly.
- [ ] 5b.3 Confirm `openspec/specs/runtime-worker/spec.md`'s `WorkerService`, `ExecutionChannel`, `ExecutionContext`, `ExecutionEvent`, `ExecutionPhase`, and "Generated Transport Code Stays Private" requirements match S3a/S3b/S4's shipped surface exactly, including the now-load-bearing "no `tonic::`/`prost::`/`tokio::` path anywhere in the public API" scenario.
- [ ] 5b.4 Confirm `openspec/specs/worker-wire-adapter/spec.md`'s requirements (all five, especially "Conversions Target Real Domain Types") match S5a's shipped `convert.rs` exactly.
- [ ] 5b.5 Confirm `openspec/specs/worker-inbound-port/spec.md`'s five requirements match the shipped domain+port surface, in particular the two "Port Is Exercisable..." scenarios against S4's integration tests (4.10, 4.12).
- [ ] 5b.6 If any spec/code mismatch surfaces in 5b.1-5b.5, record it as a blocking finding for `sdd-verify` rather than silently patching either side; resolve any genuine conflict using the same reasoning D9-D12 already applied — do not relitigate a settled decision ad hoc.
- [ ] 5b.7 Full-workspace gate: `cargo fmt --check`, `cargo clippy --workspace -- -D warnings`, `cargo test --workspace`; `cargo metadata` still lists exactly 16 members; the `ALLOWED` edge matrix and `EXTERNAL_ALLOWED` table are unchanged (D9 — no edit expected in `runtime/tests/architecture_guard.rs` beyond S0's comment-skip fix).
- [ ] 5b.8 Cross-check every `proposal.md` Success Criterion against the task(s) that satisfy it (see table below); flag and file a follow-up for any gap found.

### Task 5b.8 — Success Criteria Cross-Check

| # | Success Criterion (`proposal.md`) | Satisfied by |
|---|---|---|
| 1 | `runtime-worker` exposes a public `WorkerService` and `ExecutionChannel`, both outside `adapters/` | 4.1-4.2, 4.8 |
| 2 | `ExecutionContext` is immutable data with no channel/cancellation field, constructible in a unit test in a handful of lines | 3a.5-3a.6, 3a.8 |
| 3 | A fake `ExecutionContext` + in-memory `ExecutionChannel` exercises the port with no tokio runtime, no transport, no I/O | 4.9-4.12 |
| 4 | `ExecutionEvent` has exactly six arms; `ExecutionPhase` has exactly six states and no `Unspecified` | 3b.3-3b.4, 3b.13 |
| 5 | `convert.rs` defines no local mirror type and no private `Classify`; every rejection scenario still passes | 1.4-1.6, 5a.1-5a.3, 5a.14, 5a.17 |
| 6 | `Classify` is public in `runtime-primitives`, implemented by `WorkerError` and `ConversionError`; unspecified phase classifies `Permanent` | 1.1-1.2, 3b.9, 1.4, 5a.4, 5a.15 |
| 7 | `AllocationContract` is defined in `runtime-allocation` and nowhere else | 2.1, 5a.6 (consumption, not redefinition) |
| 8 | No `tonic::`/`prost::`/`tokio::` path anywhere in `runtime-worker`'s public API; existing containment guards still pass unmodified | S0 (guard fix, verified against unchanged verdict), all of S3a/S3b/S4 (construction), 5b.7 |
| 9 | `cargo metadata` lists exactly 16 members; `ALLOWED` unchanged | 5b.7 |
| 10 | `cargo fmt --check`, `cargo clippy --workspace -- -D warnings`, `cargo test` clean without crate-wide allows | 5b.7, 5a.16 |

---

## Requirement Coverage Map

| Spec / Requirement | Task(s) |
|---|---|
| `runtime-primitives` — Classify Trait Is Public (all 4 scenarios) | 1.1-1.6, 1.8 |
| `runtime-allocation` — AllocationContract Is A Public Data Contract, Intentionally Partial (all 4 scenarios) | 2.1-2.6 |
| `runtime-allocation` — External Allowlist Stays Empty | 2.5 |
| `runtime-worker` — WorkerService Is The Worker Domain's Public Inbound Port (all 3 scenarios) | 4.1-4.4, 4.8 |
| `runtime-worker` — ExecutionChannel Is The Worker-Owned Outbound Port (all 3 scenarios) | 4.1, 4.6, 4.8 |
| `runtime-worker` — ExecutionContext Is Immutable Data With No Channel And No Cancellation Field (all 4 scenarios) | 3a.5-3a.6, 3a.8 |
| `runtime-worker` — ExecutionEvent Is A Closed Six-Arm Enum (both scenarios) | 3b.2-3b.3, 3b.13 |
| `runtime-worker` — ExecutionPhase Has Exactly Six States And No Placeholder (all 3 scenarios) | 3b.4, 3b.13 |
| `runtime-worker` — Generated Transport Code Stays Private (all 4 scenarios) | S0 (0.1-0.4), existing structure unchanged, verified in 5b.7 |
| `worker-wire-adapter` — Identity Wrapper Messages Convert Losslessly (unchanged, re-verified) | 5a.14 |
| `worker-wire-adapter` — Unset Required Message Fields Are Rejected (unchanged, re-verified) | 5a.2, 5a.14 |
| `worker-wire-adapter` — ExecutionEvent's Six Arms Decode Exhaustively (unchanged, re-verified) | 5a.1, 5a.14 |
| `worker-wire-adapter` — ExecutionResponse's Two Arms Decode Exhaustively (unchanged, re-verified) | 5a.3, 5a.14 |
| `worker-wire-adapter` — Every Conversion Rejection Is Classified Permanent (unchanged + new variants) | 5a.13, 5a.15, 1.4 |
| `worker-wire-adapter` — Conversions Target Real Domain Types, No Local Mirror Remains (all 3 scenarios) | 5a.1-5a.3, 5a.17, 5a.18 |
| `worker-inbound-port` — WorkerService Exposes Exactly The Three Wire-Mirrored Capabilities | 4.2 |
| `worker-inbound-port` — ExecutionContext Carries No Channel And No Cancellation Signal | 3a.5-3a.6, 3a.8 |
| `worker-inbound-port` — ExecutionEvent Has Exactly Six Arms And ExecutionPhase Has No Unspecified State | 3b.3-3b.4, 3b.13 |
| `worker-inbound-port` — The Domain Surface Names No Transport Type And No Tokio Type | S0, 4.15, 5b.7 |
| `worker-inbound-port` — The Port Is Exercisable With A Fake Context And An In-Memory Channel (both scenarios) | 4.9-4.13 |
| Design D9 (RPITIT, `+ Send`, `execute<C>` generic-by-value, `dyn`-incompatibility documented) | 4.1-4.3, 4.15 |
| Design D10 (`SecurityContext` opaque `String` fields, `BTreeMap` maps) | 3a.3, 3a.8, 5a.8 |
| Design D11 (O1-O4 obligations, documented not mechanized; `CancelAck` idempotent) | 3b.8-3b.11, 4.4-4.5, 4.11-4.14 |
| Design D12 (slice/wave structure) | this document's structure |
| Design Gotcha (`architecture_guard.rs` comment-blind scan) | S0 (0.1-0.4) |

---

## Risks

| Risk | Note |
|---|---|
| S3b drifts past the 400-line budget during apply | Pre-agreed sub-split (design.md D12 Review Workload Forecast): split `ExecutionEvent` + its six payloads into its own PR, separate from `ExecutionReport`/`ExecutionPhase`/`ExecutionPulse`/`CancelAck`/`WorkerError`. |
| Task 4.13/4.14's yielding-fixture (for O1 and, optionally, O4) is not fully specified here | Explicitly flagged as an `sdd-apply` implementation choice; the happy-path fixture (`RecordingChannel`, always `Ready`) cannot demonstrate a live registration window by itself, so a second, distinct small `Future` is needed. This is the single highest-friction item in S4, mirroring how design.md flagged the `async fn`-in-impl question as S9's own highest-friction item. |
| Task 5a.3's `ExecutionResponse` routing shape (enum vs. two `TryFrom` impls) is left open | Either satisfies `worker-wire-adapter/spec.md`'s "no local mirror" requirement, since no domain `ExecutionResponse` type exists to duplicate; `sdd-apply` should pick the simpler one and note the choice, not treat it as ambiguous scope. |
| S5b's re-estimated near-zero line count assumes the five spec files truly need no edits | If `sdd-apply` finds even a small mismatch between shipped code and already-committed spec text (e.g., an exact field name or accessor signature drift), 5b.6 requires surfacing it to `sdd-verify` rather than quietly patching the spec — this preserves the spec's normative authority. |
| Eight chained PRs is one more than design.md's seven-slice count | S0 is additive and independently mergeable; it does not lengthen the critical path (Wave 1 already has three parallel slices; S0 is a fourth), so total wall-clock impact is expected to be near zero, only reviewer-count impact (+1 small, mechanical PR). |
