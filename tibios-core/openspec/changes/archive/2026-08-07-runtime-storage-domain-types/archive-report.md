# Archive Report: `runtime-storage-domain-types`

**Archived**: 2026-08-07
**Status**: COMPLETE
**Change**: `runtime-storage-domain-types` — promotes `runtime-storage` from stub to its stream-primitives data family (`StreamId`, `Sequence`), no Ports/backend

---

## Executive Summary

`runtime-storage-domain-types` has been successfully archived. All 12 tasks were implemented and verified against real code: `cargo test -p runtime-storage` and `cargo test --workspace` both green, `cargo clippy --all-targets -- -D warnings` clean workspace-wide. `sdd-verify` returned **PASS** — no CRITICAL or WARNING findings.

---

## Closure Status

| Item | Status | Notes |
|---|---|---|
| **Tasks complete** | ✅ 12/12 | One documented review-only deviation (task 3.1 — see below), not a defect. |
| **Specs merged to main** | ✅ YES | `openspec/specs/runtime-storage/spec.md` — 1 requirement modified, 4 added. |
| **Change folder archived** | ✅ YES | Moved to `openspec/changes/archive/2026-08-07-runtime-storage-domain-types/`. |

---

## Deviation: Task 3.1 (Documented, Not a Defect)

**Planned**: A runtime-passing test asserting log-is-authority (no materialized "current state" bypasses the log).
**Actual**: This slice defines no "current state" type at all, so there is no behavior a test could exercise — a passing test would prove nothing. Resolved by review instead, mirroring `runtime-object`'s task 2.2 treatment of an untestable absence: `StreamId` and `Sequence` are confirmed to be `runtime-storage`'s only public types, and neither represents materialized current state. Documented inline in `lib.rs` and in `tasks.md`.

---

## Specs Synced to Main

| Domain | Action | Details |
|---|---|---|
| `runtime-storage` | MODIFIED + ADDED | "Stub Crate, No Public Traits" replaced by "runtime-storage Exposes A Data Family, Still No Public Traits". Four requirements added: `StreamId` (opaque `String` newtype, per-aggregate stream identity, equality), `Sequence` (`u64` newtype, per-stream monotonic ordinal, ordering, no `next()`/`initial()`/`Default`), Log-Is-Authority (structural-for-now, no current-state type exists), Domain-Agnosticism (no `runtime-object` reference, no payload field). "Exhaustive Dependency Set" requirement unchanged — still exactly `runtime-primitives`. |

Open Questions Q1 (legal transitions) and Q3 (monotonic progression) are recorded in the merged spec's "Open Questions" section, deferred to `runtime-object`. Q2 (transition ownership) is resolved by reference to `23-object-store.md:174-176`, not open.

---

## Archive Contents

**Location**: `openspec/changes/archive/2026-08-07-runtime-storage-domain-types/`

- ✅ `exploration.md`
- ✅ `proposal.md`
- ✅ `design.md`
- ✅ `tasks.md` (12/12 tasks, 1 documented deviation)
- ✅ `archive-report.md` (this file)

Delta spec files under `specs/` are not carried forward as the source of truth — their content now lives in `openspec/specs/runtime-storage/spec.md`.

---

## Real Execution Evidence

| Command | Result |
|---|---|
| `cargo test -p runtime-storage` | ✅ 5/5 |
| `cargo test --workspace` | ✅ All green, 0 failed |
| `cargo clippy --all-targets -- -D warnings` | ✅ Clean |
| `rg "^pub trait" crates/runtime-storage/src/lib.rs` | ✅ No match |

---

## Design Decisions Followed

Single flat `lib.rs` (no submodules — `runtime-object`/`runtime-allocation` precedent). `StreamId` mirrors `ContentHash`'s opaque-`String`-newtype shape; `Sequence` mirrors `ObjectVersion`'s `u64`-newtype shape but deliberately omits `next()`/`initial()`/`Default` since contiguity and origin policy are unresolved Slice 2/3 questions. Neither type carries a payload field or a `runtime-object` reference — domain-agnosticism enforced structurally, not by comment. No `serde` derives — only `runtime-primitives` derives serde.

---

## Source of Truth Updated

- **`openspec/specs/runtime-storage/spec.md`** — now the data-family spec: `StreamId`, `Sequence`, Log-Is-Authority, Domain-Agnosticism, plus the unchanged dependency constraint. `append`/`replay` Ports and any backend remain unspecified, deferred to a future change (Slices 2-3).

---

## SDD Cycle Complete
