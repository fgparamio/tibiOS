# Delta for Worker Local Infer Adapter

> `local-infer-llamacpp-engine` adds a second, real implementor of `TextGenerationEngine`. `engine/mod.rs`'s `default_engine()` becomes build-conditional: with the `llamacpp` feature enabled and a real engine constructible, it returns that engine; otherwise (feature disabled — the default) it returns `DeterministicEngine`, exactly as before. `default_engine()`'s signature (`fn default_engine() -> std::sync::Arc<dyn TextGenerationEngine>`) and its status as `local_infer/engine/`'s sole exit point are unchanged. `DeterministicEngine` is not deleted and is not modified; it remains the reference implementation the conformance harness and the executor-liveness tests depend on. No other requirement in this capability changes: registration timing, the `spawn_blocking` boundary, panic propagation, cancellation/deadline polling order, the factory-only exposure of `LocalInferWorker`, and O1-O4 conformance are all untouched by this change.

## MODIFIED Requirements

### Requirement: A Deterministic Reference Engine Proves The Port, Never Real Inference

`local_infer/engine/` MUST include exactly one reference implementation of the engine port (`DeterministicEngine`) that is deterministic — given the same request, it MUST produce the same sequence of output tokens on every run, with no dependency on wall-clock time, randomness, or environment state for its output content — and MUST perform no real inference: it MUST NOT load a model, perform a GPU or FFI call, or depend on `llama.cpp`, `llama_cpp`, `ggml`, or `candle`. It MUST NOT call `std::thread::sleep` or any equivalent wait; the CPU cost it stands in for MUST come from bounded, genuine computation (a spin loop), whose iteration count per token MUST be supplied by the caller rather than hardcoded. No engine-specific name (this reference engine's own name, or a real backend's) MUST appear anywhere outside `local_infer/engine/` — including inside `local_infer/mod.rs` itself, which MUST obtain an engine only through a factory returning a type-erased handle (`impl TextGenerationEngine` or `Arc<dyn TextGenerationEngine>`), never by naming a concrete engine type. That factory, `default_engine()`, MUST select between engines by build configuration: with the `llamacpp` feature enabled and a real engine constructible, it MUST return that real engine; with the feature disabled — the default — it MUST unconditionally return `DeterministicEngine`. In both cases `default_engine()`'s signature and its status as `local_infer/engine/`'s sole exit point for obtaining an engine are unchanged.
(Previously: `default_engine()` unconditionally returned `DeterministicEngine`; no build-time or runtime engine selection existed, because `DeterministicEngine` was the only implementor of `TextGenerationEngine` in the workspace.)

#### Scenario: The reference engine produces an identical output sequence across repeated runs

- GIVEN the reference engine constructed with the same request in two separate runs
- WHEN each run is driven to completion through the engine port
- THEN the sequence of output tokens produced is identical between the two runs

#### Scenario: The reference engine performs no real inference and never sleeps

- GIVEN the reference engine's implementation
- WHEN its source is inspected
- THEN it names neither `llama.cpp` nor `candle`, loads no model file, performs no GPU or FFI call, and calls no sleep or wait function

#### Scenario: The per-token spin cost is caller-configured, not hardcoded

- GIVEN two otherwise-identical requests differing only in a caller-supplied spin-iteration count
- WHEN each is driven to completion
- THEN the produced token content is unaffected by the spin count, while the count itself governs how much CPU work each token costs

#### Scenario: No engine-specific name appears outside the engine module, including in local_infer/mod.rs

- GIVEN the source tree under `runtime/src/worker/local_infer/` outside `local_infer/engine/`, and the rest of the workspace
- WHEN it is scanned for engine-specific names (any concrete engine's own name, `llama`, `llama_cpp`, `ggml`, `candle`)
- THEN none appears — `local_infer/mod.rs` obtains an engine only through a factory returning a type-erased handle

#### Scenario: With the llamacpp feature disabled, default_engine() returns DeterministicEngine unconditionally

- GIVEN `runtime` built without the `llamacpp` feature (the default)
- WHEN `default_engine()` is called
- THEN it returns `DeterministicEngine`, exactly as it did before this change

#### Scenario: With the llamacpp feature enabled and the engine constructible, default_engine() returns the llama.cpp engine

- GIVEN `runtime` built with the `llamacpp` feature enabled, in a configuration where the llama.cpp engine can be constructed
- WHEN `default_engine()` is called
- THEN it returns the llama.cpp-backed engine, type-erased behind the same `Arc<dyn TextGenerationEngine>` return type, and `default_engine()` remains `local_infer/engine/`'s sole exit point for obtaining an engine
