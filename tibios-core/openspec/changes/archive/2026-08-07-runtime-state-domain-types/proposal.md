# Proposal: runtime-state Data Family (Cluster Snapshot Domain Types)

## Intent

`runtime-state` is still a bare stub. Following the same two-slice discipline already applied to `runtime-object`, `runtime-storage` and `runtime-scheduler`: freeze the domain's vocabulary before its behavior. This change gives the Cluster Snapshot its language — `ClusterGeneration`, `HealthState`, `NodeState`, `AllocationSummary`, `ClusterSnapshot` — with zero Ports, zero traits, zero assembler pipeline.

## Scope

### In Scope
- `ClusterGeneration` — monotonic snapshot counter, mirrors `ObjectVersion`'s shape; doc comment repeats `17-cluster-snapshot.md`'s guardrail that it is observability/topology metadata only, **never** used to validate an individual Allocation Plan
- `HealthState` — small enum, explicitly flagged in its doc comment as *inferred, not doc-mandated* (unlike the exhaustively specified `ObjectType`/`ObjectLifecycle`)
- `NodeState` — pairs `NodeId`, `HealthState`, and the Node's `runtime_scheduler::Resource`(s)
- `AllocationSummary` — pairs `AllocationId` and `WorkloadId`, intentionally minimal
- `ClusterSnapshot` — `ClusterGeneration` + `created_at: Timestamp` + `Vec<NodeState>` + `Vec<AllocationSummary>` (timestamp added during design per `17-cluster-snapshot.md`'s identity triple; `snapshot_id` stays deferred, see design D10)

### Out of Scope
- The State Assembler / Trust → Membership → Health → Resources pipeline (`19-state-assembler.md`) and any Port or trait
- Any policy, and log-based Snapshot reconstruction
- `snapshot_id` — blocked on minting a `SnapshotId` primitive, which is an architectural change to `runtime-primitives`/`02-project-structure.md` (same category as adding `RuntimeId`), not a data-family slice's call
- Cluster topology and Runtime capabilities — listed in Snapshot Contents with zero doc elaboration; same "intentionally partial" precedent as `runtime-scheduler`'s deferred capability taxonomy
- `Cluster Summary` — Admission's separate, coarser view (`20-admission-control.md`), not cited by this crate's own stub doc comment
- A parallel `ResourceState` type — Resource is owned by `runtime-scheduler` and is reused directly
- A `WorkloadState` type — `11-runtime.md` already owns that name for the Runtime composition root's lifecycle

## Capabilities

### New Capabilities
None — `runtime-state` capability already exists as a stub spec.

### Modified Capabilities
- `runtime-state`: replaces "Stub Crate, No Public Traits" with the data family; adds `ClusterGeneration`, `HealthState`, `NodeState`, `AllocationSummary`, `ClusterSnapshot` requirements. The "Exhaustive Dependency Set" and "The Network Dependency Is Data-Contract-Only" requirements are unchanged.

## Approach

Same shape as `runtime-object-domain-types`/`runtime-storage-domain-types`/`runtime-scheduler-domain-types`: plain value types in a single flat `lib.rs`, no submodules, no new dependency (`Cargo.toml` already declares the exact allowed set — `runtime-primitives`, `runtime-object`, `runtime-scheduler`, `runtime-network`, zero external), TDD per type.

Identity keys off the already-shipped dedicated ULID primitives (`NodeId`, `AllocationId`, `WorkloadId`) rather than `ObjectId`+`ObjectVersion`. `17-cluster-snapshot.md`'s prose groups Node and Allocation Summary under a Logical Object umbrella, but the shipped closed `ObjectType` enum has no `Node`/`Allocation` variant and `15-allocation-model.md` states an Allocation owns an `AllocationId` whose identity never changes — same "prose is informally inconsistent with the shipped model, and fixing it is not this change's job" call already made for `ResourceId` in `runtime-scheduler`.

`NodeState` embeds `runtime_scheduler::Resource` directly for "Resource summaries" — `14-resource-model.md` gives Resource to the Scheduler and the dependency already exists. `runtime-network` stays declared-but-unexercised this slice because it is still a bare stub with no event types in code, the same accepted state `runtime-object` had during `runtime-scheduler`'s Slice 1.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `crates/runtime-state/src/lib.rs` | Modified | Stub → 5-type data family + tests |
| `openspec/specs/runtime-state/spec.md` | Modified (at archive) | Merge this change's delta |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `HealthState`'s variants are inferred from passing prose (`Draining`/`Unhealthy` in `14-resource-model.md`), not from a closed doc-mandated enum | High | Keep the variant set minimal, mark the enum non-exhaustive-in-spirit in its doc comment, and state explicitly that Health's real owning domain (`22-networking.md` / a future security crate) may revise it |
| `ClusterGeneration` gets misread as an Allocation Plan validity token | Medium | Design phase freezes the guardrail wording; no API that pairs a `ClusterGeneration` with a plan or an admission decision |
| `AllocationSummary` drifts into carrying `runtime-allocation`-owned lifecycle state | Medium | Design phase freezes an explicit two-field set (`AllocationId`, `WorkloadId`); no status/phase/timestamp field |
| Shipping `ClusterSnapshot` without `snapshot_id` bakes in an identity-less Snapshot | Medium | Documented as deferred, not rejected; adding the field later is additive once the `SnapshotId` primitive lands |
| `NodeState` re-modelling Resource instead of reusing `runtime_scheduler::Resource` | Low | Explicitly excluded above; verified by review that no `ResourceState` type is introduced |

## Rollback Plan

Revert the commit — additive change, nothing yet depends on `runtime-state`'s public API.

## Dependencies

None beyond the already-declared `runtime-primitives`, `runtime-object`, `runtime-scheduler`, `runtime-network`. No `Cargo.toml` change.

## Success Criteria

- [x] `cargo test -p runtime-state` and `cargo test --workspace` green
- [x] `cargo clippy --all-targets -- -D warnings` clean
- [x] No public trait declared; dependency set unchanged (`runtime-primitives`, `runtime-object`, `runtime-scheduler`, `runtime-network`, zero external)
- [x] `runtime-network` is referenced only as a data contract — no Transport/Session type appears
- [x] `NodeState` reuses `runtime_scheduler::Resource`; no `ResourceState` or `WorkloadState` type exists
- [x] `AllocationSummary` carries no Allocation lifecycle field; `ClusterSnapshot` carries no `snapshot_id`, topology, or capabilities field
