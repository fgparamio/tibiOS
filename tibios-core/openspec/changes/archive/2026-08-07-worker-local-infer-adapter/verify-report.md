# Verification Report

**Change**: worker-local-infer-adapter
**Version**: N/A (openspec delta specs, no version tag)
**Mode**: Strict TDD (orchestrator-injected; corroborated by RED-first doc comments embedded in the shipped code)

---

### Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 36 |
| Tasks complete | 36 |
| Tasks incomplete | 0 |

All 36 tasks in `openspec/changes/worker-local-infer-adapter/tasks.md` are checked `[x]`. Spot-checked the RED→GREEN pairs for the core mechanism (1.1/1.2, 1.4/1.5, 1.7/1.8, 2.2/2.3, 2.4-2.6/2.7, 3.6/3.7) against real code — all correspond to real, present implementation, not scaffolding-only.

Minor gap: tasks 2.8, 3.3, and 3.15 each reference "(see Deviations)" / "(see 3.15 Deviations)" but `tasks.md` contains no standalone "Deviations" section — the deviation notes are inlined at the task bullet itself instead, so the content exists but the cross-reference target does not. Cosmetic only (SUGGESTION below).

---

### Build & Tests Execution

**Build**: Passed (clean workspace build, both default and `--features llamacpp`)

**Tests — default features** (`cargo test --workspace`):
```
165 passed, 0 failed, 0 ignored (summed across all workspace test binaries + doctests)
Key binaries: runtime --lib 54 passed; runtime --test architecture_guard 22 passed;
runtime-worker --lib 22 passed; runtime --test smoke 1 passed; runtime --test proto_drift 3 passed;
runtime-network --lib 5 passed
```
Exit code 0. No skipped tests relevant to this change.

**Tests — `--features llamacpp`** (`cargo test -p runtime --features llamacpp`):
```
worker::* : 53 passed, 0 failed, 4 ignored
architecture_guard: 22 passed, 0 failed
```
The 4 ignored tests are the llamacpp change's own Tier-3 real-model tests, gated on `TIBIOS_LOCAL_INFER_MODEL_PATH` (not set in this environment) — pre-existing, unrelated to `worker-local-infer-adapter`'s own scope, and expected to be ignored in CI per that change's own design. No regression: `worker::local_infer::engine::llamacpp::tests::the_native_backend_links_and_initialises` and `an_unloadable_model_file_is_rejected_not_panicked` both pass, and every `worker-local-infer-adapter`-owned test (O1-O4, executor liveness, backpressure, panic propagation, cancellation/deadline) passes unchanged under the feature.

**Clippy**: `cargo clippy --all-targets -- -D warnings` → clean, 0 warnings.
`cargo clippy -p runtime --all-targets --features llamacpp -- -D warnings` → clean, 0 warnings.

**Coverage**: Not available (no coverage tool configured in this workspace) — Not available.

---

### Architecture Guard

`runtime/tests/architecture_guard.rs` — 22 tests, all green, including the three new scans this change's `runtime-composition-root` delta specifies:
- `local_infer_engine_names_no_async_runtime` — PASS
- `local_infer_engine_declares_no_async_surface` — PASS
- `engine_names_stay_inside_the_engine_module` — PASS

`EXPECTED_MEMBERS` = 16 entries, unchanged by this change (confirmed by reading the table directly). `ALLOWED` (crate-edge matrix) unchanged by this change. `EXTERNAL_ALLOWED` for `runtime` is `&["tokio", "llama-cpp-2"]` — the `llama-cpp-2` entry was added later by the separate, already-archived `local-infer-llamacpp-engine` change (commit `88cef3a`), not by `worker-local-infer-adapter`, and that addition is documented in `local-infer-llamacpp-engine`'s own spec/guard-table. `worker-local-infer-adapter` itself made zero guard-table edits, exactly as its `runtime-composition-root` delta requires ("No existing guard table changes shape").

---

### Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| D0-b: engine subtree lives at `runtime/src/worker/local_infer/`, not a new crate or `runtime-worker` module | Yes | Confirmed file tree; zero `crates/runtime-worker` src changes for the engine |
| D1/D5: canon amendment to `05-async-concurrency.md:37` | Yes | Current text matches the maintainer-approved wording verbatim |
| D2: engine choice stays inside the module | Yes | `default_engine()` is the sole exit point; `LocalInferWorker`/`AnyWorker`/`main.rs` never name a concrete engine |
| D6: engine port is `TokenSink`-driven, dyn-compatible, `std`-only | Yes | `engine/port.rs` matches exactly |
| D7: `DeterministicEngine` trivial, no sleep, caller-supplied spin cost | Yes | `engine/reference.rs` matches |
| D8: `spawn_blocking` + `Handle::current()` captured on async side, guard not moved into closure | Yes | `local_infer/mod.rs::execute` matches line-for-line |
| D9: `should_stop` polling order (closed → should_stop → deadline) | Yes | `ChannelSink::check_stop`/`accept` match the mandated order |
| D10: `AnyWorker` eager match + `Box::pin`, never `Either`/`async move` wrapper | Yes | `any.rs` matches; regression test present (`a_cancel_issued_before_the_dispatched_future_is_first_polled_is_accepted`) |
| D11: conformance harness lives in `runtime/src/worker/`, invoked ≥3 times | Partial | See WARNING below — invoked 4 times under default features, but 1 of the 4 (`AnyWorker::LocalInfer`) is compiled out under `--features llamacpp` |
| D12: three containment scans, zero table edits | Yes | Confirmed above |
| D13: three chained PR slices, S1→S2→S3 | Yes | Commits `9e85ccb`, `32207aa`, `0d01517`, each self-contained and in dependency order |
| worker_service.rs doc-sketch correction (task 3.13) | Yes | Doc comment now shows eager-match + `Box::pin` + O1 hazard note |
| File Changes table | Yes | Every file design.md lists as New/Modify is present and matches |

---

### Spec Compliance Matrix

Representative sample across all 5 delta specs (full requirement set is large; every requirement below was cross-checked against source and, where behavioral, against the real test run in Step 6b):

| Requirement | Scenario | Test | Result |
|---|---|---|---|
| Engine port wholly synchronous/std-only (`worker-local-infer-adapter`) | not async, returns no Future | `engine::port` type signatures (structural) + guard `local_infer_engine_declares_no_async_surface` | ✅ COMPLIANT |
| Engine port wholly synchronous/std-only | callable with no async runtime | `engine::reference::tests::*` (plain `#[test]`) | ✅ COMPLIANT |
| Whole-subtree token scan | no tokio/async/await in `engine/` | guard `local_infer_engine_names_no_async_runtime`, `local_infer_engine_declares_no_async_surface` | ✅ COMPLIANT |
| Engine stops on sink verdict | stop-on-`SinkVerdict::Stop` | `engine::reference::tests` (stop-on-verdict case) | ✅ COMPLIANT |
| Deterministic reference engine | identical output across runs | `engine::reference::tests` determinism test | ✅ COMPLIANT |
| Deterministic reference engine | no real inference, no sleep | `engine::reference::tests::source_names_no_real_inference_backend_and_never_sleeps` | ✅ COMPLIANT |
| No engine name outside `engine/` | scan | guard `engine_names_stay_inside_the_engine_module` | ✅ COMPLIANT |
| Duplicate in-flight rejected before blocking work queued (O1/O4 timing) | sync rejection | `local_infer::tests::o4_duplicate_in_flight_execute_is_rejected` + conformance suite | ✅ COMPLIANT |
| Dropping execute future deregisters immediately | abandonment | `local_infer::tests::dropping_the_execute_future_deregisters_immediately_...` | ✅ COMPLIANT |
| Handle::block_on inside spawn_blocking, captured on async side | spike | `local_infer::tests::handle_block_on_inside_spawn_blocking_does_not_panic_or_deadlock` | ✅ COMPLIANT |
| Executor liveness | ticker keeps advancing | `local_infer::tests::the_executor_keeps_making_progress_while_an_execution_runs` | ✅ COMPLIANT |
| Boundary backpressure | bounded channel, no deadlock | `local_infer::tests::a_bounded_channel_under_backpressure_completes_without_deadlock` | ✅ COMPLIANT |
| Panic re-panics, not swallowed | engine panic | `local_infer::tests::an_engine_panic_propagates_to_executes_caller_unchanged` | ✅ COMPLIANT |
| Cancel stops at next token boundary | explicit cancel | `local_infer::tests::o1_cancel_immediately_after_execute_is_accepted` + conformance | ✅ COMPLIANT |
| Zero-duration contract fails before first token | pre-check | `local_infer::tests::a_zero_duration_contract_fails_before_the_first_token` | ✅ COMPLIANT |
| Channel closure reported distinctly | mid-run drop | `local_infer::tests::a_channel_closure_mid_run_is_reported_distinctly_as_channel_closed` | ✅ COMPLIANT |
| Factory returns `impl WorkerService`, concrete type hidden | inspection | `any_worker()` in `mod.rs`; `build_local_infer_worker()` is `pub(super)` | ✅ COMPLIANT (one level up — documented deviation, task 2.8) |
| O1-O4 via shared harness, not bespoke suite | harness invocation | `worker_conformance_suite!(worker())` in `local_infer/mod.rs` tests | ✅ COMPLIANT |
| AnyWorker eager dispatch, never `Box<dyn>`/`Either` | inspection + regression test | `any.rs::a_cancel_issued_before_the_dispatched_future_is_first_polled_is_accepted` | ✅ COMPLIANT |
| Harness invoked ≥3 times, none skipped (`worker-inbound-port`) | invocation count | `in_process.rs` ×1, `local_infer/mod.rs` ×1, `any.rs` ×2 (default build) | ⚠️ PARTIAL — see WARNING (skipped under `--features llamacpp`) |
| `main.rs` names only `AnyWorker`/`WorkerKind` (`runtime-composition-root`) | source inspection | `runtime/src/main.rs:34,75` | ✅ COMPLIANT |
| In-process worker's 8 pre-existing tests remain, unmodified except fixture import (`worker-inprocess-adapter`) | regression | `in_process.rs` has `worker_conformance_suite!` + 8 `#[tokio::test]` fns, all passing | ✅ COMPLIANT |
| `runtime-worker` gains zero new module/trait/item (`runtime-worker` delta) | source inspection | No changes under `crates/runtime-worker/src/` except the doc-comment-only edit to `worker_service.rs` | ✅ COMPLIANT |

**Compliance summary**: 22/23 sampled scenarios COMPLIANT, 1 PARTIAL. No FAILING or UNTESTED scenarios found in the sample.

---

### Correctness (Static — Structural Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| Engine port synchronous/std-only, no `runtime_worker` import | ✅ Implemented | `engine/port.rs` |
| DeterministicEngine reference implementation | ✅ Implemented | `engine/reference.rs` |
| `execute` registers synchronously, guard never crosses closure | ✅ Implemented | `local_infer/mod.rs::execute` |
| `spawn_blocking` + captured `Handle` | ✅ Implemented | same file |
| Panic re-panics unchanged | ✅ Implemented | `resume_unwind` on `JoinHandle` error |
| Cancellation/duration polling, mandated check order | ✅ Implemented | `ChannelSink::check_stop` |
| Factory-only exposure | ✅ Implemented (documented deviation, one level up via `any_worker`) | see above |
| O1-O4 via shared harness | ✅ Implemented | `conformance.rs` + 4 invocations (3 under `llamacpp`) |
| `AnyWorker` eager dispatch | ✅ Implemented | `any.rs` |
| Architecture guard: 3 new scans, zero table edits | ✅ Implemented | confirmed above |

---

### Issues Found

**CRITICAL** (must fix before archive):

1. **`openspec/specs/worker-local-infer-adapter/spec.md` already exists but is not this change's merged spec — it is missing 7 of the 8 requirements this change defines.** Evidence: the merged file is 51 lines and contains only the "A Deterministic Reference Engine Proves The Port, Never Real Inference" requirement (itself already rewritten by the later, already-archived `local-infer-llamacpp-engine` change to describe `default_engine()`'s build-conditional selection). The other seven requirements this change's own delta defines — "The Engine Port Is Wholly Synchronous...", "The Engine Produces Tokens And Stops When Told...", "execute Registers Synchronously...", "Engine Work Runs Inside spawn_blocking...", "A Panicking Engine Re-Panics...", "Cancellation And The Duration Budget Cross The Blocking Boundary...", "The Local Infer Worker Is Exposed Only Through A Factory Function...", "The Local Infer Worker Upholds Obligations O1-O4..." — are entirely absent from `openspec/specs/worker-local-infer-adapter/spec.md`.
   Root cause, confirmed in writing: `local-infer-llamacpp-engine`'s own `archive-report.md` (line 65/79, `openspec/changes/archive/2026-08-07-local-infer-llamacpp-engine/archive-report.md`) says `worker-local-infer-adapter | CREATED | New spec copied from delta` — i.e. that later change's archive step treated `worker-local-infer-adapter` as a brand-new capability and wrote out *only its own delta* as the entire spec file, because `worker-local-infer-adapter` (this change) had not yet been archived and so had no base spec to merge against.
   Confirmed the other four capabilities this change also modifies (`runtime-composition-root`, `worker-inbound-port`, `worker-inprocess-adapter`, `runtime-worker`) have **no** trace of this change's deltas merged into `openspec/specs/` at all (`rg` for `AnyWorker`, `conformance`, `local_infer` in those merged files returns zero hits) — consistent with this change never having been archived, and NOT itself a bug.
   **Risk**: if `sdd-archive` for `worker-local-infer-adapter` naively merges this change's own `worker-local-infer-adapter/spec.md` delta over the existing (already-modified-by-a-later-change) file, it will silently revert `default_engine()`'s requirement text back to the pre-llamacpp, single-engine version — undoing already-shipped, tested behavior. If it instead does nothing because the file "already exists", the other seven requirements stay permanently unmerged.
   **Fix**: before archiving, reconcile `openspec/specs/worker-local-infer-adapter/spec.md` by hand or via a corrected merge: apply all 8 requirements from this change's delta as the base, then re-apply `local-infer-llamacpp-engine`'s already-shipped modification to the "reference engine" requirement on top (i.e. end state = this change's other 7 requirements, verbatim, plus the llamacpp-revised reference-engine requirement — which is exactly what the current 51-line file already has for that one requirement). The same reconciliation is unnecessary for the other four capabilities (`runtime-composition-root`, `worker-inbound-port`, `worker-inprocess-adapter`, `runtime-worker`) since no later change touched them — those can merge normally.

**WARNING** (should fix):

1. **The O1-O4 shared conformance harness's "invoked ≥3 times, none skipped" guarantee (`worker-inbound-port` delta) does not hold under `--features llamacpp`.** Evidence: `runtime/src/worker/any.rs:129` gates `any_local_infer_conformance` (the `AnyWorker::LocalInfer` invocation of `worker_conformance_suite!`) behind `#[cfg(not(feature = "llamacpp"))]`. This gate was added by the later `local-infer-llamacpp-engine` change (commit `88cef3a`) with a reasoned justification in its own comment (real inference needs an external GGUF model CI does not provide) — but `local-infer-llamacpp-engine/design.md` explicitly lists `runtime/src/worker/any.rs` as "Explicitly unchanged" (line 471 of its design.md), which is not accurate: `git log --all -- runtime/src/worker/any.rs` shows `88cef3a` did modify it. Net effect: under the default build the requirement holds (4 invocations, `InProcessWorker` ×1, `LocalInferWorker` ×1, `AnyWorker::InProcess` ×1, `AnyWorker::LocalInfer` ×1); under `--features llamacpp` only 3 of the 4 run. The `worker-inbound-port` spec text this change wrote has no carve-out for feature-gated engines, so this is a real (if minor and now-shipped) drift between spec and code that predates this verify but was never called out.
   **Fix**: either amend the `worker-inbound-port` delta text (in the eventual merged spec) to note the feature-gated exception explicitly, or restore the `AnyWorker::LocalInfer` conformance invocation for the `llamacpp` build using a test-injected engine seam (the same seam `local_infer/mod.rs::LocalInferWorker::with_engine` already provides) instead of always going through `default_engine()`.

2. **`docs/architecture/07-performance.md:93` still says "the `local-infer` crate's choice of `llama.cpp` bindings"**, which is now factually wrong — D0-b establishes there is no `local-infer` crate, only a module. `design.md` D5 (line 77) asserts "`18-worker-model.md:132`, `25-ai-runtime.md:42`, `07-performance.md:93` all remain true as written" — true for the first two (neither actually contains the word "crate"), but not for `07-performance.md:93`, which does. This directly contradicts the proposal's own Affected Areas table (which originally listed this line as needing a "crate" → module edit) and design.md silently dropped that edit without correcting the stale wording.
   **Fix**: either amend `07-performance.md:93` to drop "crate" (e.g. "local-infer's choice of llama.cpp bindings"), or correct design.md D5's claim that the line "remains true as written."

**SUGGESTION** (nice to have):

1. `tasks.md` tasks 2.8, 3.3, and 3.15 each say "(see Deviations)" but no "Deviations" section exists in the file — the content is present inline at each bullet, so this is purely a dangling cross-reference, not missing information. Consider adding a short "## Deviations" section consolidating the three notes, or dropping the "(see Deviations)" pointers.

---

### Verdict
PASS WITH WARNINGS

All 36 tasks are complete and verifiably correspond to real code; `cargo test --workspace` (165/165) and `cargo test -p runtime --features llamacpp` (53/53, 4 pre-existing/unrelated ignores) both pass; `cargo clippy --all-targets -- -D warnings` is clean in both configurations; the architecture guard's three new containment scans pass and zero guard tables were edited by this change, as required. Design decisions D0-D14 were followed with two documented, sound deviations (2.8, 3.15) that hold up against the spec's intent one level up (`any_worker`). This change's code is fully and durably committed on `main` (commits `9e85ccb`, `32207aa`, `0d01517`) — not sitting uncommitted in the working tree. The one CRITICAL finding is a documentation/spec-merge integrity issue, not a code defect: this change's own spec delta was never merged into `openspec/specs/`, and a later, already-archived change (`local-infer-llamacpp-engine`) wrote a partial replacement in its place that must be reconciled — by hand or a corrected merge — before `worker-local-infer-adapter` itself is archived, or seven of this change's eight normative requirements will be permanently lost from the canonical spec tree.
