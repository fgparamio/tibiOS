# Tasks: Local-Infer — llama.cpp Behind the Frozen Engine Port

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | PR1 ≈ 140, PR2 ≈ 330 (total ≈ 470) |
| 400-line budget risk | PR1: Low · PR2: Medium · Single PR: High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (build story: dependency, feature gate, guard hardening) → PR 2 (decode loop: model lifecycle, real inference, Tier 3 tests) |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Medium

auto-chain resolution: proceed directly with PR1 as the next autonomous slice; no user decision pending — design D13 already fixed this boundary and its rationale (all risky infra in PR1, zero inference logic; all inference logic in PR2, gated on PR1's link-and-build proof).

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Dependency + feature gate + hardened containment guard; stub engine that always rejects | PR 1 | base `main`; independently green with feature off (no toolchain) AND on (toolchain, no model) |
| 2 | Model lifecycle, real decode loop, Tier 3 `#[ignore]`d end-to-end tests, docs | PR 2 | base = PR 1's merge commit on `main`; depends on PR 1 |

---

## PR 1 — "The door and its lock" (dependency, feature gate, guard hardening) — ~140 lines
**Base: `main`. No dependency on PR 2.**

### Phase 1.0: D14 — fix the vacuous containment guard (bug fix, lands FIRST)

- [x] 1.1 RED: add meta-test `hardened_engine_name_scan_catches_a_split_identifier` in `runtime/tests/architecture_guard.rs` (mirrors `guard_logic_catches_an_unexpected_edge`), feeding a synthetic `use llama_cpp_2::LlamaModel;` line to a not-yet-implemented substring matcher and asserting a violation is reported
- [x] 1.2 GREEN: implement `line_contains_engine_name_term(line, term)` — lowercased substring match, comment-skip preserved — and swap `engine_names_stay_inside_the_engine_module`'s check from `contains_identifier` to this matcher over `["llama", "ggml", "candle"]`. `contains_identifier` itself stays unmodified (still correct for the two async-scan tests). Confirm 1.1 passes.
- [x] 1.3 RED: add `cfg_attribute_lines_are_exempt_from_the_engine_name_scan` — a synthetic `#[cfg(feature = "llamacpp")]` line (a false positive under plain substring matching) must be exempted
- [x] 1.4 GREEN: add the exemption — trimmed line starts with `#[cfg` and its only offending term is the feature name. Confirm 1.3 passes.
- [x] 1.5 **Deviation, flagged, not silently resolved**: D13's file table places `the_feature_gate_is_named_on_exactly_one_line_outside_the_engine_subtree` in PR1. Deferred to PR2 task 2.11 instead: the line it inspects (`local_infer/mod.rs`'s `#[cfg(...)] mod real_engine;`) does not exist until PR2, so asserting "exactly one occurrence" in PR1 would be a guaranteed-red test on `main` between the two chained PRs. Recorded here and again in 1.17(c).

### Phase 1.1: Guard tests for the new dependency (RED, ahead of the manifest edit)

- [x] 1.6 RED: in `runtime/tests/architecture_guard.rs` add `const INFERENCE_ENGINE_CRATES: &[&str] = &["llama-cpp-2"];`, the table-only test `inference_engine_dependencies_are_allowlisted_for_exactly_one_crate` (mirrors `async_runtime_is_allowlisted_for_exactly_one_crate`), `the_inference_engine_dependency_is_optional_and_off_by_default` (via `cargo_metadata`: `optional == true`, `features` has a `llamacpp` key, `features["default"]` excludes it), and amend the `EXTERNAL_ALLOWED` row to `("runtime", &["tokio", "llama-cpp-2"])`. Fails: `runtime/Cargo.toml` has no such dependency yet.

### Phase 1.2: Version pin + manifest wiring (GREEN)

- [x] 1.7 Resolve the version pin (D7, apply-time task with a hard acceptance criterion): choose the newest `llama-cpp-2` release building with `default-features = false` on the developer machine; record the chosen version and its bundled llama.cpp revision in the PR description
- [x] 1.8 Modify workspace `Cargo.toml`: `[workspace.dependencies] llama-cpp-2 = { version = "=X.Y.Z", default-features = false }`. `[workspace.lints.rust]` untouched.
- [x] 1.9 Modify `runtime/Cargo.toml`: `llama-cpp-2 = { workspace = true, optional = true }`; `[features] llamacpp = ["dep:llama-cpp-2"]`, no `default` entry
- [x] 1.10 Run `cargo test -p runtime --test architecture_guard` — confirm 1.6's tests now GREEN

### Phase 1.3: Feature-gated selection in `engine/mod.rs` (GREEN)

- [x] 1.11 Implement `runtime/src/worker/local_infer/engine/mod.rs` per D8: `#[cfg_attr(feature = "llamacpp", allow(dead_code))] mod reference;`, `#[cfg(feature = "llamacpp")] mod llamacpp;`, the two `#[cfg]`-split `default_engine()` bodies, with `use reference::DeterministicEngine;` moved into the `#[cfg(not(feature = "llamacpp"))]` body (else an unused-import `-D warnings` failure under the feature). Run `cargo build && cargo clippy --all-targets -- -D warnings` with the feature off — confirm no warning.

### Phase 1.4: `LlamaCppEngine` stub (RED → GREEN)

- [x] 1.12 RED: write `the_native_backend_links_and_initialises` in `engine/llamacpp.rs`'s own `#[cfg(test)]` module (plain `#[test]`, no runtime) — fails to compile, the file doesn't exist yet
- [x] 1.13 GREEN: create `runtime/src/worker/local_infer/engine/llamacpp.rs` (new, stub): `LlamaCppEngine` (ZST) implementing `TextGenerationEngine`; `generate()` unconditionally returns `Err(EngineError::Rejected("the llama.cpp engine is not implemented yet"))`; module doc documents the `TIBIOS_LOCAL_INFER_MODEL_PATH` invocation convention (forward-looking, per D12) and backs 1.12's backend-init smoke check
- [x] 1.14 Run `cargo build -p runtime --features llamacpp && cargo test -p runtime --features llamacpp` — confirm the toolchain build/link succeeds and 1.12 passes

### Phase 1.5: Full PR1 regression sweep

- [x] 1.15 Run `cargo build`, `cargo clippy --all-targets -- -D warnings`, `cargo test --workspace` with the feature OFF and no native toolchain present — confirm byte-identical behavior to today; `default_engine()` still returns `DeterministicEngine`
- [x] 1.16 Run `cargo test -p runtime --test architecture_guard` — confirm every guard test (existing + D14 hardening + `INFERENCE_ENGINE_CRATES` table + optional/off-by-default metadata) is green; `EXPECTED_MEMBERS` stays 16

### Phase 1.6: Flag open items — do not silently resolve (closing task)

- [x] 1.17 Record three explicit open items in the PR1 description for maintainer/`sdd-verify` review:
  - (a) **D10/model_path deviation from the approved proposal**: proposal D4 said read `execution_parameters["model_path"]`; design D10 substitutes the environment variable `TIBIOS_LOCAL_INFER_MODEL_PATH` instead, because the `execution_parameters` mechanism is unreachable without a port change (traced in D10). This changes an approved proposal decision and needs explicit maintainer sign-off, not implicit acceptance.
  - (b) **`EXTERNAL_ALLOWED` ownership mismatch**: the `workspace-manifest` delta spec assigns ownership of the `EXTERNAL_ALLOWED` table edit to the `workspace-manifest` capability, but `architecture_guard.rs`'s own header doc attributes that table to "the `workspace-manifest` and `runtime-composition-root` specs" jointly. Needs reconciliation before `sdd-archive` — either amend the `workspace-manifest` spec to state shared ownership, or correct the capability attribution.
  - (c) **D14 feature-gate-line test deferred to PR2** (see 1.5): `the_feature_gate_is_named_on_exactly_one_line_outside_the_engine_subtree` moved from PR1 to PR2 task 2.11 because its precondition line does not exist until PR2's `local_infer/mod.rs` edit lands.

### Phase 1.7: Post-apply correction — engine-selection injection seam (found during review, not in the original task list)

- [x] 1.18 `cargo test -p runtime --features llamacpp` (unfiltered) surfaced 8 failing tests: `local_infer/mod.rs`'s own protocol tests (worker/channel/cancellation conformance) called `LocalInferWorker::new()`, which under the feature now resolves to the always-rejecting `LlamaCppEngine` stub instead of `DeterministicEngine` — coupling protocol tests to engine selection. Fixed with a concentrated test-only seam, not a scattered `#[cfg(test)]`:
  - `engine/mod.rs`: added `#[cfg(test)] pub(super) fn deterministic_engine_for_tests()`, unconditionally returning `reference::DeterministicEngine`, alongside `default_engine()` — no engine-specific name leaks outside `engine/` either way.
  - `local_infer/mod.rs`: the test module's `worker()` helper now calls the existing (previously single-use) `LocalInferWorker::with_engine(...)` seam with the new factory instead of `LocalInferWorker::new()`. Fixed 6 of the 8 failures.
  - The remaining 2 (`any_local_infer_conformance::o2_pulse_is_unknown_after_completion`, `o4_duplicate_in_flight_execute_is_rejected`, in `worker/any.rs`) and a 3rd found in the same sweep (`smoke.rs`'s binary-spawning test) go through the **real production dispatcher** (`any_worker()` / `main.rs`, both hardcode `WorkerKind::LocalInfer` with no seam by design — these tests exist to prove the real wiring works). Under `llamacpp` with no `TIBIOS_LOCAL_INFER_MODEL_PATH` model available in CI, they cannot complete an execution — not a dispatcher defect, an environment limitation. Gated both under `#[cfg(not(feature = "llamacpp"))]` with an explanatory comment (worded generically — "a production engine with external model artifacts" — not `llamacpp`-specific, so it doesn't need re-litigating for TensorRT-LLM/ONNX/etc. later). User-approved decision, not a silent workaround.
  - **Precise coverage accounting (verify-report W4 — the original wording overclaimed)**: PR2's four planned Tier-3 tests (design.md D12) restore general end-to-end dispatch/completion proof through the real construction path (`a_real_model_streams_tokens_end_to_end` and siblings), but none of them re-assert the *specific* o2 (pulse-after-completion) or o4 (duplicate-in-flight rejection) protocol properties — D12's table has no equivalent scenario. So "coverage moves to Tier-3" is true only for general wiring, not for these two properties specifically. Actual regression risk stays low regardless: the pulse/duplicate bookkeeping these two tests exercise lives entirely in `local_infer/mod.rs`'s `Registry`, which this whole change leaves unmodified (PR2's only planned edit there is the 2-line `#[cfg(all(test, feature = "llamacpp"))] mod real_engine;` hook, task 2.10) — and the same o2/o4 assertions already run, both feature states, against the real `LocalInferWorker` type via `local_infer::tests`' `worker_conformance_suite!(worker())` (task 1.18's seam). What remains permanently untested through the *real production dispatcher specifically* is only the narrower combination "real construction path + o2/o4 semantics" — not the properties themselves.
  - Verified: `cargo test --workspace` (feature off) and `cargo test -p runtime --features llamacpp` both fully green (54 and 49 passing respectively, 0 failed); `cargo clippy --all-targets -- -D warnings` clean both feature states.

---

## PR 2 — "The decode loop" (model lifecycle, real inference, Tier 3) — ~330 lines
**Base: PR 1's merge commit on `main`. Depends on PR 1.**

### Phase 2.0: Send + Sync gate — MUST run first, before any other PR2 task

- [x] 2.1 Implement the D11 compile-time assertion in `engine/llamacpp.rs`: `const fn assert_send_sync<T: Send + Sync>() {}` and `const _: () = { assert_send_sync::<LoadedModel>(); assert_send_sync::<LlamaCppEngine>(); };`. Run `cargo build -p runtime --features llamacpp`. **Decision point**: if it fails to compile, STOP and implement **Fallback B** (D11 — dedicated owner `std::thread` + bounded `mpsc` request/response) before any other PR2 task; record which path was taken in the PR description.

### Phase 2.1: `resolve_model_path` — pure, injectable (RED → GREEN, Tier 2)

- [x] 2.2 RED: write `an_unset_model_path_is_rejected_by_name` and `an_empty_or_nonexistent_model_path_is_rejected` (three cases: empty string, missing file, a directory) in `engine/llamacpp.rs`'s `#[cfg(test)]` module, targeting `resolve_model_path(lookup: impl Fn(&str) -> Option<OsString>) -> Result<PathBuf, String>` — not yet implemented
- [x] 2.3 GREEN: implement `resolve_model_path`, reading `TIBIOS_LOCAL_INFER_MODEL_PATH` via the injected lookup closure; every error message names the env var. Confirm 2.2 green.

### Phase 2.2: `load_model` — FFI robustness (RED → GREEN, Tier 2)

- [x] 2.4 RED: write `an_unloadable_model_file_is_rejected_not_panicked` — `load_model()` against a temp file of garbage bytes → `Err(String)`, no panic, no abort
- [x] 2.5 GREEN: implement `load_model(path) -> Result<LoadedModel, String>` (backend init + GGUF load via the pinned crate), `struct LoadedModel { backend, model }`, `context_params()`. Confirm 2.4 green.

### Phase 2.3: Process-wide lazy load through the static (RED → GREEN, Tier 2)

- [x] 2.6 RED: write `a_missing_model_yields_rejected_through_the_engine` — `LlamaCppEngine.generate(..)` with the env var unset → `Err(EngineError::Rejected(_))`, zero tokens delivered to the sink (the one test that touches the `LOADED` static)
- [x] 2.7 GREEN: implement `static LOADED: OnceLock<Result<LoadedModel, String>>` and `loaded_model()` per D11; wire `generate()`'s first step to it, replacing 1.13's stub rejection with the real path. Confirm 2.6 green.

### Phase 2.4: The decode loop

- [x] 2.8 Implement the full `generate()` decode loop per D9's shape: bounded `n_ctx` prompt-length rejection, one bounded prompt-eval `decode` call, greedy sampler, per-token `sink.accept` check with `SinkVerdict::Stop` halting before the next `decode`, `token_to_bytes` (never `token_to_str`), `sequence` counting generated tokens from 0, EOG → `stopped_early: false`. Zero `unsafe`, zero `tokio`, zero `async`/`await` anywhere in `llamacpp.rs`.
- [x] 2.9 Run `cargo test -p runtime --features llamacpp` — confirm all Tier-2 tests (2.2, 2.4, 2.6, 1.12) green

### Phase 2.5: `local_infer/mod.rs` hook + Tier 3 harness (RED → GREEN)

- [x] 2.10 Modify `runtime/src/worker/local_infer/mod.rs` (2 lines only, D10): `#[cfg(all(test, feature = "llamacpp"))] mod real_engine;` — no other production line changes in this file
- [x] 2.11 GREEN (deferred from PR1's 1.5): add `the_feature_gate_is_named_on_exactly_one_line_outside_the_engine_subtree` to `runtime/tests/architecture_guard.rs` — asserts `llamacpp` occurs on exactly one line outside `LOCAL_INFER_ENGINE_SRC`, that it lives in `local_infer/mod.rs`, and that it is a `#[cfg(...)]` attribute line. Run `cargo test -p runtime --test architecture_guard` — green now that 2.10 supplies the one qualifying line.
- [x] 2.12 RED: write the four `#[ignore]`d Tier-3 tests in new `runtime/src/worker/local_infer/real_engine.rs` per D12's table — `a_real_model_streams_tokens_end_to_end`, `cancelling_a_real_decode_loop_stops_well_before_max_tokens`, `two_identical_requests_produce_identical_bytes`, `a_prompt_longer_than_the_context_window_is_rejected` — all through `LocalInferWorker` + the real `MpscExecutionChannel`, unmodified; include the shared `required_model_path()` helper that panics with the documented invocation string when the env var is unset
- [ ] 2.13 GREEN (manual, gated on operator hardware/model): run `TIBIOS_LOCAL_INFER_MODEL_PATH=/abs/path/model.gguf cargo test -p runtime --features llamacpp -- --ignored` against a real GGUF model; confirm all four pass. Record the result and the model used in the PR description — this is the one manual verification step Tiers 1–2 cannot substitute for.
  - **BLOCKED on operator hardware/model, not on implementation.** No GGUF model file is available in this apply session/environment. The four Tier-3 tests exist, are correctly `#[ignore]`d, and are confirmed to compile cleanly (`cargo test -p runtime --features llamacpp --no-run`); `cargo test -p runtime --features llamacpp` (unfiltered) reports all four as `ignored`, never silently skipped from the count. This is the one task in PR2 an apply session cannot close — it requires an operator to supply `TIBIOS_LOCAL_INFER_MODEL_PATH` and run the command above, then record the model used and the pass/fail result here.

### Phase 2.6: Docs + final regression

- [x] 2.14 Update `docs/platform/TibiBox-Certification.md:73-76`: llama.cpp × `local-infer` moves to implemented/unvalidated
- [x] 2.15 Run full `cargo test --workspace`, `cargo test -p runtime --features llamacpp`, and `cargo clippy --all-targets -- -D warnings` with the feature both off and on; confirm zero `unsafe` and zero `#[allow(unsafe_code)]` workspace-wide, `engine/port.rs` byte-identical, and `EXPECTED_MEMBERS` still 16

---

## Rollback Notes

- Each PR reverts independently via `git revert`, in reverse order (PR2 → PR1).
- Reverting PR2 alone leaves a compiling, green workspace whose `llamacpp` build rejects every request — a safe intermediate state (proposal's own success criterion).
- Reverting PR1 restores `("runtime", &["tokio"])`, deletes the feature and the `INFERENCE_ENGINE_CRATES` guard, and returns the tree to its current state; `port.rs` and `reference.rs` were never touched, so the reverted tree *is* the current tree.
