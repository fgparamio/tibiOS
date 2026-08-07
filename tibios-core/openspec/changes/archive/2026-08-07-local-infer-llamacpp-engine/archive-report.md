# Archive Report: `local-infer-llamacpp-engine`

**Archived**: 2026-08-07  
**Status**: COMPLETE  
**Change**: `local-infer-llamacpp-engine` — llama.cpp as the first real text-generation engine behind the frozen `TextGenerationEngine` port

---

## Executive Summary

The `local-infer-llamacpp-engine` change has been successfully archived. All work planned across two chained PRs (PR1: build story, dependency, feature gate, guard hardening; PR2: decode loop, model lifecycle, Tier-3 real-model tests) has been completed and verified. **Zero CRITICAL findings** remain. Task 2.13 (real-model validation) was resolved 2026-08-07 via manual execution on Apple M4 hardware against `tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf` — all 4 Tier-3 tests passed. The three delta specs have been merged into main specs; the change folder has been moved to archive under this date prefix.

---

## Closure Status

| Item | Status | Notes |
|---|---|---|
| **CRITICAL findings** | ✅ NONE | Zero CRITICAL issues in verification pass. |
| **Task 2.13 (Tier-3 real-model run)** | ✅ RESOLVED | Manual execution 2026-08-07: `4 passed; 0 failed` against real GGUF model. |
| **PR1 verify pass** | ✅ PASS-WITH-WARNINGS | Tasks 1.1–1.18 complete; W1–W4 all resolved in PR2. |
| **PR2 verify pass** | ✅ PASS-WITH-WARNINGS | Tasks 2.1–2.15 complete; W6 (wording accuracy on Apple Silicon Metal) remains, with known mitigation (n_gpu_layers(0) proven effective). |
| **Specs merged to main** | ✅ YES | Three deltas merged: `local-infer-llamacpp-engine/spec.md`, `worker-local-infer-adapter/spec.md`, `workspace-manifest/spec.md` (extended). |
| **Change folder archived** | ✅ YES | Moved to `openspec/changes/archive/2026-08-07-local-infer-llamacpp-engine/`. |

---

## Open Items — All Resolved (2026-08-07, post-archive follow-up)

All four items below were open at initial archive time and have since been closed.

### W5: `EXTERNAL_ALLOWED` Ownership Mismatch — ✅ RESOLVED

**Issue**: The `workspace-manifest/spec.md` delta spec attributed the `EXTERNAL_ALLOWED` table edit solely to the `workspace-manifest` capability, while `runtime/tests/architecture_guard.rs:4-5`'s header doc attributed it jointly to both `workspace-manifest` and `runtime-composition-root` specs.

**Fix applied**: `openspec/specs/workspace-manifest/spec.md`'s "External-Dependency Allowlist Admits An Optional Inference-Engine Bindings Crate" requirement now opens with a joint-provenance note: `runtime-composition-root/spec.md` establishes `EXTERNAL_ALLOWED`'s base structure and the `("runtime", &["tokio"])` row; `workspace-manifest` governs how that row is extended for further external dependencies. Matches `architecture_guard.rs`'s own header doc exactly.

---

### D10 & D14 Maintainer Sign-Off — ✅ RESOLVED (confirmed 2026-08-07)

**Issue 1 (D10)**: Design D10 narrowed proposal D4's mechanism from `execution_parameters["model_path"]` to `TIBIOS_LOCAL_INFER_MODEL_PATH` (env var). This deviates from the approved proposal but preserves all substantive commitments (out-of-band, resolved once, no registry, missing/unloadable → `Rejected`).

**Issue 2 (D14)**: The proposal's Intent #3 claimed "the containment guards hold" for the identifiers this change introduces. D14 discovered the existing guard was vacuous against `llama_cpp_2` and `#[cfg(feature = "llamacpp")]` and hardened it. The proposal overstated the guard's readiness.

**Sign-off**: Maintainer confirmed "yes" to both on 2026-08-07. `design.md`'s Open Questions checkboxes for D10 and D14 are now checked, each annotated "Maintainer sign-off: confirmed 2026-08-07."

---

### W6: CPU-Only Wording Overclaim on Apple Silicon — ✅ RESOLVED

**Issue**: The `local-infer-llamacpp-engine/spec.md` and `TibiBox-Certification.md` both asserted "no GPU, Metal, CUDA, or ROCm acceleration path exists." This was literally false on Apple Silicon (macOS aarch64): the pinned `llama-cpp-2` crate's own `Cargo.toml` enables the Metal backend unconditionally on that target.

**Verification Evidence**: Running `TIBIOS_LOCAL_INFER_MODEL_PATH=tinyllama.gguf cargo test -p runtime --features llamacpp -- --ignored` on Apple M4 revealed `ggml_metal_device_init: GPU name: MTL0 (Apple M4)` in the logs, but a 0-byte Metal compute buffer alongside a fully populated CPU one — Metal initializes but performs zero compute work.

**Fix applied**: Both `openspec/specs/local-infer-llamacpp-engine/spec.md`'s Purpose section and `TibiBox-Certification.md`'s `local-infer` row were reworded to claim a *compute-path* guarantee (`n_gpu_layers(0)`, no GPU compute performed) rather than a *build-path* one (no GPU backend ever compiles in), and both now cite the buffer-size evidence. Production targets (x86_64, Jetson Orin) are unaffected by the Apple-Silicon-specific Metal auto-enable.

---

## Specs Synced to Main

| Domain | Action | Details |
|---|---|---|
| `local-infer-llamacpp-engine` | CREATED | New spec copied from delta. Contains 6 requirements covering feature gating, port compliance, model-path env-var mechanism, cancellation bounds, test isolation, FFI safety, and containment guards. |
| `worker-local-infer-adapter` | CREATED | New spec copied from delta. Modifies the reference-engine requirement to be build-conditional (feature-on returns real engine; feature-off returns `DeterministicEngine`). `default_engine()` signature and role as sole exit point unchanged. |
| `workspace-manifest` | UPDATED | Appended two new requirements: (1) External-dependency allowlist admits optional bindings crate, governed like any other; (2) Default build compiles zero non-tokio external dependencies into `runtime`. Added table-only guard test `INFERENCE_ENGINE_CRATES`. |

---

## Archive Contents

**Location**: `/Users/fernandogutierrezparamio/desarrollo/TibiOS/tibios-core/openspec/changes/archive/2026-08-07-local-infer-llamacpp-engine/`

- ✅ `proposal.md` (pointer to source)
- ✅ `design.md` (full design document, 505 lines)
- ✅ `tasks.md` (chained PR breakdown, tasks 1.1–2.15)
- ✅ `verify-report.md` (full verification report, PR1+PR2, 181 lines)
- ✅ `specs/local-infer-llamacpp-engine/spec.md` (new spec, 6 requirements)
- ✅ `specs/worker-local-infer-adapter/spec.md` (modified spec, 1 requirement change)
- ✅ `specs/workspace-manifest/spec.md` (delta merged into main)
- ✅ `archive-report.md` (this file)

---

## Real Execution Evidence (From Verify Pass)

### PR1 Verification (Build Story, Feature Gate, Guard Hardening)

| Command | Result |
|---|---|
| `cargo build --workspace` (feature off) | ✅ Green |
| `cargo test --workspace` (feature off) | ✅ Green — 54 tests in `runtime`, 0 failed |
| `cargo build -p runtime --features llamacpp` | ✅ Green — `llama-cpp-2 0.1.154` + `llama-cpp-sys-2 0.1.154` built and linked |
| `cargo test -p runtime --features llamacpp` | ✅ Green — 49 unit tests + 21 architecture_guard tests, 0 failed |
| `cargo clippy --all-targets -- -D warnings` | ✅ Clean (both feature states) |
| `engine/port.rs` diff | ✅ Empty (byte-identical) |
| `rg unsafe` workspace scan | ✅ Zero matches in source code |

### PR2 Verification (Decode Loop, Model Lifecycle, Tier-3 Tests)

| Command | Result |
|---|---|
| `cargo test --workspace` (feature off) | ✅ Green — 54 passed, 0 failed |
| `cargo test -p runtime --features llamacpp` | ✅ Green — 53 passed, 4 ignored (exactly the 4 Tier-3 tests) |
| `cargo clippy --all-targets -- -D warnings` (both feature states) | ✅ Clean |
| `TIBIOS_LOCAL_INFER_MODEL_PATH=tinyllama.gguf cargo test -p runtime --features llamacpp -- --ignored` (Apple M4, 2026-08-07) | ✅ 4 PASSED — `a_real_model_streams_tokens_end_to_end`, `cancelling_a_real_decode_loop_stops_well_before_max_tokens`, `two_identical_requests_produce_identical_bytes`, `a_prompt_longer_than_the_context_window_is_rejected` |

---

## Key Implementation Decisions (D7–D14)

| Decision | Outcome | Evidence |
|---|---|---|
| **D7** — `llama-cpp-2` crate + exact version pin | ✅ Implemented | Version `0.1.154` pinned in `Cargo.toml`, `Cargo.lock` committed |
| **D8** — Feature gate selects engine at compile time, no runtime condition | ✅ Implemented | `engine/mod.rs` has two `#[cfg]`-split `default_engine()` bodies; no composite/fallback logic |
| **D9** — Decode loop: pull-based, one `decode` per token, `SinkVerdict::Stop` halts by not calling `decode` again | ✅ Implemented | `engine/llamacpp.rs:254-258` shows control flow: `sink.accept()` checked → `SinkVerdict::Stop` breaks **before** next `decode()` |
| **D10** — Model path from `TIBIOS_LOCAL_INFER_MODEL_PATH` env var, process-wide lazy-loaded, **not** from `execution_parameters` | ✅ Implemented | `engine/llamacpp.rs:11-15` documents mechanism; `resolve_model_path()` is testable free function; flagged for maintainer sign-off |
| **D11** — `OnceLock`-memoised model+backend per process; fresh context per call | ✅ Implemented | `engine/llamacpp.rs` static `LOADED: OnceLock<Result<LoadedModel, String>>`; contexts created/dropped per `generate()` |
| **D12** — Three test tiers: Tier 1 (no toolchain), Tier 2 (toolchain, no model), Tier 3 (toolchain + model, `#[ignore]`d) | ✅ Implemented | 22 guard+lint tests (Tier 1); Tier-2 FFI tests in `engine/llamacpp.rs` `#[cfg(test)]`; Tier-3 in `real_engine.rs`, all `#[ignore]`d by default |
| **D13** — Auto-chain: PR1 (infra, stub) + PR2 (decode loop, real tests) | ✅ Implemented | PR1 estimated ~140 lines (guard row, feature, conditional selection, stub); PR2 ~330 lines (full decode loop, model lifecycle, tests) |
| **D14** — Harden `engine_names_stay_inside_the_engine_module` with substring matching + cfg-exemption + meta-tests | ✅ Implemented | Tasks 1.1–1.4: new matcher `line_contains_engine_name_term()`, meta-tests `hardened_engine_name_scan_catches_a_split_identifier` and `cfg_attribute_lines_are_exempt_from_the_engine_name_scan`, both pass |

---

## Verification Workload Summary

**PR1**: 
- 8 WARNINGs (W1–W4 resolved in PR2; W5 remains open, procedural).
- **Zero CRITICAL**.

**PR2**:
- 1 new WARNING (W6, wording accuracy on Apple Silicon; behavioral mitigation proven).
- **Zero CRITICAL**.

**Task 2.13** (Tier-3 real-model run):
- Previously BLOCKED on operator hardware/model.
- Resolved 2026-08-07: Manual execution on Apple M4, model `tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf`, all 4 tests passed.

**Overall**: **Pass-with-Warnings across both PR slices; all warnings documented with known mitigations or follow-ups.**

---

## Artifact Reference Trail

| Artifact | Topic Key (Engram) | File Path | Lines |
|---|---|---|---|
| **Proposal** | `sdd/local-infer-llamacpp-engine/proposal` | `openspec/changes/local-infer-llamacpp-engine/proposal.md` | 151 |
| **Design** | `sdd/local-infer-llamacpp-engine/design` | `openspec/changes/local-infer-llamacpp-engine/design.md` | 505 |
| **Tasks** | `sdd/local-infer-llamacpp-engine/tasks` | `openspec/changes/local-infer-llamacpp-engine/tasks.md` | 157 |
| **Verify Report** | `sdd/local-infer-llamacpp-engine/verify-report` | `openspec/changes/local-infer-llamacpp-engine/verify-report.md` | 181 |
| **Archive Report** | `sdd/local-infer-llamacpp-engine/archive-report` | `openspec/changes/archive/2026-08-07-local-infer-llamacpp-engine/archive-report.md` | (this file) |

---

## Source of Truth Updated

The following specs now reflect the new capability and its constraints:

- **`openspec/specs/local-infer-llamacpp-engine/spec.md`** — New. Defines the llama.cpp engine's feature-gated compilation, frozen port compliance, env-var model path mechanism, cancellation bounds, test isolation, FFI safety requirements.

- **`openspec/specs/worker-local-infer-adapter/spec.md`** — New. Defines the adapter's build-conditional engine selection: with feature on, `default_engine()` returns llama.cpp; with feature off (default), returns `DeterministicEngine`. No call-site changes required.

- **`openspec/specs/workspace-manifest/spec.md`** — Updated. Extended to cover: (1) optional inference-engine bindings crate allowlisting + `INFERENCE_ENGINE_CRATES` table-only guard; (2) default build contains zero non-tokio external dependencies into `runtime`.

---

## SDD Cycle Complete

The change has been fully planned (proposal, design, tasks), implemented (PR1 + PR2), verified (pass-with-warnings, real-model validated), and archived. The three new/modified specs are now the source of truth for this capability and its dependencies. Follow-up work (W5 reconciliation, W6 wording fix, maintainer sign-offs D10/D14, CI job with cached model) is documented in open items and can proceed asynchronously.

**The `local-infer-llamacpp-engine` change is CLOSED and ready for handoff.**
