# Proposal: Local-Infer — llama.cpp as the First Real Text-Generation Engine

> **The port is closed; only the implementation is open.** `worker-local-infer-adapter` already froze `TextGenerationEngine`, `TokenSink`, `SinkVerdict`, `Token`, `GenerationRequest`, `GenerationSummary`, `EngineError` (`runtime/src/worker/local_infer/engine/port.rs`) and made `default_engine() -> Arc<dyn TextGenerationEngine>` the subtree's sole, type-erased exit point. This change adds a second implementor behind that exact signature. **Changing the port is out of scope.**

## Intent

`DeterministicEngine` is a spin loop that hashes bytes. It proved the blocking boundary; it has never proved the port. Three claims stay unverified until a real engine exists:

1. **The port is sufficient.** `SinkVerdict`-driven cooperative stop, `&mut dyn TokenSink`, `EngineError::Rejected` — all designed for a real loop, all only ever exercised by a placeholder. `EngineError::Rejected` is currently `#[allow(dead_code)]` (`port.rs:49`); model-load failure is its first real producer.
2. **`unsafe_code = "deny"` survives contact with FFI.** `Cargo.toml:53-54` denies it workspace-wide. D3 of the prior design committed to satisfying that via an *external* bindings crate, never a relaxation — untested until now.
3. **The containment guards hold.** `engine_names_stay_inside_the_engine_module` (`architecture_guard.rs:804`) forbids `llama`/`ggml`/`candle` outside `local_infer/engine/`. It was written before any such name existed. This change is the first thing it actually constrains.

`docs/platform/TibiBox-Certification.md:53` certifies llama.cpp as `local-infer`'s **secondary** engine — "universal compatibility", the layer "that keeps the platform from being NVIDIA-exclusive". TensorRT-LLM (primary) does not exist in either Worker. This change builds the compatibility engine, deliberately, first.

## Scope

### In Scope

- One new file, `runtime/src/worker/local_infer/engine/llamacpp.rs`: a `TextGenerationEngine` implementor backed by an external llama.cpp bindings crate, CPU-only.
- One optional external dependency on `runtime`, behind a `llamacpp` cargo feature, **off by default**.
- The `EXTERNAL_ALLOWED` row edit in `runtime/tests/architecture_guard.rs`, plus a new table-only guard (D3) pinning the bindings crate to `runtime` alone.
- Feature-conditional selection *inside* `engine/mod.rs`; `default_engine()`'s signature and every call site unchanged.
- Model path supplied out-of-band via `execution_parameters["model_path"]`; absent/unloadable → `EngineError::Rejected` (D4).
- Real-engine tests `#[ignore]`d by default; `cargo test --workspace` stays green with no native toolchain and no GGUF file.

### Out of Scope

- **Any change to the engine port** — traits, structs, error enum, `default_engine()` signature.
- **GPU/Metal/CUDA acceleration.** CPU-only. Acceleration belongs to the TensorRT-LLM primary, not the compatibility engine (D6).
- **Model resolution machinery.** No registry, no download, no `WorkloadId → GGUF` mapping (D4).
- Extracting `engine/` into `crates/local-infer/` (D1). Tokenizer configuration, sampling parameters beyond `max_tokens`, batching, KV-cache reuse, multi-model residency.
- Capability-keyed engine dispatch (`worker-local-infer-adapter/design.md:107` follow-up) and `WorkerError::UnsupportedCapability`.
- Any `tibios-ray` change.

## Capabilities

### New Capabilities

- `local-infer-llamacpp-engine`: the llama.cpp-backed `TextGenerationEngine` — its feature gate, its FFI-containment obligation, its model-path contract, its rejection semantics, and the build/test posture that keeps the toolchain optional.

### Modified Capabilities

- `worker-local-infer-adapter`: `default_engine()` becomes build-conditional while remaining the sole exit point; a real engine is now a permitted implementor of the frozen port.
- `workspace-manifest`: `runtime`'s external-dependency allowlist grows beyond `tokio`; introduces the workspace's first optional and first non-pure-Rust dependency.

## Approach

Add the engine **in place**, behind a feature flag, and pay for it with one visible manifest row and one new guard table.

| Piece | Owns | Forbidden |
|---|---|---|
| `engine/llamacpp.rs` | FFI calls, model load, decode loop, `SinkVerdict` checks | `tokio`, `async`/`await`, `unsafe`, any Worker-domain type |
| `engine/mod.rs` | `#[cfg(feature)]` selection | Leaking either engine's name upward |
| `runtime/Cargo.toml` | `llamacpp = ["dep:…"]`, `optional = true` | Being on by default |

### D1 — Extend in place; do **not** extract to a crate

The prior design named extraction as the trigger-bound follow-up: "when the FFI engine arrives with its bindings dependency, extract `local_infer/engine/` into `crates/local-infer/`" (`worker-local-infer-adapter/design.md:57`). The trigger has arrived. **Extract anyway? No — not in this change.**

Reasons, in descending force:

1. **Extraction reopens a question this change cannot answer.** D4 explicitly deferred the `local-infer` vs `runtime-local-infer` naming decision. Extraction forces it, plus `EXPECTED_MEMBERS` 16→17, plus a `02-project-structure.md` layout amendment, plus a new `EXTERNAL_ALLOWED` row — all before a single line of inference is written.
2. **The blast radius the extraction was meant to prevent does not materialize.** Argument #1 for D0-b was that `runtime-worker` must not carry the bindings dependency, because every domain crate links against it. `runtime` is the binary; nothing depends on `runtime`. An optional, default-off dependency on the composition root reaches exactly one artifact.
3. **Reversibility is unchanged.** D4's own reversibility argument still holds: the subtree has zero dependencies on anything above it, so the move remains a file move plus a manifest entry — *after* the engine works, when the naming question can be decided with evidence rather than in the abstract.
4. **Reviewer cost.** Extraction turns a contained diff into a workspace-topology change on top of the workspace's first FFI integration. Two hard things, one review.

**Extraction stays a named follow-up**, and it becomes strictly cheaper once the engine is proven.

### D2 — `unsafe_code = "deny"` is preserved, verbatim per prior D3

No `unsafe` in this repository. No crate opts out. No `#[allow(unsafe_code)]`. The bindings crate (`llama-cpp-2` or `llama_cpp`/`llama_cpp_sys` — `sdd-design` picks, with build-toolchain and maintenance as the deciding criteria) owns every `unsafe` line, exactly as `runtime-worker` delegates codegen to `prost`/`tonic`. If no candidate crate can satisfy this, **the change is blocked, not amended.**

### D3 — The guard-table edit is deliberate and visible, never silent

`EXTERNAL_ALLOWED` (`architecture_guard.rs:106`) currently reads `("runtime", &["tokio"])`. It must become `&["tokio", "<bindings-crate>"]`. Three things `sdd-design` must know:

- **`optional = true` does not exempt it.** `every_crate_declares_exactly_its_allowed_external_dependencies` reads `package.dependencies` from `cargo metadata` and filters only on `DependencyKind::Normal | Build` — optional dependencies are present regardless of feature activation. The row edit is mandatory.
- **The containment scan will not catch the manifest.** `engine_names_stay_inside_the_engine_module` walks `.rs` files under `crates/runtime-worker/src` and `runtime/src` only. `runtime/Cargo.toml` and `runtime/tests/architecture_guard.rs` are outside both. The engine name therefore enters the tree through a door no existing guard watches.
- **Therefore: add a positive guard.** Mirror `TRANSPORT_CRATES` / `ASYNC_RUNTIME_CRATES` with an `INFERENCE_ENGINE_CRATES` table-only test asserting the bindings crate is allowlisted for exactly `runtime`. Same pattern, same file, ~15 lines. This converts "someone edited a table" into "someone edited a table *and* a named invariant", which is what makes the row visible in review rather than incidental.

### D4 — Model path: out-of-band, resolved at construction, deliberately dumb

Precedent: `tibios-ray`'s archived `LlamaCppTextBackend` took `model_path` at construction and never invented resolution machinery. Same stance here — read `execution_parameters["model_path"]` alongside the existing `prompt` / `max_tokens` / `cpu_spin_iterations` keys (`local_infer/mod.rs:40-55`). Missing, unreadable, or unloadable → `EngineError::Rejected(reason)`, which the adapter already handles.

**`sdd-design` MUST NOT design a model registry, a cache, a download path, or a `WorkloadId`-to-artifact mapping.** Those are a separate change with its own storage and lifecycle concerns. A string is enough.

### D5 — Feature gate keeps the workspace toolchain-free

`llamacpp` is off by default. Unfeatured, `default_engine()` returns `DeterministicEngine` and nothing links llama.cpp — `cargo build`, `cargo clippy --all-targets -- -D warnings`, and `cargo test --workspace` need no clang, no cmake, no GGUF file, and behave byte-identically to today. `DeterministicEngine` is **not** deleted: it remains the reference implementation that the conformance harness and the executor-liveness tests depend on.

Real-engine tests are `#[ignore]` by default and require both `--features llamacpp` and an operator-supplied model. CI does not enable the feature in this change; wiring a CI job with a cached model is a follow-up.

**Open for `sdd-design`:** whether `--features llamacpp` *alone* selects the engine, or selection is additionally runtime-conditional (feature compiled in, engine chosen only when `model_path` is present). The latter is more forgiving; the former is simpler to guard. Not settled here.

### D6 — CPU-only, on purpose

No Metal, CUDA, or ROCm build flags. Acceleration multiplies the build matrix and the "works on my machine" surface, and it argues for the *primary* engine's job, not the secondary's. `TibiBox-Certification.md:52` assigns Jetson-native performance to TensorRT-LLM. Revisit only if a certification target demands it.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `runtime/src/worker/local_infer/engine/llamacpp.rs` | New | The engine; the only file naming llama.cpp |
| `runtime/src/worker/local_infer/engine/mod.rs` | Modified | `#[cfg(feature)] mod llamacpp;` + conditional `default_engine()` body |
| `runtime/src/worker/local_infer/mod.rs` | Modified | `model_path` extracted from `execution_parameters`; `GenerationRequest` unchanged **or** extended — D4 detail for `sdd-design` |
| `runtime/Cargo.toml` | Modified | Optional dependency + `[features] llamacpp` |
| `Cargo.toml` (workspace) | Modified | `[workspace.dependencies]` entry; `[workspace.lints.rust]` **untouched** |
| `runtime/tests/architecture_guard.rs` | Modified | `EXTERNAL_ALLOWED` row + `INFERENCE_ENGINE_CRATES` table test (D3) |
| `docs/platform/TibiBox-Certification.md:73-76` | Modified | llama.cpp × `local-infer` moves from "Not yet implemented" to implemented/unvalidated |
| `openspec/specs/…` | New/Modified | Per Capabilities above |

Explicitly unchanged: `engine/port.rs`, `engine/reference.rs`, `EXPECTED_MEMBERS` (stays 16), `ASYNC_RUNTIME_CRATES`, `TRANSPORT_CRATES`, the two `local_infer_engine_*` scans, and every workspace crate other than `runtime`.

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| No candidate bindings crate satisfies `unsafe_code = "deny"` from *our* side | Low | Both candidates own their `unsafe`; workspace lints do not apply to dependencies. If false, the change is **blocked** (D2), never amended. |
| Native toolchain (clang/bindgen/cmake) becomes a de facto build requirement | Med | Default-off feature (D5); success criterion asserts a clean clone builds and tests with no toolchain. |
| No GGUF model in CI → the engine is never actually executed by automation | **High** | Accepted for this change. `#[ignore]`d tests + a documented manual verification procedure; a model-cached CI job is a named follow-up. This is the one claim automation will not defend. |
| Bindings crate churn / thin maintenance (both candidates are young) | Med | The port is the insulation: the engine is one file behind a frozen trait, swappable without touching a call site. Pin an exact version. |
| The guard-table edit slips through review as noise | Med | D3's `INFERENCE_ENGINE_CRATES` test makes it a named invariant, not a list entry. |
| `EngineError::Rejected` proves insufficient for real failures (load vs decode vs OOM) | Med | Deliberately not pre-solved. If the single variant is inadequate, that is a **port change** — out of scope here; record it and raise a follow-up rather than widening scope. |
| Two hard things at once (FFI + build matrix) exceed the 400-line review budget | **High** | Auto-chain: PR1 = dependency, feature gate, guard row + table test, conditional selection returning `DeterministicEngine`; PR2 = the decode loop, `model_path`, `#[ignore]`d tests, docs. Each slice is independently green and revertible. |
| A hard-to-kill FFI decode loop ignores `SinkVerdict::Stop` | Med | Cancellation is checked per token, between decode steps; abandonment latency is bounded by one token, matching the existing abandonment test's contract. |

## Rollback Plan

Purely additive and default-off. Revert in order: delete `engine/llamacpp.rs`; revert `engine/mod.rs` to the unconditional `DeterministicEngine` body; drop `[features] llamacpp` and the optional dependency from `runtime/Cargo.toml` and the workspace `[workspace.dependencies]` entry; restore `("runtime", &["tokio"])` and delete the `INFERENCE_ENGINE_CRATES` test; revert the certification-doc rows. `port.rs` and `reference.rs` are never touched, so the reverted tree is the current tree. Under the D1 chaining, reverting PR2 alone leaves a compiling, green workspace with an unused feature flag — a safe intermediate state.

## Dependencies

- `worker-local-infer-adapter` — landed; supplies the frozen port, `default_engine()`, and the containment guards.
- One external bindings crate: `llama-cpp-2` (utilityai) or `llama_cpp`/`llama_cpp_sys` (edgenai). **`sdd-design` selects one**; criteria: owns its `unsafe`, buildable without CUDA, maintained, pinnable.
- A native C/C++ toolchain (clang + bindgen, likely cmake) — required **only** with `--features llamacpp`.
- A GGUF model file — operator-supplied, never committed, never downloaded by the build.

## Success Criteria

- [ ] `cargo build`, `cargo clippy --all-targets -- -D warnings`, and `cargo test --workspace` are green on a clean clone with **no** native toolchain and **no** model file.
- [ ] `unsafe_code = "deny"` holds workspace-wide; zero occurrences of `unsafe` and zero `#[allow(unsafe_code)]` in this repository.
- [ ] `EXPECTED_MEMBERS` still has 16 entries; `Cargo.toml` gains no workspace member.
- [ ] `engine_names_stay_inside_the_engine_module` still passes — no `llama`/`ggml`/`candle` identifier outside `local_infer/engine/`.
- [ ] `local_infer_engine_names_no_async_runtime` and `local_infer_engine_declares_no_async_surface` still pass over the enlarged subtree.
- [ ] A table-only test asserts the bindings crate is allowlisted for exactly `runtime`.
- [ ] `engine/port.rs` is byte-identical before and after; `default_engine()`'s signature is unchanged and remains the subtree's sole exit point.
- [ ] With `--features llamacpp` and a real GGUF model, `LocalInferWorker` streams real tokens end-to-end through the existing O1-O4 harness, unmodified.
- [ ] A missing or unloadable `model_path` yields `EngineError::Rejected` and a clean Worker-level failure — no panic, no hang.
- [ ] Cancellation stops a real decode loop within one token.
- [ ] `DeterministicEngine` still exists and still backs the default build.
