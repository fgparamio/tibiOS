# Tasks: runtime-scheduler Data Family (Scheduling Domain Types)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~180-220 |
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
| 1 | Full data family (`Resource`, `Candidate`, `FilterResult`, `Score`, `AllocationPlan`) | PR 1 | Single PR, base main; tests included per type |

## Phase 1: Resource

- [x] 1.1 RED — test: `Resource::new`/accessors round-trip `id`/`version`/`capacity`
- [x] 1.2 GREEN — add `Resource { id: ObjectId, version: ObjectVersion, capacity: u64 }` to `crates/runtime-scheduler/src/lib.rs`, `#[derive(Debug, Clone, Copy, PartialEq, Eq)]`, no allocation-owned field

## Phase 2: Candidate

- [x] 2.1 RED — test: `Candidate::new`/accessors round-trip `node`/`resource`
- [x] 2.2 GREEN — add `Candidate { node: NodeId, resource: Resource }`, `#[derive(Debug, Clone, PartialEq, Eq)]`

## Phase 3: FilterResult

- [x] 3.1 RED — test: `FilterResult::Infeasible(reason)` round-trips the exact reason
- [x] 3.2 GREEN — add `enum FilterResult { Feasible, Infeasible(String) }`, `#[derive(Debug, Clone, PartialEq, Eq)]`

## Phase 4: Score

- [x] 4.1 RED — test: a higher `Score` compares greater than a lower one
- [x] 4.2 GREEN — add `Score(f64)` with `new`/`value`, `Ord`/`Eq` via `f64::total_cmp`, `#[derive(Debug, Clone, Copy, PartialEq, PartialOrd)]` + manual `Eq`/`Ord`

## Phase 5: AllocationPlan

- [x] 5.1 RED — test: `AllocationPlan::new`/accessors round-trip `workload`/`candidate`
- [x] 5.2 GREEN — add `AllocationPlan { workload: WorkloadId, candidate: Candidate }`, `#[derive(Debug, Clone, PartialEq, Eq)]`

## Phase 6: Structural Guarantees and Crate Doc

- [x] 6.1 Review-only — confirm `Resource` has no field representing current workload, reservation, or lease state; document inline in `lib.rs`
- [x] 6.2 Update crate-level doc comment: drop "stub" wording, keep citing both `14-resource-model.md` and `16-scheduling-engine.md`
- [x] 6.3 Confirm `Cargo.toml` still declares exactly `runtime-primitives` + `runtime-object`, zero external

## Phase 7: Verification

- [x] 7.1 Run `cargo test -p runtime-scheduler`, `cargo clippy -p runtime-scheduler --all-targets -- -D warnings`, `cargo check -p runtime-scheduler` — all clean
- [x] 7.2 Run `cargo test --workspace` and `cargo clippy --all-targets -- -D warnings` — all clean
- [x] 7.3 Verify no public trait declared (`rg "^pub trait" crates/runtime-scheduler/src/lib.rs` — no match)
