# Archive Report: `runtime-scheduler-domain-types`

**Archived**: 2026-08-07
**Status**: COMPLETE
**Change**: `runtime-scheduler-domain-types` — promotes `runtime-scheduler` from stub to its Scheduling-domain data family (`Resource`, `Candidate`, `FilterResult`, `Score`, `AllocationPlan`), no Ports/algorithm

---

## Executive Summary

`runtime-scheduler-domain-types` has been successfully archived. All 15 tasks were implemented and verified against real code: `cargo test -p runtime-scheduler` (5/5) and `cargo test --workspace` both green, `cargo clippy --all-targets -- -D warnings` clean workspace-wide. No CRITICAL or WARNING findings.

---

## Closure Status

| Item | Status | Notes |
|---|---|---|
| **Tasks complete** | ✅ 15/15 | No deviations. |
| **Specs merged to main** | ✅ YES | `openspec/specs/runtime-scheduler/spec.md` — 1 requirement modified, 4 added. |
| **Change folder archived** | ✅ YES | Moved to `openspec/changes/archive/2026-08-07-runtime-scheduler-domain-types/`. |

---

## Specs Synced to Main

| Domain | Action | Details |
|---|---|---|
| `runtime-scheduler` | MODIFIED + ADDED | "Stub Crate, No Public Traits" replaced by "runtime-scheduler Exposes A Data Family, Still No Public Traits". Four requirements added: `Resource` (observable capacity only, no allocation-owned field), `Candidate` (`NodeId`+`Resource` pairing), `FilterResult` (`Feasible \| Infeasible(reason)`), `Score` (total order via `f64::total_cmp`), `AllocationPlan` (`WorkloadId`+`Candidate` binding, producer-owns-data-contract). "Exhaustive Dependency Set" requirement unchanged — still exactly `runtime-primitives` + `runtime-object`. |

Open Questions (full capability taxonomy, `AllocationPlan` Scheduling Metadata) are carried forward into the merged spec's "Open Questions" section, deferred to a future Ports/behavior change.

---

## Archive Contents

**Location**: `openspec/changes/archive/2026-08-07-runtime-scheduler-domain-types/`

- ✅ `proposal.md`
- ✅ `design.md`
- ✅ `tasks.md` (15/15 tasks, no deviations)
- ✅ `archive-report.md` (this file)

Delta spec files under `specs/` are not carried forward as the source of truth — their content now lives in `openspec/specs/runtime-scheduler/spec.md`.

---

## Real Execution Evidence

| Command | Result |
|---|---|
| `cargo test -p runtime-scheduler` | ✅ 5/5 |
| `cargo test --workspace` | ✅ All green, 0 failed |
| `cargo clippy --all-targets -- -D warnings` | ✅ Clean |
| `rg "^pub trait" crates/runtime-scheduler/src/lib.rs` | ✅ No match |
| `Cargo.toml` dependencies | ✅ Exactly `runtime-primitives` + `runtime-object`, zero external |

---

## Design Decisions Followed

Five plain value types in a single flat `lib.rs` (no submodules — `runtime-object`/`runtime-storage` precedent). `Resource` owns `id`/`version`/`capacity` directly rather than wrapping `runtime_object::LogicalObject` (which requires `ContentHash`+`ObjectType`, meaningless here); `runtime-object` stays a declared-but-unused dependency this slice. `capacity` is a plain `u64`, not a new newtype — inventing a capability taxonomy now would guess at unspecified vocabulary. `Resource` excludes allocation-owned state (`current_workload`/`reservation`/`lease`) by construction, not by comment. `Score` wraps `f64` with `Ord`/`Eq` via `f64::total_cmp` — a genuine total order including `NaN`, no fallible constructor, no external crate. `AllocationPlan` carries only its core `WorkloadId`+`Candidate` binding this slice, same "intentionally partial" precedent as `runtime-allocation`'s `AllocationContract`. No `serde` derives — only `runtime-primitives` derives serde.

---

## Source of Truth Updated

- **`openspec/specs/runtime-scheduler/spec.md`** — now the data-family spec: `Resource`, `Candidate`, `FilterResult`, `Score`, `AllocationPlan`, plus the unchanged dependency constraint. `FilterPolicy`/`ScoringPolicy`/`SchedulingStrategy` and any Port/algorithm remain unspecified, deferred to a future change.

---

## SDD Cycle Complete
