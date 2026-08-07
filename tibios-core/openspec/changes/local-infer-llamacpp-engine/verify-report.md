# Verify Report — `local-infer-llamacpp-engine` PR1 (tasks 1.1–1.18)

**Status**: pass-with-warnings
**Scope**: PR1 only (build story: dependency, feature gate, guard hardening, stub engine). PR2 (tasks 2.1–2.15, decode loop) is out of scope and correctly not implemented.
**State inspected**: uncommitted working tree on `main` (no PR1 commit exists yet — `git log -1` shows the last real commit is `#2 worker-local-infer-adapter` merge; all PR1 changes are unstaged working-tree modifications + one untracked new file, `runtime/src/worker/local_infer/engine/llamacpp.rs`).

## Real execution evidence (not static-only)

| Command | Result |
|---|---|
| `cargo build --workspace` (feature off) | green |
| `cargo test --workspace` (feature off) | green — 54 tests in `runtime`'s unit suite, 0 failed |
| `cargo clippy --all-targets -- -D warnings` (feature off, forced rebuild via `touch`) | clean |
| `cargo build -p runtime --features llamacpp` | green — confirmed via `Cargo.lock`/`cargo tree` that `llama-cpp-2 0.1.154` + `llama-cpp-sys-2 0.1.154` actually built and linked (cmake + bindgen), not just declared |
| `cargo test -p runtime --features llamacpp` | green — 49 unit tests + 21 `architecture_guard` tests, 0 failed; `smoke.rs` correctly reports `0 passed` (gated off) |
| `cargo clippy -p runtime --all-targets --features llamacpp -- -D warnings` (forced rebuild via `touch`) | clean |
| `cargo test -p runtime --test architecture_guard` (feature off) | 21/21 green, including both new D14 meta-tests and the still-passing legacy scan — no false positives introduced |
| `git diff main -- engine/port.rs engine/reference.rs` | empty (byte-identical, confirmed) |
| `git diff main -- Cargo.toml` on `[workspace.lints.rust]` | no hunk touches it — `unsafe_code = "deny"` unchanged |
| `rg unsafe` across `runtime/src`, `runtime/tests`, `crates/` | zero matches except one doc-comment prose mention (`crates/runtime-worker/src/ports/worker_service.rs:62`, not code) |
| `cargo tree -p runtime -e normal` vs `--features llamacpp` | `llama-cpp-2` fully absent from the default tree, present only with the feature — confirms the workspace-manifest spec's "zero non-tokio external dependency in a default build" scenario |

Task 1.18's own numbers (54 / 49 passing, 0 failed both feature states) are independently reproduced above, not just taken on trust.

## CRITICAL

None found.

## WARNING

**W1 — Spec text (`local-infer-llamacpp-engine/spec.md:43-58`) still commits to the `execution_parameters["model_path"]` mechanism, contradicted by design D10's env-var decision, and the deviation isn't recorded in the spec itself.**
Design D10 explicitly narrows/replaces proposal D4's mechanism with `TIBIOS_LOCAL_INFER_MODEL_PATH` (an environment variable), for two independent, well-argued reasons (no channel from `execution_parameters` to the engine without a port change; a per-execution path implies out-of-scope multi-model residency). PR1's own `llamacpp.rs` module doc (lines 11-15) already commits to the env-var mechanism, forward-looking to PR2. But `openspec/changes/local-infer-llamacpp-engine/specs/local-infer-llamacpp-engine/spec.md`'s "Requirement: The Model Path Is Resolved From execution_parameters At Construction" (and its two scenarios) was never updated to reflect D10 — it still says `execution_parameters["model_path"]` throughout, with no cross-reference to D10 or acknowledgment of the deviation.
This is already tracked as an explicit open item (tasks.md 1.17a, design.md Open Questions) requiring "a maintainer's yes" — so it isn't silently hidden — but the tracking lives only in tasks.md/design.md, not in the spec artifact itself, which is what `sdd-verify`'s compliance matrix is supposed to check against. Since PR1 implements no model-resolution behavior yet (that's PR2's task 2.2-2.7), this doesn't block PR1, but it must be resolved — either by amending the spec to match D10, or by getting the maintainer sign-off D10 itself asks for — before PR2 lands or `sdd-archive` runs on the full change.
*Fix*: update `local-infer-llamacpp-engine/spec.md`'s "Model Path" requirement to name `TIBIOS_LOCAL_INFER_MODEL_PATH`, or explicitly record it as "pending maintainer confirmation, see design D10" if the team wants to defer the rewrite.

**W2 — Spec text (`local-infer-llamacpp-engine/spec.md:101-109`) asserts the containment guard "requires no modification for this change to satisfy it," which is factually contradicted by design D14 and by PR1's own diff.**
D14 documents, in detail, that `engine_names_stay_inside_the_engine_module` was vacuous against the exact identifiers this change introduces (`llama_cpp_2`, `#[cfg(feature = "llamacpp")]`) and that PR1 hardens it (tasks 1.1-1.4). The diff confirms a real, non-trivial rewrite: `find_identifier_occurrences_in_files` → `find_engine_name_occurrences_in_files`, a new substring matcher, a new cfg-attribute exemption, plus two new meta-tests. The spec's own "Scenario: The existing containment scan still passes with llamacpp.rs added" sentence — "requires no modification for this change to satisfy it" — is simply wrong as written; it describes the pre-D14 (buggy) world, not what actually shipped. This isn't tracked anywhere in tasks.md's flagged open items (1.17a/b/c) — it's a new finding from this verification pass.
*Fix*: correct the requirement text to state the guard was hardened in PR1 (D14) and cite D14 directly, rather than claiming no modification occurred.

**W3 — Spec scenario "With the llamacpp feature enabled ... default_engine() returns the llama.cpp engine" (`worker-local-infer-adapter/spec.md:42-46`) has zero real-execution evidence under PR1; nothing currently invokes `default_engine()`'s feature-on branch at runtime.**
Traced every call site of the real construction path (`LocalInferWorker::new()` → `default_engine()`): `local_infer/mod.rs:94` (`build_local_infer_worker`, production only), `main.rs:75` (production binary, not exercised by `cargo test`), and `any.rs:133` (the one test call site) — which is now `#[cfg(not(feature = "llamacpp"))]`-gated by task 1.18's fix. Also confirmed `LlamaCppEngine::generate()`'s own stub rejection body has no direct unit test anywhere (`llamacpp.rs`'s `#[cfg(test)]` module only contains `the_native_backend_links_and_initialises`). Net effect: `cargo test -p runtime --features llamacpp` compiles and type-checks the feature-on `default_engine()` body, but no passing test ever calls it. The spec's THEN clause ("it returns the llama.cpp-backed engine ... type-erased behind `Arc<dyn TextGenerationEngine>`") is unverified by execution — this is exactly the gap the task prompt anticipated ("real construction is PR2, that's the stub's whole point in PR1"), but the spec's wording doesn't scope the scenario down to PR1's reality, and nothing currently closes even the cheap, model-free part of it (does `default_engine()` under the feature actually construct and return something whose `.generate()` yields the PR1 stub's rejection).
*Fix (cheap, no FFI/model needed)*: add one Tier-1/Tier-2 test — e.g. in `llamacpp.rs`'s own test module, `LlamaCppEngine::new().generate(&sample_request, &mut sink)` asserts `Err(EngineError::Rejected(msg)) if msg.contains("not implemented yet")`. This directly tests the stub without touching `default_engine()`'s cfg-selection, and is a reasonable minimum bar for a MODIFIED spec requirement under Strict TDD.

**W4 — Task 1.18's "end-to-end coverage ... moves to PR2's Tier-3 operator-run tests (task 2.12/2.13)" claim is imprecise for the two specific protocol scenarios it gates off.**
The two tests gated `#[cfg(not(feature = "llamacpp"))]` in `any.rs` are `o2_pulse_is_unknown_after_completion` and `o4_duplicate_in_flight_execute_is_rejected` — WorkerService-protocol assertions (pulse state after a completed execution; duplicate-in-flight rejection), not inference-behavior assertions. Design D12's table for PR2's four planned Tier-3 tests (`a_real_model_streams_tokens_end_to_end`, `cancelling_a_real_decode_loop_stops_well_before_max_tokens`, `two_identical_requests_produce_identical_bytes`, `a_prompt_longer_than_the_context_window_is_rejected`) does not include an o2- or o4-equivalent scenario — none of them assert pulse-after-completion or duplicate-in-flight rejection through the real dispatcher. So the literal claim that this coverage "moves to" PR2's Tier 3 is not accurate; PR2 as currently scoped restores general end-to-end wiring proof (`ExecutionPhase::Completed` through the real construction path) but not these two specific protocol properties under a real engine.
Actual regression risk is low, not hidden: `local_infer/mod.rs` — where pulse/duplicate bookkeeping actually lives — is provably unmodified by this whole change (D10, confirmed: PR2's only planned edit to it is the 2-line `#[cfg(all(test, feature = "llamacpp"))] mod real_engine;` hook), and the same o2/o4 assertions already run, feature-on and feature-off, against the real `LocalInferWorker` type via `local_infer::tests`' own `worker_conformance_suite!(worker())` (confirmed via `cargo test -p runtime --features llamacpp --bin runtime -- --list`, which lists `worker::local_infer::tests::o2_pulse_is_unknown_after_completion` and `o4_duplicate_in_flight_execute_is_rejected` as present and passing). What's genuinely untested is only the *combination* of "real production dispatcher construction path" + "o2/o4 semantics" — a narrower gap than task 1.18's wording implies.
*Fix*: tighten task 1.18's language (or add a short note to PR2's tasks.md) to say precisely what Tier-3 restores (general completion/dispatch wiring) versus what remains permanently untested through the real dispatcher (o2/o4-specific protocol properties, covered only via the deterministic-engine seam).

**W5 — `EXTERNAL_ALLOWED` ownership mismatch between the workspace-manifest delta spec and `architecture_guard.rs`'s own header doc — confirmed real, already tracked (tasks.md 1.17b), not yet reconciled.**
Verified independently: `workspace-manifest/spec.md` attributes the `EXTERNAL_ALLOWED` table edit solely to the `workspace-manifest` capability, while `architecture_guard.rs:4-5`'s header doc attributes the same table jointly to "the `workspace-manifest` and `runtime-composition-root` specs." This is exactly what task 1.17(b) already flags for reconciliation "before `sdd-archive`." No new finding here — confirming it's real and still outstanding, since it will block a clean `sdd-archive` on the full (PR1+PR2) change if left unresolved.

## SUGGESTION

**S1 — Task 1.7's acceptance criterion ("record the chosen version and its bundled llama.cpp revision in the PR description") is only half-satisfied.** The exact version pin (`llama-cpp-2 = "=0.1.154"`) is visible and verifiable in `Cargo.toml`/`Cargo.lock`, but no PR description exists yet (this is uncommitted working-tree state, no PR opened) recording the bundled upstream llama.cpp revision. Not a blocker now — there's no PR to write it into — but flag it as a checklist item when PR1 is actually opened.

**S2 — No git-history evidence of RED→GREEN sequencing for this PR1 slice.** All of PR1's changes are currently uncommitted working-tree modifications (confirmed via `git log -1` and `git status`), so there is no commit-level trail to independently verify the RED-before-GREEN ordering tasks.md claims (e.g., 1.1 RED / 1.2 GREEN, 1.3 RED / 1.4 GREEN, 1.12 RED / 1.13 GREEN). The in-file doc comments self-report RED states ("RED: ... fails to compile") but that's the same artifact claiming compliance with itself. Not flagged as a compliance failure — Strict TDD Mode doesn't mandate a specific commit granularity — but if the team wants verifiable TDD history, committing each RED/GREEN pair separately (or at least recording it in the PR description) would let a future verify pass check it independently rather than trusting task-list prose.

## Summary of what checks out cleanly

- D8's `#[cfg]`-split `default_engine()` in `engine/mod.rs` matches the design exactly, including the `use reference::DeterministicEngine;` move to avoid an unused-import warning under the feature, and the `cfg_attr(.., allow(dead_code))` on `mod reference;`.
- Task 1.18's post-hoc `deterministic_engine_for_tests()` seam is architecturally sound: it's `#[cfg(test)]`-only, lives in `engine/mod.rs` alongside `default_engine()`, and names no engine type outside `engine/` — consistent with "no engine-specific name escapes `engine/`."
- D14's guard hardening is real, correct, and doesn't introduce false positives: `hardened_engine_name_scan_catches_a_split_identifier` and `cfg_attribute_lines_are_exempt_from_the_engine_name_scan` both pass, and `engine_names_stay_inside_the_engine_module` itself still passes over the whole (enlarged) tree with zero false positives.
- `INFERENCE_ENGINE_CRATES` and `EXTERNAL_ALLOWED`'s `runtime` row are exact (`["llama-cpp-2"]` / `["tokio", "llama-cpp-2"]`), not supersets, and `the_inference_engine_dependency_is_optional_and_off_by_default` genuinely reads `cargo_metadata` (`optional`, `features["llamacpp"]`, `features["default"]`) rather than hardcoding an assumption.
- `EXPECTED_MEMBERS` stays 16 — no new workspace crate, matching D1's extend-in-place decision.
- `engine/port.rs` and `engine/reference.rs` are byte-identical to `main` (empty `git diff`), satisfying the binding "frozen port" constraint from both proposal and design.
- Feature-off behavior is byte-identical to today's: `default_engine()` still unconditionally returns `DeterministicEngine`, and the full workspace test/build/clippy sweep is clean.
- Feature-on build genuinely links (`llama-cpp-2`/`llama-cpp-sys-2` present in the built dependency tree, not just declared), and all 49+21 tests pass, matching task 1.18's numbers.
- Zero `unsafe`/`#[allow(unsafe_code)]` in workspace code; `unsafe_code = "deny"` untouched.

---

# Verify Report — `local-infer-llamacpp-engine` PR2 (tasks 2.1–2.15)

**Status**: pass-with-warnings
**Scope**: PR2 only (model lifecycle, real decode loop, Tier-3 harness, cert doc). PR1's own build story (dependency, feature gate, guard hardening) is not re-verified here — it already passed in the section above.
**State inspected**: uncommitted working tree on `main`, same as PR1 — no PR1 or PR2 commit exists yet; all changes are unstaged working-tree modifications plus two untracked new files (`engine/llamacpp.rs` full rewrite, `real_engine.rs`).

## Real execution evidence (not static-only)

| Command | Result |
|---|---|
| `cargo test --workspace` (feature off) | green — 54 passed (runtime unit suite), 22/22 `architecture_guard`, 0 failed |
| `cargo test -p runtime --features llamacpp` | green — 53 passed, **4 ignored** (exactly the 4 Tier-3 tests, by name), 0 failed; 22/22 `architecture_guard` |
| `cargo clippy --all-targets -- -D warnings` (feature off, forced rebuild via `touch`) | clean |
| `cargo clippy -p runtime --all-targets --features llamacpp -- -D warnings` (forced rebuild via `touch`) | clean |
| `cargo test -p runtime --features llamacpp --no-run` | succeeds — confirms the 4 `#[ignore]`d Tier-3 tests in `real_engine.rs` compile |
| `rg unsafe` across `llamacpp.rs`, `real_engine.rs` | zero real `unsafe`, two comment-prose mentions only |
| `git diff main -- engine/port.rs engine/reference.rs` | empty (byte-identical) |
| `EXPECTED_MEMBERS` | still 16 |
| `cargo metadata --features llamacpp` (this session, macOS aarch64) | `llama-cpp-sys-2` resolves with `features: ["common", "default", "metal"]` — see W6 |

Task 2.15's own numbers are independently reproduced above, not taken on trust.

## Specific verification findings

1. **D11 Send+Sync gate** — `assert_send_sync::<LoadedModel>()` / `::<LlamaCppEngine>()` (`engine/llamacpp.rs:126-130`) is present, uncommented, no `#[allow]` suppression, and genuinely compiles (proven by the clean clippy/test runs above, not just presence of the code). Traced the pinned crate's own source (`llama-cpp-2-0.1.154/src/model.rs:128,130`): `unsafe impl Send for LlamaModel {}` / `unsafe impl Sync for LlamaModel {}` are real, crate-authored declarations. `LlamaBackend` is `pub struct LlamaBackend {}` (zero fields) — trivially auto-`Send + Sync`. **Claim independently verified, not trusted from the comment.**

2. **`ManuallyDrop<LlamaBackend>` — sound, not a leak papered over.** Traced `impl Drop for LlamaBackend` in the pinned crate: `drop()` does `compare_exchange(true, false, ..)` on a process-global `AtomicBool`, and calls `unreachable!()` if that fails. `load_model()` sometimes constructs a **second, non-owning** `LlamaBackend {}` value when `LlamaBackend::init()` reports `BackendAlreadyInitialized` — a real, discovered hazard: in a single `cargo test` process, only the *first* caller across *all* test functions ever gets `Ok`. If that second value were ever dropped, it would either flip the shared flag to `false` while the real owner (held in the `LOADED` static) is still alive and in use, or panic on the crate's own `unreachable!()`. `ManuallyDrop` prevents both by ensuring no `Drop` ever runs through this path. Since Rust never destructs `static`s at normal process exit anyway, production behavior is unchanged — this only neutralizes a test-only, multi-init hazard. **Verdict: deliberate, correctly reasoned, checks out.**

3. **Zero `unsafe` in `llamacpp.rs` itself** — confirmed; `rg unsafe` returns only two comment-prose lines, no code.

4. **`token_to_bytes`, not `token_to_str`** — confirmed at `engine/llamacpp.rs:186-202`, implemented via `token_to_piece_bytes` with retry-on-`InsufficientBufferSpace` (the pinned crate deprecates the old `token_to_bytes` wrapper; this reimplements its logic without calling the deprecated API, so `-D warnings` stays clean). Matches D9 exactly.

5. **Rewritten 2.11 guard test does not open a containment hole.** Traced `the_feature_gate_is_named_on_exactly_one_line_outside_the_engine_subtree` (`architecture_guard.rs:1025+`): it scans outside `LOCAL_INFER_ENGINE_SRC` for non-comment lines containing `"llamacpp"`, asserts every such occurrence is a `#[cfg(...)]`-prefixed line, and asserts at least one such line lives in `local_infer/mod.rs`. This is a **separate, secondary** guard from the primary containment guard (`engine_names_stay_inside_the_engine_module`, hardened per D14, scanning `["llama", "ggml", "candle"]`), which is **not** loosened by this change. The exemption helper (`line_is_exempt_engine_name_cfg_attribute`) masks out only the literal `"llamacpp"` substring before re-checking against `llama`/`ggml`/`candle` — so a `#[cfg(...)]` line that *also* names `llama_cpp_2` directly is still caught by the primary guard. **Conclusion: sound rewrite** — it permits multiple legitimate feature-flag mentions (which PR1's own approved task 1.18 already required, in `any.rs`/`smoke.rs`), but does not weaken engine-identifier containment.

6. **`n_ctx` prompt-length bound** — confirmed at `engine/llamacpp.rs:229-234`: `if prompt_tokens.len() >= n_ctx { return Err(Rejected(..)) }`, reading `n_ctx` back from `ctx.n_ctx()` (sourced from `context_params()`). Matches D9.

7. **Cancellation halts within one token** — confirmed at `engine/llamacpp.rs:254-258`. Control flow per loop iteration: sample → EOG check → `token_to_bytes` → `sink.accept(...)` checked → `SinkVerdict::Stop` breaks **before** the next `ctx.decode()` call. Not a flag-set-and-ignored pattern — a real, one-token-bounded halt, traced directly in the decode loop's control flow.

8. **Full regression run personally, both feature states, both clippy states** — all green (see table above), not assumed from apply-progress's own numbers.

9. **`TibiBox-Certification.md` does not overclaim certification status.** The `llama.cpp`/`local-infer` row correctly stays `🔶 assumed` for **both** x86_64 and Jetson Orin (never `✅ certified`), consistent with the doc's own Phase 1 (Experimental) / Phase 2 (Certified, requires real-hardware VRAM/latency/throughput/stability measurement) process and its stated principle "Certification is earned by validation on real hardware, not assumed." **This part checks out cleanly.** The row's prose repeats the CPU-only claim from spec.md, though — see W6.

10. **Metal/GPU disclosure — confirmed real, via `cargo metadata --features llamacpp` on this machine (macOS aarch64):** `llama-cpp-sys-2` resolves with `features: ["common", "default", "metal"]`. Root cause traced to the pinned crate's **own** `Cargo.toml`: `[target.'cfg(all(target_os = "macos", any(target_arch = "aarch64", target_arch = "arm64")))'.dependencies.llama-cpp-sys-2] features = ["metal"]` — a hard, target-conditional override that is **not** gated by tibios-core's `default-features = false` on `llama-cpp-2`. On Apple Silicon, the Metal backend is compiled in and is what `LlamaBackend::init()` initializes, regardless of the model-level `n_gpu_layers(0)` mitigation (which only prevents layer-weight offload/compute, not backend registration). This contradicts spec.md Purpose's absolute claim ("no GPU, Metal, CUDA, or ROCm acceleration path exists") for the specific platform this PR was actually built and Tier-1/Tier-2 tested on. Production targets (x86_64, Jetson Orin/Linux) are unaffected (the `target_os = "macos"` condition doesn't match), and actual inference compute stays CPU-only (`n_gpu_layers(0)` verified in code) — so this is a **WARNING** (documentation/spec-wording overclaim), not a CRITICAL (no behavioral defect on the named production targets).

## WARNING (PR2)

**W6 — `spec.md` Purpose and `TibiBox-Certification.md`'s llama.cpp/local-infer row both assert "no GPU, Metal, CUDA, or ROCm acceleration path exists" unconditionally; this is false for the Apple Silicon (macOS aarch64) target this PR was actually built and tested on.**
Confirmed via `cargo metadata --features llamacpp`: `llama-cpp-sys-2` resolves with the `metal` feature active, due to `llama-cpp-2`'s own target-conditional Cargo.toml override (see finding 10), independent of `default-features = false`. Compute stays CPU-only (`n_gpu_layers(0)` verified in code), so this is not a correctness bug — but the absolute wording overclaims for at least one real, tested platform, and the gap was only privately noted in apply-progress, not surfaced in the spec or cert doc text.
*Fix*: soften `spec.md`/`TibiBox-Certification.md` wording to "no GPU compute offload (`n_gpu_layers` pinned to 0)" or explicitly disclose the macOS/Metal backend-presence caveat.

## SUGGESTION (PR2)

**S3 — no git-commit history for PR2 either**, same class as PR1's S2: all PR2 changes are uncommitted working-tree modifications, so RED→GREEN sequencing claims in `tasks.md` can't be independently verified from history, only trusted via in-file doc comments. Not a blocker under Strict TDD Mode's own rules; recommend committing PR1 and PR2 as separate, internally-ordered commit sequences before opening PRs, per D13's stacked-to-main chain strategy.

**S4 — the loosened 2.11 guard test has no upper bound on how many `#[cfg(feature = "llamacpp")]` lines may exist outside `engine/`** (today: 3 — `local_infer/mod.rs`, `any.rs`, `smoke.rs`, all legitimate). Not a real hole today (the separate, unloosened `engine_names_stay_inside_the_engine_module` guard still fully protects engine-identifier containment — see finding 5), but if this count grows unboundedly over time it could signal creeping build-conditional logic outside the intended single point. Not a blocker.

## Summary of what checks out cleanly (PR2)

- D11 Send+Sync gate is real and independently verified against the pinned crate's source (finding 1).
- `ManuallyDrop<LlamaBackend>` is sound, documented, and addresses a real, correctly-diagnosed hazard — not a masked resource-management bug (finding 2).
- Zero `unsafe` in `llamacpp.rs` (finding 3).
- `token_to_bytes` used correctly, never `token_to_str` (finding 4).
- The rewritten 2.11 guard test does not weaken engine-identifier containment; the primary hardened scan is untouched (finding 5).
- `n_ctx` bound implemented exactly per D9 (finding 6).
- Cancellation halts within one token, verified via direct control-flow trace, not assumed (finding 7).
- Full regression green in both feature states and both clippy states, independently reproduced (finding 8).
- `TibiBox-Certification.md` correctly stays "assumed," does not overclaim hardware validation (finding 9).
- PR1's stale stub test (`the_pr1_stub_rejects_every_request_without_producing_a_token`) was cleanly removed and superseded by `a_missing_model_yields_rejected_through_the_engine`, whose own doc comment says so explicitly — confirmed not left behind silently asserting something now false.
- Task 2.13 is correctly recorded as BLOCKED (operator hardware/model), not silently skipped or falsely marked done; the 4 Tier-3 tests are confirmed `#[ignore]`d and compile-clean via `--no-run`.
- `default_engine()`'s design (D8), `local_infer/mod.rs`'s 2-line diff (D10), and the file-change table in design.md are all matched exactly by the actual diff.

## Spec Compliance Matrix (PR2-relevant scenarios)

| Requirement | Scenario | Test | Result |
|---|---|---|---|
| Model path from env var | Unset path rejected | `an_unset_model_path_is_rejected_by_name` + `a_missing_model_yields_rejected_through_the_engine` | ✅ COMPLIANT |
| Model path from env var | Unloadable path rejected | `an_unloadable_model_file_is_rejected_not_panicked` + `an_empty_or_nonexistent_model_path_is_rejected` | ✅ COMPLIANT |
| Cancellation stops within one token | `SinkVerdict::Stop` halts real decoding | `cancelling_a_real_decode_loop_stops_well_before_max_tokens` (Tier-3, `#[ignore]`d, **not executed** — blocked on 2.13) | ⚠️ PARTIAL — code path traced sound (finding 7), no real execution evidence yet; expected/accepted per design's own disclosed risk |
| Real-engine tests ignored by default | `cargo test --workspace` never runs a real-model test | Empirically confirmed (54/54 feature-off, 4 ignored feature-on) | ✅ COMPLIANT |
| llama.cpp name stays inside engine module | Hardened scan catches split-identifier / exempts cfg lines | `hardened_engine_name_scan_catches_a_split_identifier`, `cfg_attribute_lines_are_exempt_from_the_engine_name_scan` | ✅ COMPLIANT |
| llama.cpp name stays inside engine module | Scan still passes with `llamacpp.rs` added | `engine_names_stay_inside_the_engine_module` | ✅ COMPLIANT |
| `default_engine()` returns the llama.cpp engine when constructible | Feature-on branch returns the real engine | `real_engine.rs`'s 4 tests (all call `build_local_infer_worker()` → `default_engine()`'s feature-on branch), Tier-3, `#[ignore]`d, **not executed** | ⚠️ PARTIAL — compiles/type-checks (`--no-run` proof), no real execution evidence until 2.13 runs; same class of gap as PR1's W3, now properly scoped into an intentionally-ignored Tier-3 test rather than absent entirely |

## Open items before archive — roll-up across BOTH PR1 and PR2 verify passes

**PR1** (from the prior verify pass, re-confirmed this session against current on-disk state):
- W1 (spec model_path text) — **RESOLVED**, confirmed: `spec.md` now names `TIBIOS_LOCAL_INFER_MODEL_PATH` throughout.
- W2 (containment guard "no modification" claim) — **RESOLVED**, confirmed: `spec.md` now describes D14's hardening explicitly.
- W3 (stub test coverage) — **RESOLVED** via clean supersession: the stub test was replaced by `a_missing_model_yields_rejected_through_the_engine` in PR2 (see finding above), not left stale.
- W4 (task 1.18 coverage-claim precision) — **RESOLVED**, confirmed: `tasks.md` carries the tightened "Precise coverage accounting" paragraph.
- W5 (`EXTERNAL_ALLOWED` ownership split between `workspace-manifest` spec and `architecture_guard.rs`'s header doc) — **STILL OPEN**, confirmed unchanged this session. Blocks a fully clean archive until reconciled.
- Maintainer sign-off (design.md Open Questions, tasks.md 1.17a) — **STILL OPEN**, procedural: (a) D10's env-var `model_path` mechanism deviates from proposal D4's `execution_parameters` mechanism; (b) D14's guard-hardening premise (proposal's Intent #3 was overstated). Both need an explicit maintainer "yes."

**PR2** (this session):
- W6 (CPU-only wording overclaim on Apple Silicon, `spec.md` + `TibiBox-Certification.md`) — **NEW, OPEN**. Needs a wording fix or explicit disclosed caveat before archive, if the team wants the spec/cert docs to be literally accurate for every platform the code has actually run on.
- Task 2.13 (Tier-3 real-model run) — **BLOCKED** on operator hardware/model, not a defect. Should be closed by an operator before the change is considered hardware-validated; whether this is a hard gate for `sdd-archive` depends on the team's bar (the proposal's own "High risk: engine never executed by automation" is already accepted, not mitigated, per design.md D12).
- S1/S2 (PR1, cosmetic) — still applicable, non-blocking.
- S3/S4 (PR2, cosmetic) — non-blocking.

**Net across the full change: zero CRITICAL findings.** One new WARNING (W6) plus one still-open WARNING from PR1 (W5) plus two procedural maintainer sign-offs remain before a fully clean `sdd-archive`.
