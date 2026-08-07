# Exploration: runtime-scheduler Data Family (Scheduling Domain Types)

## Current State

`crates/runtime-scheduler/src/lib.rs` is still the bare stub (doc comment only, citing `14-resource-model.md` and `16-scheduling-engine.md`). `Cargo.toml` already declares its full future dependency set — `runtime-primitives` + `runtime-object`, zero external crates — matching `runtime/tests/architecture_guard.rs`'s existing allowlist entries (lines 24-27, 93, 129).

## Affected Areas

- `crates/runtime-scheduler/src/lib.rs` — stub becomes the data family
- `openspec/specs/runtime-scheduler/spec.md` — currently only "Exhaustive Dependency Set" + "Stub Crate, No Public Traits"

## Domain Findings

- **`14-resource-model.md`**: `Resource` belongs to `runtime-scheduler` (no `runtime-resource` crate). It is a specialized Logical Object — identity is `ObjectId` + `ObjectVersion` (from `runtime-primitives`), never a separate `ResourceId` type. Capacity/Allocated/Available are **observational state**, never persisted through an Authoritative Event Stream. Capability metadata (GPU/CUDA/etc.) participates in Filter; capacity participates in Allocation.
- **`16-scheduling-engine.md`**: pipeline is Candidate Discovery → Capability Filter (produces `FilterResult`: `Feasible | Infeasible(reason)`) → Scoring Policies (produce `Score`) → `AllocationPlan`. The Scheduling Engine is a pure function `(Cluster Snapshot, Workload Requirements) → AllocationPlan`. `FilterPolicy`/`ScoringPolicy` traits are explicitly Ports/behavior — deferred.
- **`15-allocation-model.md`**: `AllocationPlan` is a Data Contract *owned by the Scheduler* (producer-owns-data-contract rule). It carries ephemeral Scheduling Metadata — `Priority`, `Cost`, `Affinity`, `Locality Score`, `Energy Score`, `Rack Preference`, `AI Placement Score` — that never reaches `Allocation` itself. It also declares explicit dependencies (Objects referenced, each with observed `ObjectVersion`/`ContentHash`) for later per-dependency revalidation. Note: this doc's own prose says "a `ResourceId`" informally when listing `Allocation`'s identity fields — inconsistent with 14's ObjectId-based identity; not this change's problem to fix, `runtime-allocation` already owns a documented partial `AllocationContract` and will resolve it if/when needed.
- **`17-cluster-snapshot.md`**: `Cluster Snapshot` construction is owned by State Assembler (`19-state-assembler.md`, presumably `runtime-state`), not `runtime-scheduler`. `Candidate` is a `runtime-scheduler`-local concept consumed during Candidate Discovery — not the Snapshot itself.

## User-Confirmed Scope (this change)

**In**: `Resource`, `Candidate`, `FilterResult`, `Score`, `AllocationPlan` — domain types only.
**Out**: `FilterPolicy`, `ScoringPolicy`, `SchedulingStrategy`/`SchedulingEngine`, any trait/Port, any placement algorithm. Deferred to a future behavior change, once vocabulary is stable — same two-slice discipline as `runtime-object` (data family → future Ports) and `runtime-storage` (data family → future `append`/`replay`).

**Explicit constraint carried into design**: `Resource` must describe observable capacity only — never current workload, reservation, lease, or scheduler-internal metadata (that belongs to `Allocation`/`Lease`, already owned elsewhere).

## Ready for Proposal

Yes.
