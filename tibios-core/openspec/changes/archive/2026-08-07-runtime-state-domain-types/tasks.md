# Tasks: runtime-state Data Family (Cluster Snapshot Domain Types)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~200-240 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Full data family (`ClusterGeneration`, `HealthState`, `NodeState`, `AllocationSummary`, `ClusterSnapshot`) | PR 1 | Single PR, base main; tests included per type |

## Phase 1: ClusterGeneration

- [x] 1.1 RED — test: `ClusterGeneration::initial().as_u64()` is `0`
- [x] 1.2 RED — test: `next()` advances one, pure (repeat calls on same value yield same result)
- [x] 1.3 RED — test: `from_u64`/`as_u64` round-trip
- [x] 1.4 RED — test: later generation compares greater than earlier one (`Ord`)
- [x] 1.5 RED — test: `Default` equals `initial()`
- [x] 1.6 GREEN — add `ClusterGeneration(u64)` to `crates/runtime-state/src/lib.rs`: `initial()`, `next()`, `from_u64()`, `as_u64()`, manual `Default`, `#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]`, doc comment stating observability/topology metadata only, MUST NEVER validate an Allocation Plan

## Phase 2: HealthState

- [x] 2.1 RED — test: `HealthState` variants distinct (`assert_ne!` across `Healthy`/`Degraded`/`Unhealthy`), `Copy`
- [x] 2.2 GREEN — add `enum HealthState { Healthy, Degraded, Unhealthy }`, `#[derive(Debug, Clone, Copy, PartialEq, Eq)]`, doc comment flagging variant set as inferred, not doc-mandated

## Phase 3: NodeState

- [x] 3.1 RED — test: `NodeState::new`/accessors round-trip `node`/`health`/multi-`Resource`
- [x] 3.2 RED — test: `NodeState` with an empty resource list is representable
- [x] 3.3 GREEN — add `NodeState { node: NodeId, health: HealthState, resources: Vec<Resource> }`, `#[derive(Debug, Clone, PartialEq, Eq)]`, no Trust/Membership/capability field

## Phase 4: AllocationSummary

- [x] 4.1 RED — test: `AllocationSummary::new`/accessors round-trip `allocation`/`workload`
- [x] 4.2 GREEN — add `AllocationSummary { allocation: AllocationId, workload: WorkloadId }`, `#[derive(Debug, Clone, Copy, PartialEq, Eq)]`, no lifecycle/status/phase/timestamp field

## Phase 5: ClusterSnapshot

- [x] 5.1 RED — test: `ClusterSnapshot::new`/accessors round-trip `generation`/`created_at`/`nodes`/`allocations`
- [x] 5.2 RED — test: empty `ClusterSnapshot` (no nodes, no allocations) representable
- [x] 5.3 RED — test: equality is structural (two snapshots built from equal parts are equal)
- [x] 5.4 GREEN — add `ClusterSnapshot { generation: ClusterGeneration, created_at: Timestamp, nodes: Vec<NodeState>, allocations: Vec<AllocationSummary> }`, private fields, single `new(...)`, read-only accessors, `#[derive(Debug, Clone, PartialEq, Eq)]`, no `snapshot_id`/topology/capabilities field

## Phase 6: Structural Guarantees / Crate Doc

- [x] 6.1 Review-only — confirm no API pairs `ClusterGeneration` with `AllocationPlan`/`Candidate`/admission decision (D2 guardrail)
- [x] 6.2 Review-only — confirm no `ResourceState`, `WorkloadState`, or `MembershipState` type exists anywhere in the crate
- [x] 6.3 Update crate-level doc comment: drop "Stub for" wording, keep citing both `17-cluster-snapshot.md` and `19-state-assembler.md`, keep `runtime-network`-is-data-contract-only paragraph verbatim
- [x] 6.4 Confirm `Cargo.toml` still declares exactly `runtime-primitives`, `runtime-object`, `runtime-scheduler`, `runtime-network`, zero external

## Phase 7: Verification

- [x] 7.1 Run `cargo test -p runtime-state` and `cargo clippy -p runtime-state --all-targets -- -D warnings` — both green
- [x] 7.2 Run `cargo test --workspace` and `cargo clippy --workspace --all-targets -- -D warnings` — both green
- [x] 7.3 Review `crates/runtime-state/src/lib.rs` against Success Criteria in `proposal.md`
