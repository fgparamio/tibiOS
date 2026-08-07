# Local Infer llama.cpp Engine Specification

## Purpose

`local-infer-llamacpp-engine` is the second implementor of `TextGenerationEngine` (`runtime/src/worker/local_infer/engine/port.rs`) — the first to perform real inference. It lives entirely inside `local_infer/engine/llamacpp.rs`, behind an off-by-default `llamacpp` Cargo feature on `runtime`, and is backed by an external llama.cpp bindings crate that owns every `unsafe` line the workspace-wide `unsafe_code = "deny"` lint forbids everywhere else. It changes nothing about the frozen port (`worker-local-infer-adapter/spec.md`): no new trait, no new method, no new error variant, no change to `default_engine()`'s signature.

This engine performs no GPU-accelerated compute, deliberately: model parameters set `n_gpu_layers(0)`, so no layer is ever offloaded to a GPU — acceleration belongs to the platform's primary (TensorRT-LLM) engine, not this compatibility engine (`local-infer-llamacpp-engine/proposal.md` D6). This is a compute-path guarantee, not a build-path one: on a platform where the pinned bindings crate compiles in a GPU backend by default (confirmed via `cargo metadata`: Apple Silicon macOS pulls in Metal regardless of `default-features = false`), that backend still initializes at the process level, but `n_gpu_layers(0)` keeps it idle — verified by a real decode run showing a 0-byte Metal compute buffer alongside a fully populated CPU one. There is no scenario below asserting the absence of GPU *code*, only of GPU *compute*: a compiled-in-but-idle backend is not independently distinguishable from an absent one except by the buffer-size evidence above, and no scenario re-derives that evidence on every run.

## Requirements

### Requirement: Compilation Is Gated Behind An Off-By-Default Feature; The Unfeatured Workspace Needs No Native Toolchain Or Model

`runtime/src/worker/local_infer/engine/llamacpp.rs` and its external bindings dependency MUST be compiled only when the `llamacpp` Cargo feature on `runtime` is enabled; that feature MUST be off by default. With the feature disabled, `cargo build`, `cargo clippy --all-targets -- -D warnings`, and `cargo test --workspace` MUST succeed on a clean clone with no native C/C++ toolchain (no clang, no bindgen, no cmake) and no GGUF model file present anywhere on disk.

#### Scenario: A clean clone builds, lints, and tests cleanly with the feature off and no toolchain or model present

- GIVEN a clean clone of the workspace, the `llamacpp` feature never enabled, no native C/C++ toolchain installed, and no GGUF model file anywhere on disk
- WHEN `cargo build`, `cargo clippy --all-targets -- -D warnings`, and `cargo test --workspace` are run
- THEN all three succeed

#### Scenario: The feature is off unless explicitly requested

- GIVEN `runtime/Cargo.toml`'s `[features]` table
- WHEN it is inspected
- THEN `llamacpp` is not a member of the `default` feature set

### Requirement: The llama.cpp Engine Implements The Frozen TextGenerationEngine Port, Unmodified

The llama.cpp engine type MUST implement `TextGenerationEngine` (`generate(&self, request: &GenerationRequest, sink: &mut dyn TokenSink) -> Result<GenerationSummary, EngineError>`) exactly as defined in `engine/port.rs`, with no change to that trait, to `GenerationRequest`, `Token`, `GenerationSummary`, `EngineError`, `SinkVerdict`, or `TokenSink`. `engine/port.rs` MUST be byte-identical before and after this change.

#### Scenario: engine/port.rs is untouched

- GIVEN `runtime/src/worker/local_infer/engine/port.rs` before this change lands and after it lands
- WHEN the two versions are diffed
- THEN they are byte-identical

#### Scenario: The llama.cpp engine type satisfies TextGenerationEngine without any trait change

- GIVEN the llama.cpp engine type defined in `llamacpp.rs`
- WHEN it is used as a `TextGenerationEngine` trait object (e.g. bound to `Arc<dyn TextGenerationEngine>`)
- THEN it compiles and is callable through the existing trait's `generate` method signature, unchanged

### Requirement: The Model Path Is Resolved From An Environment Variable At Construction; A Missing Or Unloadable Model Rejects, Never Panics

Deviation from the approved proposal, tracked pending maintainer sign-off (design.md D10, tasks.md 1.17a): the proposal's D4 named `execution_parameters["model_path"]` as the mechanism, but `execution_parameters` has no channel into the engine without a port change, which is out of scope for this change. The llama.cpp engine instead MUST resolve its model from the `TIBIOS_LOCAL_INFER_MODEL_PATH` environment variable, read once and cached process-wide (design.md D11). A missing environment variable, an unreadable path, or a path that fails to load as a valid model MUST produce `EngineError::Rejected(reason)` — never a panic, never a hang — which the adapter's existing `Err(EngineError::Rejected(reason))` handling (`local_infer/mod.rs`, `run_off_executor`) already turns into a `Failed` terminal report.

#### Scenario: An unset model path is rejected

- GIVEN `TIBIOS_LOCAL_INFER_MODEL_PATH` is unset
- WHEN the llama.cpp engine is asked to generate for any request
- THEN it returns `Err(EngineError::Rejected(reason))`, and the Worker-level execution reaches a `Failed` terminal phase with no panic and no hang

#### Scenario: An unloadable model path is rejected

- GIVEN `TIBIOS_LOCAL_INFER_MODEL_PATH` names a path that does not exist or is not a valid model file
- WHEN the llama.cpp engine is asked to generate for any request
- THEN it returns `Err(EngineError::Rejected(reason))`, and the Worker-level execution reaches a `Failed` terminal phase with no panic and no hang

### Requirement: Cancellation Stops A Real Decode Loop Within One Token

Once model loading succeeds and generation begins, the llama.cpp engine MUST check the sink's verdict after every emitted token, exactly as the port's contract requires, and MUST stop generating no later than the token boundary immediately following a `SinkVerdict::Stop` — bounding cancellation latency to at most one further token, matching the reference engine's own contract and the adapter's abandonment-detection contract (`worker-local-infer-adapter/spec.md`).

#### Scenario: A SinkVerdict::Stop halts real decoding within one token

- GIVEN the llama.cpp engine mid-decode, driven by a real model, with tokens remaining before `max_tokens`
- WHEN its sink returns `SinkVerdict::Stop` in response to a produced token
- THEN the engine produces no more than one further token before returning its summary

### Requirement: Real-Engine Tests Are Ignored By Default And Require Both The Feature And An Operator-Supplied Model

Any test that drives the llama.cpp engine through a real decode (loading an actual GGUF model) MUST be annotated `#[ignore]` so `cargo test --workspace` never runs it by default. Such a test MUST only be runnable with both `--features llamacpp` and an operator-supplied model path; the workspace MUST NOT download, cache, or commit a model file as part of any build or test step.

#### Scenario: cargo test --workspace never executes a real-model test

- GIVEN the full test suite including any llama.cpp real-decode tests
- WHEN `cargo test --workspace` is run without `--ignored`
- THEN no test that loads a real GGUF model executes

#### Scenario: A real-model test requires an explicit opt-in

- GIVEN a llama.cpp real-decode test
- WHEN it is run
- THEN it only executes when invoked with `--features llamacpp` and `--ignored`, and with an operator-supplied model path available

### Requirement: The Bindings Crate Owns Every unsafe Line; The Workspace-Wide Deny Never Relaxes

`llamacpp.rs` itself MUST contain no `unsafe` code and no `#[allow(unsafe_code)]`. All `unsafe` FFI work MUST live inside the external bindings crate the engine depends on, never inside this workspace. The root `Cargo.toml`'s `[workspace.lints.rust] unsafe_code = "deny"` MUST remain untouched by this change.

#### Scenario: The workspace contains zero unsafe code after this change

- GIVEN the full workspace source tree after this change lands
- WHEN it is scanned for the `unsafe` keyword and for `#[allow(unsafe_code)]`
- THEN neither occurs anywhere

#### Scenario: unsafe_code = "deny" is unchanged

- GIVEN the root `Cargo.toml`'s `[workspace.lints.rust]` table before and after this change
- WHEN it is diffed
- THEN `unsafe_code = "deny"` is present, unmodified, in both

### Requirement: The llama.cpp Name Stays Inside The Engine Module

No identifier naming this engine, or any of `llama`, `llama_cpp`, `ggml`, `candle`, MUST appear anywhere outside `runtime/src/worker/local_infer/engine/` — enforced by the `engine_names_stay_inside_the_engine_module` architecture-guard scan. Landing this change exposed a real gap in that scan (design.md D14): its prior identifier matcher matched whole identifiers only, so split forms like `llama_cpp_2` (the bindings crate's own name) or `#[cfg(feature = "llamacpp")]` would have slipped through undetected. The scan was hardened in PR1, ahead of any new engine code, specifically so this change's own identifiers are the first thing it correctly catches.

#### Scenario: The hardened containment scan catches split-identifier and cfg-attribute forms

- GIVEN a synthetic line such as `use llama_cpp_2::LlamaModel;` outside the engine subtree
- WHEN `engine_names_stay_inside_the_engine_module` scans it
- THEN it reports a violation, and a `#[cfg(feature = "llamacpp")]` attribute line is correctly exempted from being flagged as itself a violation

#### Scenario: The hardened containment scan still passes with llamacpp.rs added to the engine subtree

- GIVEN `crates/runtime-worker/src/` and `runtime/src/` excluding `runtime/src/worker/local_infer/engine/`
- WHEN `engine_names_stay_inside_the_engine_module` scans them after `llamacpp.rs` is added
- THEN it finds no occurrence of `llama`, `llama_cpp`, `ggml`, or `candle`
