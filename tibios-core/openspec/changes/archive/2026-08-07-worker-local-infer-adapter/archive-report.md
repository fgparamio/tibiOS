# Archive Report: `worker-local-infer-adapter`

**Archived**: 2026-08-07
**Status**: COMPLETE
**Change**: `worker-local-infer-adapter` — the second concrete `WorkerService` implementation, running a wholly synchronous, CPU-bound engine on `spawn_blocking` behind a real async/blocking boundary

---

## Executive Summary

`worker-local-infer-adapter` has been successfully archived. All 36 tasks were implemented and verified against real code (`cargo test --workspace`: 165/165; `cargo test -p runtime --features llamacpp`: 59/59, 4 ignored Tier-3), with clippy clean in both feature configurations and the architecture guard's 3 new containment scans passing. `sdd-verify` returned **PASS WITH WARNINGS**: 1 CRITICAL (a spec-merge integrity gap, not a code defect) and 2 WARNING findings. All three have since been resolved and committed to `main` before this archive ran.

---

## Closure Status

| Item | Status | Notes |
|---|---|---|
| **CRITICAL findings** | ✅ RESOLVED | See below — spec-merge reconciliation, fixed by hand. |
| **WARNING findings** | ✅ RESOLVED (2/2) | O1-O4 harness gap under `--features llamacpp` fixed in code; stale `07-performance.md:93` wording fixed. |
| **Tasks complete** | ✅ 36/36 | Verified against real code, not just checkmarks. |
| **Specs merged to main** | ✅ YES | 4 deltas merged (`worker-local-infer-adapter`, `runtime-composition-root`, `worker-inbound-port`, `worker-inprocess-adapter`); `runtime-worker` delta carried zero normative changes (doc-comment-only task note). |
| **Change folder archived** | ✅ YES | Moved to `openspec/changes/archive/2026-08-07-worker-local-infer-adapter/`. |

---

## CRITICAL Resolved: Spec-Merge Integrity

**Issue**: `openspec/specs/worker-local-infer-adapter/spec.md` already existed at verify time but contained only 1 of this change's 8 requirements. Root cause: a later, already-archived change (`local-infer-llamacpp-engine`) ran its own archive step first, found no base spec for `worker-local-infer-adapter` yet (this change hadn't been archived), and wrote its own delta out as the entire spec file — silently discarding the other 7 requirements this change defines.

**Fix applied**: Reconciled `openspec/specs/worker-local-infer-adapter/spec.md` by hand — restored all 8 requirements from this change's delta, keeping `local-infer-llamacpp-engine`'s already-shipped rewrite of the "reference engine" requirement (build-conditional `default_engine()` selection) on top, exactly as production code already behaves. Purpose section merged to keep the D0-b placement rationale and the `05-async-concurrency.md:37` property alongside the already-shipped `default_engine()` description. Committed `1a8aefe`, pushed to `main` before this archive ran.

---

## WARNINGs Resolved

### WARNING 1: O1-O4 Harness Skipped `AnyWorker::LocalInfer` Under `--features llamacpp`

**Issue**: `runtime/src/worker/any.rs` gated the shared O1-O4 conformance harness's `AnyWorker::LocalInfer` invocation behind `#[cfg(not(feature = "llamacpp"))]`, because `default_engine()` needs an operator-supplied GGUF model CI doesn't provide. This left `worker-inbound-port`'s "invoked ≥3 times, none skipped" guarantee unmet under that feature.

**Fix applied**: Added a test-only `local_infer_worker_with_deterministic_engine()` constructor (`runtime/src/worker/local_infer/mod.rs`, `#[cfg(all(test, feature = "llamacpp"))]`) and a second `any_local_infer_conformance` arm in `any.rs`, active under `--features llamacpp`, that wraps `AnyWorker::LocalInfer` around the deterministic reference engine instead of `default_engine()`. The harness now runs — and passes — under both feature configurations. Verified: 5 O1-O4 tests run under `--features llamacpp` where 0 ran before; `cargo clippy --all-targets --features llamacpp -- -D warnings` clean.

### WARNING 2: Stale "local-infer crate" Wording

**Issue**: `docs/architecture/07-performance.md:93` still said "the `local-infer` crate's choice of `llama.cpp` bindings" — D0-b established there is no `local-infer` crate, only a module inside `runtime`.

**Fix applied**: Changed `crate's` → `module's`.

Both fixes committed together with the CRITICAL fix in `1a8aefe`, pushed to `main`.

---

## Specs Synced to Main

| Domain | Action | Details |
|---|---|---|
| `worker-local-infer-adapter` | RECONCILED | All 8 requirements restored (engine port sync contract, sink policy, reference engine, sync registration, `spawn_blocking` boundary, panic re-panic, cancellation/deadline polling, factory-only exposure, O1-O4 via shared harness), keeping `local-infer-llamacpp-engine`'s already-shipped reference-engine rewrite. |
| `runtime-composition-root` | UPDATED | `Runtime Wires One Real Execution End-To-End` modified (now selects via `any_worker(kind)`/`WorkerKind`, never a concrete Worker or engine type). Two requirements added: `AnyWorker` eager-dispatch, and the architecture guard's 3 source-token containment scans (zero guard-table edits). |
| `worker-inbound-port` | UPDATED | Added the shared O1-O4 conformance harness requirement — one macro, invoked ≥3 times (now genuinely ≥3 under every feature set, see WARNING 1 above). |
| `worker-inprocess-adapter` | UPDATED | `The In-Process Worker Upholds Obligations O1-O4 Under Real Concurrency` modified to require verification through the shared harness rather than a bespoke suite; existing test suite kept as supplementary coverage. Two scenarios added. |
| `runtime-worker` | NO CHANGE | Delta carried zero ADDED/MODIFIED/REMOVED requirements — a task-level note only, correcting a doc-comment sketch in `worker_service.rs` with no observable behavior change. |

---

## Archive Contents

**Location**: `openspec/changes/archive/2026-08-07-worker-local-infer-adapter/`

- ✅ `proposal.md`
- ✅ `design.md` (372 lines)
- ✅ `tasks.md` (120 lines, 36 tasks)
- ✅ `verify-report.md` (159 lines — PASS WITH WARNINGS, 1 CRITICAL + 2 WARNING, both resolved post-verify)
- ✅ `archive-report.md` (this file)

Delta spec files under `specs/` are not carried into the archive — their content now lives in `openspec/specs/`.

---

## Real Execution Evidence

| Command | Result |
|---|---|
| `cargo test --workspace` | ✅ 165/165 |
| `cargo test -p runtime --features llamacpp` | ✅ 59/59, 4 ignored (pre-existing Tier-3, operator-run only) |
| `cargo clippy --all-targets -- -D warnings` | ✅ Clean |
| `cargo clippy --all-targets --features llamacpp -- -D warnings` | ✅ Clean |
| `architecture_guard.rs` | ✅ 22/22, including the 3 new scans this change adds |

---

## Design Decisions (D0–D14)

Followed in code with 2 documented, sound deviations (tasks 2.8, 3.15), both consistent with the spec's intent one level up (`any_worker`). D0 was settled as **D0-b**: the entire `local_infer/` subtree lives inside `runtime` as plain modules, not a new crate — see `runtime-composition-root/spec.md`'s new containment-scan requirement for how the guard proves this without a crate boundary.

---

## Source of Truth Updated

- **`openspec/specs/worker-local-infer-adapter/spec.md`** — Reconciled. All 8 requirements, source of truth for the adapter's sync/async boundary, cancellation, and factory-only exposure contracts.
- **`openspec/specs/runtime-composition-root/spec.md`** — Updated. `AnyWorker` dispatch and the local-infer containment guard are now normative.
- **`openspec/specs/worker-inbound-port/spec.md`** — Updated. The shared O1-O4 harness is now the mandatory verification mechanism for every `WorkerService` implementation.
- **`openspec/specs/worker-inprocess-adapter/spec.md`** — Updated. O1-O4 verified via the shared harness; original test suite retained as supplementary coverage.

---

## SDD Cycle Complete

The change has been fully planned, implemented, verified (pass-with-warnings), remediated (CRITICAL + both WARNINGs resolved and pushed to `main`), and archived. The reconciled and updated specs above are now the source of truth for this capability and the three it modifies.

**The `worker-local-infer-adapter` change is CLOSED.**
