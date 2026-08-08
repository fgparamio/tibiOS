# Archive Report: runtime-state-domain-types

**Change**: runtime-state-domain-types  
**Archived**: 2026-08-07  
**Artifact Store Mode**: openspec  
**Status**: COMPLETE

---

## Executive Summary

The `runtime-state-domain-types` change has been successfully completed, verified, and archived. All 24 tasks across 7 phases executed and passed. The delta spec has been merged into the main specification. The change introduces the Cluster Snapshot data family (`ClusterGeneration`, `HealthState`, `NodeState`, `AllocationSummary`, `ClusterSnapshot`) to the `runtime-state` domain, completing the vocabulary freeze per the two-slice discipline.

---

## Verification Outcome

**Verdict**: PASS WITH WARNINGS

| Metric | Result |
|--------|--------|
| Tests | 12/12 passed (runtime-state), all workspace tests green |
| Clippy | Clean (zero warnings, `-D warnings` enforced) |
| Build | Success (`cargo check -p runtime-state`) |
| Architecture Guard | 22/22 passed (includes runtime-state allowed-edge, exhaustive-dependency, external-dependency assertions) |
| Spec Compliance | 12/12 scenarios compliant |
| Success Criteria | 6/6 met |

**Issues**:
- CRITICAL: None
- WARNING: No formal TDD Cycle Evidence artifact (openspec mode tracks via `tasks.md` checkboxes; git history is squashed monorepo import). Circumstantial signal is strong: test count matches design 1:1 (12/12 unit test rows); task phases strictly order RED before GREEN.
- SUGGESTION: Success Criteria checkboxes now ticked at archive time (cosmetic, per verify-report).

---

## Specs Synced

### runtime-state (`openspec/specs/runtime-state/spec.md`)

| Action | Count | Details |
|--------|-------|---------|
| Modified | 1 | "Stub Crate, No Public Traits" → "runtime-state Exposes A Data Family, Still No Public Traits" |
| Added | 5 | ClusterGeneration, HealthState, NodeState, AllocationSummary, ClusterSnapshot |
| Unchanged | 2 | "Exhaustive Dependency Set", "The Network Dependency Is Data-Contract-Only" |

**Merge**: Delta requirements 1 MODIFIED + 5 ADDED applied cleanly to the main spec. First two requirements preserved as-is. Third requirement replaced. Five new requirements appended.

---

## Implementation Summary

### Data Family (5 Types)

| Type | Derives | Fields | Role |
|------|---------|--------|------|
| `ClusterGeneration` | Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash + manual Default | `(u64)` | Monotonic snapshot counter; mirrors `ObjectVersion`'s shape; observability/topology metadata only |
| `HealthState` | Debug, Clone, Copy, PartialEq, Eq | `Healthy \| Degraded \| Unhealthy` | Inferred Health enum; explicitly flagged as not doc-mandated; revisable |
| `NodeState` | Debug, Clone, PartialEq, Eq | `{ node: NodeId, health: HealthState, resources: Vec<Resource> }` | Pairs Node identity, Health, and Scheduler Resources (reused directly) |
| `AllocationSummary` | Debug, Clone, Copy, PartialEq, Eq | `{ allocation: AllocationId, workload: WorkloadId }` | Intentionally minimal; no lifecycle/status fields |
| `ClusterSnapshot` | Debug, Clone, PartialEq, Eq | `{ generation: ClusterGeneration, created_at: Timestamp, nodes: Vec<NodeState>, allocations: Vec<AllocationSummary> }` | Atomic Snapshot; immutable by construction; `snapshot_id` deferred |

### No New Traits, No New Ports
- Zero public traits declared
- Zero assembler pipeline
- Zero ports or composition logic
- Data types only; pipeline is future slice

### Dependency Integrity
- `Cargo.toml` unchanged — still exactly: `runtime-primitives`, `runtime-object`, `runtime-scheduler`, `runtime-network`, zero external
- Architecture Guard confirms no new external dependencies
- `runtime-network` remains data-contract-only (events are unexercised; stub crate still has no event types in code)
- `runtime-scheduler::Resource` reused directly; no parallel `ResourceState`

---

## Tasks Completed

**Total**: 24 / 24 (100%)

| Phase | Goal | Status | Subtasks |
|-------|------|--------|----------|
| Phase 1 | ClusterGeneration | ✅ Complete | 6/6 (RED 1.1-1.5, GREEN 1.6) |
| Phase 2 | HealthState | ✅ Complete | 2/2 (RED 2.1, GREEN 2.2) |
| Phase 3 | NodeState | ✅ Complete | 3/3 (RED 3.1-3.2, GREEN 3.3) |
| Phase 4 | AllocationSummary | ✅ Complete | 2/2 (RED 4.1, GREEN 4.2) |
| Phase 5 | ClusterSnapshot | ✅ Complete | 4/4 (RED 5.1-5.3, GREEN 5.4) |
| Phase 6 | Structural Guarantees / Crate Doc | ✅ Complete | 4/4 (review-only 6.1-6.3, config verify 6.4) |
| Phase 7 | Verification | ✅ Complete | 3/3 (test/clippy 7.1-7.3) |

---

## Archive Contents

| Artifact | Path | Status |
|----------|------|--------|
| Proposal | `proposal.md` | ✅ (Success Criteria all ticked) |
| Exploration | `exploration.md` | ✅ |
| Specification | `specs/runtime-state/spec.md` | ✅ (merged into main spec) |
| Design | `design.md` | ✅ |
| Tasks | `tasks.md` | ✅ (24/24 complete) |
| Verification Report | `verify-report.md` | ✅ (PASS WITH WARNINGS) |
| Archive Report | `archive-report.md` | ✅ (this file) |

---

## Source of Truth Updated

The following specs now reflect the completed change and are the authoritative definitions:

- **`openspec/specs/runtime-state/spec.md`** — Merged delta: 1 MODIFIED requirement (data family replaces stub), 5 ADDED requirements (ClusterGeneration, HealthState, NodeState, AllocationSummary, ClusterSnapshot), 2 unchanged (dependencies). All scenarios now specify data-type behavior, not-yet-specified assembler logic deferred.

---

## Deferred (Documented as Open Questions)

The following remain out of scope and are documented in the design:

- **`snapshot_id`**: blocked on minting a `SnapshotId` primitive in `runtime-primitives` (`02-project-structure.md` architectural change, precedent: `RuntimeId`). Field is additive post-primitive landing.
- **Cluster topology and Runtime capabilities**: listed in Snapshot Contents with zero elaboration in any doc. Deferred per "intentionally partial" precedent (`runtime-scheduler` GPU/CUDA taxonomy).
- **State Assembler / Trust → Membership → Health → Resources pipeline** (`19-state-assembler.md`): trait-design follow-up, not this data-only slice.

---

## Guarantees Enforced

1. **No `ClusterGeneration` + `AllocationPlan` pairing**: Structurally unrepresentable in the crate; guardrail enforced via no-method, no-field, no-free-function rule (D2).

2. **No parallel Resource type**: `NodeState` reuses `runtime_scheduler::Resource` directly; `ResourceState` does not exist (D5/D6).

3. **No `WorkloadState` collision**: `11-runtime.md` already owns `WorkloadState` for Runtime lifecycle. `AllocationSummary` correctly implements Snapshot Contents' "Allocation summaries" (D7).

4. **`HealthState` explicitly inferred**: Doc comment flags variant set as inferred from prose, not exhaustively doc-mandated, revisable by future Health domain (D4).

5. **`AllocationSummary` intentionally minimal**: Exactly 2 fields (`AllocationId`, `WorkloadId`); no `runtime-allocation`-owned lifecycle (D7).

6. **`ClusterSnapshot` immutable by construction**: All-fields constructor, private fields, read-only accessors. Partially-assembled Snapshot unrepresentable (D8).

---

## Key Decisions Preserved in Archive

- **D1**: `ClusterGeneration` is its own newtype, not `ObjectVersion` (resolves ownership/reusability risk)
- **D2**: Mirrors `ObjectVersion`'s surface; `Ord` scoped to "more recent" (observability only, never plan validation)
- **D3**: `HealthState` = `Healthy | Degraded | Unhealthy` (no `Draining` — Membership-owned per `19-state-assembler.md`)
- **D4**: `HealthState` doc self-flags inferred/revisable; no `Default` (D5)
- **D5-D6**: `NodeState` reuses `runtime_scheduler::Resource`; no parallel types
- **D7**: `AllocationSummary` frozen at 2 fields, `Copy` (D8)
- **D8**: `ClusterSnapshot` immutable; single constructor
- **D9**: No serde derives (zero-external guard)
- **D10**: `created_at: Timestamp` ships; `snapshot_id` stays blocked (split per user confirmation)

---

## SDD Cycle Complete

The change has been **fully planned** (proposal + exploration), **fully specified** (spec + design), **fully tasked and implemented** (24 tasks, all complete, tests green), **verified** (PASS WITH WARNINGS, zero CRITICAL issues), and **archived** (delta merged, folder archived, report written).

Ready for the next change.

---

**Archived by**: SDD Archive phase  
**Archive date**: 2026-08-07  
**Next recommended**: None (change is complete)
