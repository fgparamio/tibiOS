# Exploration: runtime-state Data Family (Cluster Snapshot Domain Types)

## Current State

`crates/runtime-state/src/lib.rs` is still the bare stub (doc comment only, citing `17-cluster-snapshot.md` and `19-state-assembler.md`, and explicitly documenting that its `runtime-network` dependency is data-contract-only — it consumes the Runtime Events Networking publishes, `TrustRevoked`/`PeerReachabilityChanged`/`SessionEstablished`/`SessionClosed`/`MemberJoined`/`MemberLeft`/`HealthChanged`, and must never reference Networking's Transport/Session internals — same exception pattern `02-project-structure.md` grants `runtime-allocation -> runtime-scheduler`). `Cargo.toml` already declares its full future dependency set — `runtime-primitives`, `runtime-object`, `runtime-scheduler`, `runtime-network`, zero external — confirmed exact against `runtime/tests/architecture_guard.rs`'s `ALLOWED` table (lines 44-52) and `EXTERNAL_ALLOWED`. `openspec/specs/runtime-state/spec.md` currently only has "Exhaustive Dependency Set" + the network-is-data-contract-only stub requirement.

## Affected Areas

- `crates/runtime-state/src/lib.rs` — stub becomes the data family
- `openspec/specs/runtime-state/spec.md` — currently only dependency + stub requirements
- `crates/runtime-primitives/src/identity.rs` — existing `NodeId`, `AllocationId`, `WorkloadId`, `ObjectId`/`ObjectVersion` to reuse
- `crates/runtime-scheduler/src/lib.rs` — `Resource` (id/version/capacity), to be reused directly, not re-modeled

## Domain Findings

- **`17-cluster-snapshot.md`**: Snapshot Contents are Runtime-approved Nodes, Health observations, Resource summaries, **Allocation summaries**, cluster topology, Runtime capabilities. It says "Allocation summaries," never "Workload state" — the user's originally proposed `WorkloadState` name is a collision with an already-defined, differently-owned concept: `11-runtime.md` already defines `WorkloadState` as the Runtime composition root's lifecycle (`Created → Scheduled → Running → Completed/Failed → Recovered`), not something `runtime-state` owns. The correct Slice-1 type per the Snapshot Contents line is `AllocationSummary`.
- **`19-state-assembler.md`**: pipeline is Trust → Membership → Health → Resources → Cluster Snapshot, each stage owned by exactly one domain. The assembler/pipeline logic itself is explicitly out of scope for a data-only Slice 1 — only the data shapes it produces belong here.
- **Identity fields — prose vs. shipped code**: `17-cluster-snapshot.md`'s prose parenthetical groups "Node, Resource, Logical Object Reference, Allocation Summary" under one ObjectId+ObjectVersion umbrella. That's inconsistent with what's actually shipped: the closed `ObjectType` enum (10 variants) has no `Node`/`Allocation` category, and `15-allocation-model.md` explicitly says "Every Allocation owns an `AllocationId`... Identity never changes." Same "prose is informally inconsistent with the shipped model, not this change's problem to fix" pattern already flagged for `ResourceId` during the `runtime-scheduler` exploration. `NodeState` and `AllocationSummary` should key off the already-shipped dedicated ULID primitives (`NodeId`, `AllocationId`), not `ObjectId`+`ObjectVersion`.
- **`14-resource-model.md`** / already-shipped `runtime-scheduler::Resource`: Resource is explicitly owned by `runtime-scheduler` (no `runtime-resource` crate exists or should exist). `runtime-state` already depends on `runtime-scheduler` — "Resource summaries" should reuse `runtime_scheduler::Resource` directly inside `NodeState`, not invent a parallel `ResourceState` type.
- **`runtime-network` still a bare stub**: no event types exist in code yet, so `TrustRevoked` etc. can't be consumed as real Rust types this slice. The dependency stays declared-but-unexercised — same accepted precedent as `runtime-object` being unused in the `runtime-scheduler` Slice 1.
- **Snapshot ID gap**: `17-cluster-snapshot.md` says every Snapshot owns a Snapshot ID, but `runtime-state` has zero allowed external dependencies (no `ulid` crate) and no `SnapshotId` primitive exists in `runtime-primitives`. Minting one is an explicit architectural change (reopens `02-project-structure.md`, same category as the precedent of adding `RuntimeId`) — recommend deferring `snapshot_id` from this slice entirely rather than bundling a primitives change into a data-family slice.
- **`Cluster Summary` is a different, real concept**: `19-state-assembler.md`/`20-admission-control.md`/GLOSSARY.md define `Cluster Summary` as Admission's coarser, cheaper view, distinct from the full `Cluster Snapshot`. Not mentioned in the user's scope and not cited by `runtime-state`'s own stub doc comment (only 17/19) — defer to a later slice.
- **Health has no closed enum anywhere**: unlike `ObjectType`/`ObjectLifecycle` (exhaustively spelled out in their owning docs), `14-resource-model.md` only informally names `Draining`/`Unhealthy` in passing prose. Any `HealthState` enum this slice is necessarily inferred, not doc-mandated — must be flagged explicitly as such and treated as revisable once Health's real owning domain (likely under `22-networking.md`/a future `runtime-security`) is built out.
- **"cluster topology" and "Runtime capabilities"**: also listed in Snapshot Contents, zero elaboration anywhere in the docs. Recommend deferring both — same "intentionally partial" precedent as the deferred GPU/CUDA capability taxonomy in `runtime-scheduler`.

## User-Confirmed Scope (this change)

**In** (refined from the user's original `ClusterSnapshot`/`NodeState`/`ResourceState`/`WorkloadState` proposal against the findings above): `ClusterGeneration`, `HealthState`, `NodeState`, `AllocationSummary`, `ClusterSnapshot` — domain types only.

- `ClusterGeneration` — mirrors `ObjectVersion`'s shape; doc comment must repeat `17-cluster-snapshot.md`'s explicit guardrail that it is observability/topology metadata only, **never used to validate an individual Allocation Plan**.
- `HealthState` — small enum, explicitly flagged in its doc comment as *inferred, not doc-mandated* (unlike `ObjectType`/`ObjectLifecycle`).
- `NodeState` — pairs `NodeId`, `HealthState`, and the Node's `runtime_scheduler::Resource`(s). Reuses existing primitives, no new `ResourceState`.
- `AllocationSummary` — pairs `AllocationId` and `WorkloadId`, intentionally minimal (no Runtime-owned lifecycle fields — that stays `runtime-allocation`'s).
- `ClusterSnapshot` — `ClusterGeneration` + `Vec<NodeState>` + `Vec<AllocationSummary>`. No `snapshot_id`, no cluster topology, no Runtime capabilities this slice — all three deferred as Open Questions.

**Out**: State Assembler/pipeline logic, any Port, any policy, log-based reconstruction, `snapshot_id` (blocked on a `runtime-primitives` change), cluster topology, Runtime capabilities, `Cluster Summary` (Admission's separate coarse view). Deferred to future slices — same two-slice discipline as `runtime-object`/`runtime-storage`/`runtime-scheduler`.

**Open Questions carried into design**: Snapshot granularity/versioning (blocked on `SnapshotId` primitive — architectural, not this slice's call); fully immutable vs. incremental Delta; which Snapshot parts derive from `runtime-network` vs. `runtime-scheduler` long-term; State Assembler invariants (future slice, not this one).

## Ready for Proposal

Yes.
