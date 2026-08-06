# Verification Report

**Change**: worker-grpc-adapter
**Version**: N/A (openspec, hybrid persistence)
**Mode**: Strict TDD (orchestrator-injected)

---

### Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 51 (1.1-1.6, 2.1-2.6, 3.1-3.12, 4.1-4.11, 5.1-5.13) |
| Tasks complete | 51 |
| Tasks incomplete | 0 |

All 5 phases fully checked `[x]` in `tasks.md`. Task 5.13's own Success-Criteria cross-check table is present and internally consistent with this report's independent findings (see Success Criteria section below).

---

### Build & Tests Execution

**Build**: PASS — `cargo check -p runtime-worker` exit 0 (generated code compiles from vendored `proto/` via local `protoc` at `/opt/homebrew/bin/protoc`, `libprotoc 34.1`).

**Tests**: `cargo test --workspace` — exit 0. Aggregate: **58 passed / 0 failed / 0 skipped** across all binaries with non-zero test counts:
- `runtime-primitives` unit tests: 21 passed (includes the 10 new Phase 1 round-trip tests: `parse_round_trips_valid_ulid_text`, `parse_rejects_invalid_ulid_text`, `parse_rejects_empty_text`, `identity_parse_error_display_is_not_empty`, `object_version_round_trips_valid_numeric_text`, `object_version_rejects_{non_numeric,empty,negative,overflowing}_text`, plus pre-existing content/lease/time/error tests)
- `runtime-worker` unit tests (`adapters::grpc::convert::tests::*`): 23 passed
- `runtime-worker` `tests/proto_drift.rs`: 3 passed
- `runtime` `tests/architecture_guard.rs`: 11 passed
- All other 12 crates: 0 tests (unchanged stubs), all report `ok`
- Doc-tests: 0 across 15 crates; `runtime_worker` correctly produces **no** `Doc-tests runtime_worker` block at all (confirms `[lib] doctest = false` took effect — the crate's own unit/integration tests are unaffected, as claimed)

**Clippy**: `cargo clippy --workspace --all-targets -- -D warnings` — exit 0, zero warnings. Independently re-ran `cargo clippy -p runtime-worker --all-targets -- -D warnings` — exit 0. Confirms proposal Success Criterion 8 without relying on the apply agent's self-report.

**Fmt**: `cargo fmt --check` — **exit 1**, 8 unformatted blocks, all inside files this change created/modified (`identity.rs`, `build.rs` x2, `convert.rs` x3, `proto_drift.rs`). No `rustfmt.toml` exists in the repo and fmt is not part of the proposal's 8 Success Criteria or any spec scenario, so this is **not CRITICAL** — flagged as WARNING below.

**Coverage**: Not available (no coverage tool configured in this workspace).

---

### RED/GREEN Re-Verification (Strict TDD, independent of apply agent's self-report)

The apply/tasks reports claim several tests were "RED/GREEN-verified" during authoring. I independently re-ran one live RED check rather than trusting the claim:

- Corrupted both digests in `proto/PROTO_MANIFEST.sha256` to zeros → `cargo test -p runtime-worker --test proto_drift` → `vendored_proto_digests_match_the_manifest` **FAILED** as expected, naming both files and both digest values, with the regeneration command in the failure message. Restored the manifest byte-for-byte immediately after (`git diff --stat -- proto/PROTO_MANIFEST.sha256` shows no residual diff); re-ran the same test suite → all 3 `proto_drift` tests green again.

This directly confirms proposal Success Criterion 7 ("the drift test fails when the vendored `proto/` diverges from its checksum manifest") by execution, not by reading code.

---

### Spec Compliance Matrix

#### `runtime-worker/spec.md`

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| Exhaustive Dependency Set | Declared dependencies match the allowed set | `architecture_guard.rs > every_domain_crate_declares_exactly_its_allowed_workspace_dependencies` | COMPLIANT |
| Exhaustive Dependency Set | External deps stay within the allowlist | `architecture_guard.rs > every_crate_declares_exactly_its_allowed_external_dependencies` | COMPLIANT |
| Exhaustive Dependency Set | Build-dependency stays within the allowlist | `architecture_guard.rs > every_crate_declares_exactly_its_allowed_external_dependencies` (Build kind included in filter) | COMPLIANT |
| Crate Doc Comment Cites the Owning Document | Doc comment cites the owning doc | Manual inspection: `runtime-worker/src/lib.rs:1-3` says "Implements `18-worker-model.md`." No dedicated automated test exists for this scenario. | PARTIAL (structurally correct, unguarded — no regression test) |
| Generated Transport Code Stays Private | Generated code module is not public | `architecture_guard.rs > runtime_worker_generated_code_is_included_once_in_a_private_module` | COMPLIANT |
| Generated Transport Code Stays Private | No re-export escapes the private module | `architecture_guard.rs > runtime_worker_never_reexports_the_adapter_module` | COMPLIANT |
| Generated Transport Code Stays Private | private_interfaces lint is denied | `architecture_guard.rs > runtime_worker_denies_private_interfaces_and_bounds_lints` | COMPLIANT |
| Generated Transport Code Stays Private | Public API carries no tonic/prost path | `architecture_guard.rs > runtime_worker_transport_types_stay_inside_the_private_adapter_module` | COMPLIANT |

#### `runtime-primitives/spec.md`

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| Identity Primitives Round-Trip | Valid ULID text parses successfully | `identity.rs > parse_round_trips_valid_ulid_text` | COMPLIANT |
| Identity Primitives Round-Trip | Invalid ULID text is rejected | `identity.rs > parse_rejects_invalid_ulid_text`, `parse_rejects_empty_text` | COMPLIANT |
| Identity Primitives Round-Trip | ULID-backed accessor returns the original text | `identity.rs > parse_round_trips_valid_ulid_text` (asserts `as_ulid()`'s rendered text) | COMPLIANT |
| Identity Primitives Round-Trip | ObjectVersion constructs fallibly from numeric text | `identity.rs > object_version_round_trips_valid_numeric_text` | COMPLIANT |
| Identity Primitives Round-Trip | ObjectVersion rejects non-numeric text | `object_version_rejects_{non_numeric,empty,negative,overflowing}_text` | COMPLIANT |
| Exhaustive Dependency Set / No Public Traits / Ownership Documented | (pre-existing, unaffected by this change) | pre-existing guard rows/tests | COMPLIANT (unchanged) |

#### `worker-wire-adapter/spec.md` (new capability, in full)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| Identity Wrapper Messages Convert Losslessly | Well-formed identity value round-trips | `convert.rs > {object_id,workload_id,allocation_id,object_version,content_hash}_round_trips_through_wire` | COMPLIANT |
| Identity Wrapper Messages Convert Losslessly | Invalid ULID text is rejected, not defaulted | `convert.rs > {object_id,workload_id,allocation_id}_rejects_invalid_ulid_text` | COMPLIANT |
| Identity Wrapper Messages Convert Losslessly | Invalid ObjectVersion text is rejected, not defaulted | `convert.rs > object_version_rejects_non_numeric_text` | COMPLIANT |
| Unset Required Message Fields Are Rejected | Missing required identity field fails conversion | `convert.rs > checkpoint_created_rejects_unset_checkpoint_object_id`, `execution_event_checkpoint_created_arm_rejects_missing_object_id` (both assert the error names `"checkpoint_object_id"`) | COMPLIANT |
| ExecutionEvent's Six Arms Decode Exhaustively | Each of the six arms converts | `convert.rs > execution_event_{output_chunk,progress,warning,checkpoint_created,metrics_snapshot,end_of_stream}_arm_converts` (all 6 present) | COMPLIANT |
| ExecutionEvent's Six Arms Decode Exhaustively | Unset ExecutionEvent oneof is rejected | `convert.rs > execution_event_rejects_unset_oneof` | COMPLIANT |
| ExecutionResponse's Two Arms Decode Exhaustively | Event arm converts | `convert.rs > execution_response_event_arm_converts` | COMPLIANT |
| ExecutionResponse's Two Arms Decode Exhaustively | Report arm converts | `convert.rs > execution_response_report_arm_converts` | COMPLIANT |
| ExecutionResponse's Two Arms Decode Exhaustively | Unset ExecutionResponse oneof is rejected | `convert.rs > execution_response_rejects_unset_oneof` | COMPLIANT |
| Every Conversion Rejection Is Classified Permanent | Every rejection variant classifies as Permanent | `convert.rs > every_conversion_error_variant_classifies_permanent` (all 5 variants) | COMPLIANT |
| Every Conversion Rejection Is Classified Permanent | No conversion path panics | No `unwrap()`/`expect()` in non-test `convert.rs` code (manually confirmed by reading the full file); all fallible paths return `Result` | COMPLIANT |

**Compliance summary**: 26/27 scenarios COMPLIANT, 1/27 PARTIAL (doc-comment citation — correct but unguarded by an automated test).

---

### Correctness (Static — Structural Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| `runtime-primitives` round-trip constructors | Implemented | `identity.rs:56-74` (`parse`/`as_ulid` in the macro), `:145-160` (`ObjectVersion::from_u64`/`as_u64`), `IdentityParseError` exported from `lib.rs:19` |
| Vendored `proto/` + manifest | Implemented | `proto/{README.md,PROTO_MANIFEST.sha256,tibios/**}` present, byte-identical layout to umbrella tree; manifest format matches `shasum -a 256` exactly |
| `build.rs` + private `adapters/` tree | Implemented | `include_file` was available on `tonic-build 0.13` (fallback not needed, contrary to the design's pre-argued friction point) |
| `convert.rs` fallible conversion layer | Implemented | All 5 identity messages + both oneofs, `ConversionError` classified `Permanent` via a private `Classify` trait |
| `architecture_guard.rs` per-crate allowlist + containment scan | Implemented | `EXTERNAL_ALLOWED` (16 rows), `TRANSPORT_CRATES`, 4 new/replacing tests, doc comment updated per task 5.11 |

---

### Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| D5 (`protoc` required, preflight panic) | Yes | `build.rs:60-77` matches the design's exact shape: `PROTOC` env check first, then `PATH` scan, panic message names the OS install commands, `PROTOC=` override, and `proto/README.md` |
| D5 Consequence: `build_server(false)` | Yes | `build.rs:43` |
| D5 friction point: `include_file` availability | Resolved without fallback | `tonic-build 0.13`'s `Builder` DOES expose `include_file` (`build.rs:49`); the pre-argued `prost_build::Config` fallback was not needed. Confirmed by successful `cargo check -p runtime-worker` |
| D6 (`EXTERNAL_ALLOWED` assoc-list, `diff_dependencies` reuse) | Yes | `architecture_guard.rs:90-107`, same shape as `ALLOWED`, `diff_dependencies` shared at `:156-171` |
| D7 (source-token containment scan, 3 tests + `deny` lint) | Yes | `architecture_guard.rs:403-608`, all 4 tests present (task 5.10 added a 4th dedicated test rather than extending 5.9, per its own note — a documented, harmless deviation from "3 tests" phrasing) |
| D8 (vendored `proto/` at repo root + manifest + drift tests) | Yes | Repo-root `proto/` (not nested under `runtime-worker`), 3 tests in `proto_drift.rs`, umbrella-comparison test gracefully no-ops when absent |
| Undocumented deviation: `compile_well_known_types(true)` | Yes, and correct | `build.rs:48`. Not mentioned in design.md, but its stated purpose (compile `google.protobuf.Duration` locally instead of adding `prost-types` as a dependency) is verified: `Cargo.lock` shows `prost-types` present only as a *transitive* dependency of `tonic`/`prost-build`, never a direct dependency of `runtime-worker` (confirmed via `rg -n "prost-types" Cargo.lock` — no `runtime-worker` entry references it directly). `EXTERNAL_ALLOWED`'s `runtime-worker` row stays `{prost, tonic, tonic-build}` exactly, so D6's allowlist is not violated. This deviation is additive-safe and does not need a design amendment, but should be added to design.md before archive for future-reader accuracy (WARNING, not CRITICAL). |
| Undocumented deviation: `[lib] doctest = false` | Yes, and correct | `Cargo.toml:19`, with an inline comment explaining the `google.protobuf.Duration` doc-comment/rustdoc conflict. Confirmed empirically: `cargo test --workspace` shows zero `Doc-tests runtime_worker` block (vs. 0-test blocks for the other 15 crates), and all 23 `#[cfg(test)]` unit tests plus 3 `proto_drift.rs` integration tests still ran and passed — the claim "no unit/integration tests affected" holds. Same as above: additive-safe, but undocumented in design.md (WARNING). |

---

### Success Criteria Cross-Check (proposal.md, 8 items — independently verified, not just re-stating tasks.md's own table)

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 1 | `cargo check -p runtime-worker` succeeds, generated code compiled from vendored `proto/` | PASS | Direct re-run, exit 0 |
| 2 | `mod adapters` carries no `pub`; no `pub use` names it; `private_interfaces` is `deny` | PASS | `runtime_worker_never_reexports_the_adapter_module` + `runtime_worker_denies_private_interfaces_and_bounds_lints`, both green; manual read of `lib.rs`/`adapters/mod.rs`/`grpc/mod.rs` confirms no `pub` anywhere on the module chain |
| 3 | No `tonic::`/`prost::` path in `runtime-worker`'s public API | PASS | `runtime_worker_transport_types_stay_inside_the_private_adapter_module`, green |
| 4 | `architecture_guard.rs` asserts `{tonic, prost, tonic-build}` on `runtime-worker` and nowhere else, fails when another crate gains them | PASS | `transport_dependencies_are_allowlisted_for_exactly_one_crate` + `every_crate_declares_exactly_its_allowed_external_dependencies`, both green; underlying `diff_dependencies` logic independently meta-tested by `guard_logic_catches_{an_unexpected,a_missing}_edge` |
| 5 | `cargo metadata` still lists exactly 16 members; `ALLOWED` matrix unchanged | PASS | Direct `cargo metadata --no-deps` → 16 packages, names match `EXPECTED_MEMBERS` exactly; `ALLOWED`'s `runtime-worker` row unchanged (`["runtime-primitives", "runtime-allocation", "runtime-object"]`) |
| 6 | `TryFrom` rejects invalid ULID, unset required message, unset `oneof` — each `ErrorClass::Permanent` | PASS | All corresponding `convert.rs` tests green, including `every_conversion_error_variant_classifies_permanent` covering all 5 variants |
| 7 | Drift test fails when vendored `proto/` diverges from checksum manifest | PASS | Independently RED-verified live (see "RED/GREEN Re-Verification" above), not just read from code |
| 8 | `cargo clippy --workspace -- -D warnings` is clean without crate-wide allows | PASS | Direct re-run (both `--workspace` and `-p runtime-worker` individually), exit 0, 0 warnings; only scoped allows found are `#[allow(missing_docs, clippy::all, clippy::pedantic)]` on the `mod grpc;` declaration (module-scoped) and `#![allow(dead_code)]` at the top of `convert.rs` (also module-scoped, not crate-wide) |

**8/8 Success Criteria: PASS.**

---

### Git History / Commit Hygiene Check

`git log --stat 22c505a..9639a92` confirms exactly the 5 expected commits, in the expected order, each touching only its phase's files:

| Commit | Files touched | Note |
|---|---|---|
| `22c505a` | `identity.rs`, `lib.rs` (implied), `tasks.md` | Phase 1 |
| `a0fcb64` | `proto/{README.md,PROTO_MANIFEST.sha256,tibios/**}`, `tasks.md` | Phase 2 |
| `af5770c` | `Cargo.lock`, `Cargo.toml` (root+crate), `build.rs`, `adapters/{mod.rs,grpc/mod.rs}`, `lib.rs`, `proto_drift.rs`, `tasks.md` | Phase 3 |
| `a6f902e` | `convert.rs`, `tasks.md` | Phase 4 |
| `9639a92` | `architecture_guard.rs`, `tasks.md` | Phase 5 |

Phase 4 and Phase 5's concurrent `tasks.md` edits landed in **separate commits** (`a6f902e` then `9639a92`), not squashed into one — the noted risk ("shared `tasks.md` edits landing in the same commit") did **not** materialize. Read the final `tasks.md` in full: no duplicated headings, no orphaned merge markers, Phase 4's 4.1-4.11 and Phase 5's 5.1-5.13 (including the 5.13 cross-check table) are both present exactly once, content is coherent. No content loss or duplication found.

No unexpected files are mixed into these 5 commits — each commit's diff is scoped to its phase as designed.

---

### Uncommitted Artifacts Check (openspec mode requirement)

`git status --short` (working tree, checked before AND after this verify run — identical both times):

```
 M openspec/specs/runtime-primitives/spec.md
 M openspec/specs/runtime-worker/spec.md
?? openspec/changes/worker-grpc-adapter/design.md
?? openspec/changes/worker-grpc-adapter/proposal.md
?? openspec/specs/worker-wire-adapter/
```

`tasks.md` IS committed (tracked across all 5 commits, confirmed via `git log -- tasks.md`). But `proposal.md`, `design.md`, and all 3 spec deltas (`runtime-worker` modified, `runtime-primitives` modified, `worker-wire-adapter` new) are **NOT committed** — they exist only as working-tree changes/untracked files. This is flagged as a WARNING: these MUST be committed before `sdd-archive`, or the archived record will not reflect the actual planning artifacts that governed this implementation.

(Unrelated noise also present in `git status`, outside this change's scope: `../README.md`, `README.md`, `../tibios-ray/.claude/` — not evaluated, not this change's responsibility.)

---

### Issues Found

**CRITICAL** (must fix before archive): **None.**

**WARNING** (should fix):
1. `proposal.md`, `design.md`, and all 3 spec files (`runtime-worker/spec.md`, `runtime-primitives/spec.md`, `worker-wire-adapter/spec.md`) are uncommitted (working-tree modifications / untracked). Commit them before `sdd-archive` so the archived record matches what was actually implemented and verified.
2. `cargo fmt --check` fails with 8 unformatted blocks across `identity.rs`, `build.rs`, and `convert.rs` (all files this change authored). Not a project-enforced gate (no `rustfmt.toml`, not in success criteria), but should be run and committed for consistency with future contributors' expectations.
3. Two implementation decisions were made during apply that are not recorded in `design.md`: `compile_well_known_types(true)` (avoids a `prost-types` direct dependency) and `[lib] doctest = false` (works around non-Rust doc-comment content in generated `google.protobuf.Duration` bindings). Both are verified correct and additive-safe, but design.md should be amended with a short "Consequences" note for each so a future reader doesn't mistake them for accidental deviations.
4. The `runtime-worker/spec.md` scenario "Doc comment cites the owning doc" (crate doc comment citing `18-worker-model.md`) has no dedicated automated test — it is correct today (manually confirmed) but unguarded against regression, unlike its `runtime-primitives` counterpart which is also untested but at least pre-existing/unchanged by this task set.

**SUGGESTION** (nice to have):
1. Consider adding a `rustfmt.toml` (even an empty one, pinning defaults) plus a `cargo fmt --check` step to whatever CI eventually gets written for this repo — the repo currently has none (`.github/`, `Makefile`, `justfile` all absent, consistent with design.md D5's own observation).
2. `task 5.10`'s self-note ("Extend 5.9 (or add a 4th, dedicated test)") chose the 4th-test path — worth a one-line mention in `design.md`'s D7 section that the final shape is 4 tests, not the 3 originally described, purely for documentation accuracy.

---

### Verdict

**PASS WITH WARNINGS**

Zero CRITICAL issues. All 51 tasks complete, all 8 proposal Success Criteria independently re-verified (not just re-stated), 58/58 real tests pass (`cargo test --workspace`, exit 0), `cargo clippy --workspace -- -D warnings` clean (exit 0), the drift-detection guard was independently RED/GREEN re-verified by live execution, and both undocumented implementation deviations (`compile_well_known_types(true)`, `doctest = false`) were checked against the allowlist/architecture invariants and found safe. The 4 WARNINGs (uncommitted planning artifacts, `cargo fmt` cleanliness, two undocumented-but-safe design deviations, one untested doc-comment scenario) should be addressed before `sdd-archive` but do not block it on correctness grounds. This change is a candidate for `sdd-archive` once the uncommitted `openspec/` artifacts are committed.
