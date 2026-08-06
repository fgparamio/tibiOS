# Proposal: Worker Inbound Port (the Worker domain's public language)

## Intent

`proto-worker-contract` froze the wire projection. `worker-grpc-adapter` compiled it behind a private `adapters/` tree. Both proposals deferred the same thing, by name: "Worker domain types, Inbound Ports, and their conversions — separate, later change."

The consequence is visible today in `crates/runtime-worker/src/adapters/grpc/convert.rs`: it converts wire types into **private local mirror enums** (`ExecutionEventArm`, `ExecutionResponseArm`) that exist only because there was nothing real to convert into, and it carries `#![allow(dead_code)]` because nothing consumes them. `runtime-worker/src/lib.rs` is still 7 lines whose doc comment says "Stub for the Worker domain". The crate owns a wire contract and no language.

This change gives the Worker domain its own public language — `ExecutionContext`, `ExecutionEvent`, `ExecutionReport`, `ExecutionPhase`, `ExecutionPulse`, cooperative cancellation — and the **Inbound Port** through which the Runtime invokes a Worker (`02-project-structure.md`'s Inbound Ports section names it `WorkerService`). It is the first time a TibiOS domain crate exposes a real port, and it establishes the pattern the other fourteen domains will copy.

Success looks like: `local-infer` and `tibios-ray` can be written against a trait that exists, `convert.rs` converts into real domain types instead of private mirrors, and `18-worker-model.md`'s own testability claim ("a fake Execution Context plus an in-memory channel, no real infrastructure required") is demonstrably true in `cargo test` with zero async runtime and zero transport.

## Decisions This Change Must Settle First

| # | Question | Decision |
|---|---|---|
| 1 | `runtime-worker` may depend on `runtime-allocation` and `runtime-object`, but both are 3-line stubs with zero public types. `ExecutionContext` doc-mandates an Allocation Contract and resolved Dependency References. Where do those live? | **Split by ownership, not by convenience.** Dependency References become a Worker-owned `ResolvedDependency` (`ObjectId` + `ObjectVersion` + `ContentHash`, all already in `runtime-primitives`) — a *resolved reference* is not an `Object`, so `runtime-object` stays a stub. `AllocationContract` is different: `02-project-structure.md`'s Ownership Boundaries table assigns it to `runtime-allocation`, and its Data Contract rule (`Allocation → AllocationContract → Worker`) forbids the consumer redefining it. So this change adds **exactly one** pure data struct to `runtime-allocation` and nothing else. See Approach for the rejected alternatives. |
| 2 | `WorkerError` must be classified `Transient`/`Permanent`/`Fatal` (`04-error-handling.md`), but `runtime-primitives`' spec says "No Public Traits In This Change — trait/port design is an explicit follow-up change", which is why `convert.rs` hand-rolled a **private copy** of `Classify`. A second private copy is now due. | **This change is that explicit follow-up.** Promote `Classify` to a public trait in `runtime-primitives`, exactly as `04-error-handling.md:146` mandates ("`ErrorClass` and the `Classify` trait live in `runtime-primitives`"), retire the "No Public Traits In This Change" requirement, and delete `convert.rs`'s private copy. One definition, not three. |
| 3 | Does `ExecutionContext` *contain* the Execution Channel and the cancellation signal, as `18-worker-model.md:52` reads literally? | **No — and the frozen wire contract already settled this.** `worker.proto:68` states it outright: "There is no Channel field and no CancellationToken field: on the wire, the Channel IS the SubmitJob response stream, and cancellation IS the Cancel RPC — neither serializes." The domain follows the same split: `ExecutionContext` stays pure immutable data (`Clone`, `PartialEq`, trivially constructible in a test), and the channel arrives as a separate parameter of the port method. Keeping a `dyn ExecutionChannel` inside `ExecutionContext` would make the doc's own "fake context in a unit test" claim harder, not easier. |
| 4 | The port is inherently async (`emit` must await on a bounded channel — backpressure, `05-async-concurrency.md:93`), but `runtime-worker`'s external allowlist is exactly `{tonic, prost, tonic-build}` — no `tokio`, no `async-trait`, no `thiserror` — and `03-api-design.md:157` forbids Tokio types in any public API. | **Constraint accepted, mechanism deferred to `sdd-design`.** Two hard requirements this change will not trade away: (a) the `ExecutionChannel` is a Worker-owned **Outbound Port** (a trait), never a `tokio::sync::mpsc` in the public signature — the bounded mpsc implementation belongs to the Composition Root, out of scope here; (b) the preferred outcome adds **no new external dependency** (native AFIT; hand-written `Display`/`Error` per the `IdentityParseError`/`ConversionError` precedent). If `sdd-design` proves AFIT is not dyn-compatible on the pinned toolchain (`rust-version = "1.93"`) and the Composition Root genuinely needs dynamic dispatch, the fallbacks in preference order are enum dispatch → manual `Pin<Box<dyn Future>>` → admitting `async-trait` (which costs an `EXTERNAL_ALLOWED` row and a spec delta, and must be justified against `05-async-concurrency.md:105`). |

## Scope

### In Scope

- **Worker domain types** (public, `runtime-worker`, outside `adapters/`): `ExecutionContext`, `ResolvedDependency`, `SecurityContext`, `ObservabilityContext`, `ExecutionEvent` (the six arms as a closed Rust enum) with its payload types, `ExecutionReport`, `ExecutionPhase`, `ExecutionPulse`, `CancelAck`-equivalent, `WorkerError`.
- **`WorkerService` — the Inbound Port**: exactly three capabilities, mirroring the three permanent RPCs (`SubmitJob`, `Cancel`, `Pulse`), because the wire is a *projection* of the domain and the domain must never be poorer than its projection.
- **`ExecutionChannel` — the Worker-owned Outbound Port**: `emit(event)`. Transport-agnostic by construction; a Worker "does not even know the concept of a client" (`18-worker-model.md:88`).
- **`runtime-allocation`**: one public data contract, `AllocationContract` (Decision #1). No trait, no behavior, no external dependency (its allowlist is `[]`).
- **`runtime-primitives`**: `Classify` promoted to a public trait (Decision #2).
- **`convert.rs` rewiring**: `ExecutionEventArm`/`ExecutionResponseArm`/local `CheckpointCreated`/local `Classify` are deleted; `TryFrom` now targets the real domain types. Rejection semantics (`Permanent`, never panic, never default) are preserved verbatim.
- **Unit tests** proving `18-worker-model.md`'s testability claim: a fake `ExecutionContext` + an in-memory `ExecutionChannel`, no tokio runtime, no transport, no I/O.
- **Spec deltas**: `runtime-worker`, `runtime-allocation`, `runtime-primitives`, `worker-wire-adapter`; new capability `worker-inbound-port`.

### Out of Scope

- **Any Worker implementation.** `local-infer` and `tibios-ray` are adapters; this change defines the port they will implement. No llama.cpp, no blocking thread pool, no subprocess supervision.
- **The concrete Execution Channel.** The bounded `tokio::sync::mpsc` implementation, and anything that owns a `Receiver`, belongs to the Runtime — a later change.
- **Composition Root wiring** in `runtime/`. No construction, no registry, no capability matching.
- **Any edit to `proto/`** (frozen) or to the transport layer itself. Only `convert.rs`'s *target* changes; the generated code, `build.rs`, the vendored copy, and the drift test are untouched.
- **Richer `Allocation` / `Object` domain types** beyond the single struct in Decision #1. `15-allocation-model.md` and `13-object-model.md` get their own changes.
- **A 17th workspace member.** The answer stays no.

## Capabilities

### New Capabilities

- `worker-inbound-port`: the Worker domain's public language and its Inbound Port — what `WorkerService` must expose, that `ExecutionContext` is immutable data carrying no channel and no cancellation token, that `ExecutionEvent` has exactly six arms and `ExecutionPhase` has no `Unspecified`, that the domain surface names no transport type and no Tokio type, and that a Worker is exercisable with a fake context plus an in-memory channel.

### Modified Capabilities

- `runtime-worker`: Purpose stops saying "stub"; gains the domain-language and Inbound Port requirements. Its two containment requirements (private generated code, no `tonic::`/`prost::` in the public API) become *load-bearing* for the first time — until now the crate had no public API for them to constrain.
- `runtime-allocation`: "Stub Crate, No Public Traits" → owns the `AllocationContract` data contract, still no public traits. Dependency set and empty external allowlist unchanged.
- `runtime-primitives`: "No Public Traits In This Change" is retired and replaced by a `Classify` requirement. External allowlist unchanged (`{serde, ulid}`).
- `worker-wire-adapter`: its Purpose currently states "Worker domain types … are explicitly out of scope — they do not exist yet". That sentence expires here; the conversion target becomes the real domain types. Every rejection scenario it defines survives unchanged.

### Unchanged, Explicitly Asserted

- `worker-wire-contract` (frozen `.proto`), `workspace-manifest` (16 members), `runtime-composition-root`, the `ALLOWED` workspace-edge matrix (`runtime-worker → runtime-allocation` already exists), and `EXTERNAL_ALLOWED` (under the preferred outcome of Decision #4).

## Approach

**Ownership decides placement, and the two stub crates are not symmetric.** The scoping question presents `runtime-allocation` and `runtime-object` as one problem; reading the specs shows they are two. `runtime-object` owns `Object` — but an `ExecutionContext` never carries an `Object`, it carries a *reference the Runtime already resolved* (`18-worker-model.md:52`: "already resolved — Workers never locate Objects"). That triple is `ObjectId` + `ObjectVersion` + `ContentHash`, three primitives that already exist, and the frozen `.proto` already models it inside `tibios.worker.v1` as `ResolvedModelRef`. So `runtime-object` stays a 3-line stub and its spec is untouched.

`AllocationContract` cannot take that route. `02-project-structure.md`'s Ownership Boundaries table assigns it to `runtime-allocation`, and its Data Contract rule is explicit — `Allocation → AllocationContract → Worker`, "the producer owns the contract, consumers never redefine it". Three alternatives were considered and rejected:

1. **Define it inside `runtime-worker`** — a consumer redefining a producer's data contract. Rejected: it is the exact anti-pattern the ownership table exists to prevent, and it would have to be un-done the day `runtime-allocation` becomes real.
2. **Drop it from `ExecutionContext`, carry only `AllocationId`** — rejected: `18-worker-model.md:56` requires the Worker to *honor and enforce* the contract (max execution duration above all). A Worker holding an opaque ID it cannot dereference (it has no Allocation service, and must never acquire one) cannot enforce anything.
3. **Build the full contract now** — all six documented facets (exclusive/shared, renewable lease, preemptible, migration allowed, checkpoint required, max duration). Rejected as scope creep into `15-allocation-model.md`'s own change, and as design-by-guess for five facets nothing consumes yet.

The chosen path is the smallest ownership-correct delta: `runtime-allocation` gains one struct whose field set matches the frozen wire message exactly (`max_execution_duration`), documented as intentionally partial, with `15-allocation-model.md` cited as the owner of its eventual full shape. Blast radius: one file, one spec delta, zero dependency-graph change (`runtime-worker → runtime-allocation` is already in the `ALLOWED` matrix), zero new external dependency.

**The wire contract is the best available design review of the domain.** `worker.proto` was derived from `18-worker-model.md` under a stated Transport-Agnosticism Test, and it already resolved questions the domain now faces: the channel and cancellation do not belong on the context (Decision #3); `EndOfStream` and `ExecutionReport` are never collapsed; `ExecutionResponse` has exactly two arms and `ExecutionEvent` exactly six, permanently. The domain adopts those resolutions rather than relitigating them — with one deliberate divergence: **the domain enum has no `Unspecified` variant.** `EXECUTION_PHASE_UNSPECIFIED` is a proto3 tag-zero obligation, not a state a Worker can be in; `convert.rs` rejects it as `Permanent`, the same treatment already given to an unset `oneof`.

**One lifecycle enum, not two.** `18-worker-model.md:78` warns that the Worker-local lifecycle (`Received → Prepared → Running → Completed/Failed`) and the Runtime-wide `WorkloadState` are two different machines that must not be merged — a warning about `runtime-worker` vs `runtime-state`, not an instruction to model two enums *inside* `runtime-worker`. The frozen `ExecutionPhase` is precisely that Worker-local lifecycle plus `Cancelled`, so it serves as the single domain enum. Inventing a second, near-identical enum next to it would be symmetry, not architecture.

**The port surface is fixed by the projection, not invented.** Three RPCs, three port capabilities: `execute` (context + channel → report), `cancel` (by `WorkloadId`, acknowledged-not-terminated), `pulse` (by `WorkloadId`). `02-project-structure.md:196` already names this port `WorkerService`; this change does not get to rename it.

**Deferred to `sdd-design`, deliberately.** The async mechanism and dyn-compatibility (Decision #4); whether `SecurityContext.tenant_id` becomes `runtime_primitives::TenantId` (ULID-parsed, so a non-ULID tenant string becomes a `Permanent` rejection) or stays `String` (the frozen proto constrains it to neither); how `cancel`/`pulse` correlate a `WorkloadId` to an in-flight execution given that Workers are reusable across Contexts; and exactly how many slices this change is cut into.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `crates/runtime-worker/src/lib.rs` | Modified | doc comment stops saying "stub"; declares the public domain modules |
| `crates/runtime-worker/src/` (new modules) | New | domain types + `WorkerService` + `ExecutionChannel`, all outside `adapters/` |
| `crates/runtime-worker/src/adapters/grpc/convert.rs` | Modified | private mirrors and private `Classify` deleted; `TryFrom` retargeted; `#![allow(dead_code)]` re-examined |
| `crates/runtime-allocation/src/lib.rs` | Modified | one public `AllocationContract` data contract |
| `crates/runtime-primitives/src/error.rs` | Modified | `Classify` becomes a public trait |
| `crates/runtime-worker/Cargo.toml` | Possibly modified | only if Decision #4 lands on a new dependency — preferred outcome is no change |
| `runtime/tests/architecture_guard.rs` | Possibly modified | `EXTERNAL_ALLOWED` only under the same condition; the transport-token scan already covers the new public modules for free |
| `openspec/specs/{runtime-worker,runtime-allocation,runtime-primitives,worker-wire-adapter}/` | Modified | spec deltas |
| `openspec/specs/worker-inbound-port/` | New | new capability |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Decision #4 forces `async-trait` or `tokio` into `runtime-worker`, widening a pinned allowlist that two prior changes worked to keep narrow | Med | `sdd-design` must exhaust AFIT and enum dispatch first and record the finding; any widening is an explicit spec delta plus an `EXTERNAL_ALLOWED` row, never a silent `Cargo.toml` edit |
| Touching `runtime-allocation` and `runtime-primitives` means a third and fourth frozen-spec loosening in as many changes — the pattern could become a habit | Med | Both are pre-argued from the owning documents, not from convenience: the ownership table for `AllocationContract`, `04-error-handling.md:146` plus the primitives spec's own "explicit follow-up change" wording for `Classify`. Each is one item, and both spec deltas are written in this change, not deferred |
| `AllocationContract` is defined with one field today and gains five when `15-allocation-model.md` gets its change — a breaking change for `ExecutionContext` | Med | Document it as intentionally partial at the definition site and in the spec; additive struct growth is the expected path, and no external consumer exists yet to break |
| Deleting `convert.rs`'s mirror types churns a module that just passed verification, risking regression of its rejection semantics | Med | `worker-wire-adapter`'s scenarios stay normative and unchanged; the existing tests are the regression net — retarget them, never delete them |
| Estimated change exceeds the 400-line review budget by a wide margin (domain types + docs + tests + rewiring + four spec deltas + one new spec) | High | Chained slices, flagged now for `sdd-tasks`: (1) `Classify` in primitives + drop the private copy, (2) `AllocationContract`, (3) Worker domain data types + their unit tests, (4) `WorkerService` + `ExecutionChannel` ports, (5) `convert.rs` retarget + spec deltas. Slices 1–2 are independently mergeable |
| The port is designed with no implementation to validate it, so `local-infer`'s real needs may not surface until later | Med | The two consumers are already characterized (`25-ai-runtime.md:42`, `18-worker-model.md:132`) and the frozen wire contract is a third, independent projection of the same requirements — three sources agreeing is the strongest validation available before an implementation exists |
| `tenant_id` as `TenantId` would make any non-ULID tenant string a hard `Permanent` rejection against a frozen `.proto` that allows any string | Low | Named explicitly as a `sdd-design` decision rather than settled by default here |

## Rollback Plan

Additive in every crate. Reverting restores the 7-line `runtime-worker` stub, the two 3-line stubs, `convert.rs`'s private mirrors, and the private `Classify` copy. Nothing calls the port — no Worker implementation and no Composition Root wiring exists — so there is no runtime behavior to unwind and no migration. `Classify` in `runtime-primitives` and `AllocationContract` in `runtime-allocation` are each independently revertible, since each is consumed only by code introduced in this same change. Spec deltas are text-only.

## Dependencies

- `openspec/specs/worker-wire-contract/spec.md` and `proto/tibios/{primitives,worker}/v1/*.proto` — normative and read-only here.
- `openspec/specs/worker-wire-adapter/spec.md` — its rejection semantics are inherited, not redesigned.
- `runtime-primitives`' existing identity/value types (`WorkloadId`, `AllocationId`, `ObjectId`, `ObjectVersion`, `ContentHash`, `TenantId`, `Timestamp`, `ErrorClass`) — reused, never reinvented.
- `docs/architecture/{18,02,03,04,05,06,25}-*.md` at tag `architecture-v1.0`.
- No new toolchain requirement; `protoc` is already required by the existing `build.rs`.

## Non-Goals

- Writing `local-infer` or wiring `tibios-ray`.
- Implementing the bounded `tokio::sync::mpsc` Execution Channel, or anything that owns its `Receiver`.
- Composition Root wiring, Worker registration, or capability matching (`16-scheduling-engine.md` already owns the selection decision — this change adds no routing component, per `25-ai-runtime.md`'s anti-pattern list).
- Designing the full Allocation Contract, the Object model, or the Runtime-wide `WorkloadState`.
- Checkpoint *policy* (Runtime-owned); only the `CheckpointCreated` event shape is in scope.
- Reopening the `.proto`, the vendored copy, `build.rs`, or the drift test.
- Adding a 17th workspace member.

## Success Criteria

- [ ] `runtime-worker` exposes a public `WorkerService` Inbound Port and a public `ExecutionChannel` Outbound Port, both outside `adapters/`
- [ ] `ExecutionContext` is immutable data with no channel field, no cancellation field, and no transport type — constructible in a unit test in a handful of lines
- [ ] A fake `ExecutionContext` plus an in-memory `ExecutionChannel` exercises the port with no tokio runtime, no transport, and no I/O
- [ ] `ExecutionEvent` has exactly six arms; `ExecutionPhase` has exactly six states and no `Unspecified`
- [ ] `convert.rs` defines no local mirror type and no private `Classify`; every `worker-wire-adapter` rejection scenario still passes
- [ ] `Classify` is public in `runtime-primitives`, implemented by both `WorkerError` and the adapter's `ConversionError`; a wire `EXECUTION_PHASE_UNSPECIFIED` classifies `Permanent`
- [ ] `AllocationContract` is defined in `runtime-allocation` and in no other crate
- [ ] No `tonic::`, `prost::`, or `tokio::` path appears anywhere in `runtime-worker`'s public API; the existing containment guards still pass unmodified
- [ ] `cargo metadata` still lists exactly 16 members; the `ALLOWED` edge matrix is unchanged
- [ ] `cargo fmt --check`, `cargo clippy --workspace -- -D warnings`, and `cargo test` are clean without crate-wide allows
