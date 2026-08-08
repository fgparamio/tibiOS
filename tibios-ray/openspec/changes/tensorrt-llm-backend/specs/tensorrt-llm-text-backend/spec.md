# TensorRT-LLM Text Backend Specification

## Purpose

Defines `TensorrtLlmTextBackend` — the third concrete Backend Adapter for `chat.generate`, executing against a **precompiled** TensorRT-LLM engine artifact. Lives in `engines/`, structurally satisfies `backends/text.py::TextGenerationBackend`, never in `backends/`. Follows `vllm-text-backend`'s residency shape: one shared, lazily-constructed, refcounted engine instance per model, natively-async streaming, no thread bridge. Engine compilation (`trtllm-build`) is categorically outside this Backend's — and the Runtime's — responsibility.

## Requirements

### Requirement: Structural Conformance to TextGenerationBackend

`TensorrtLlmTextBackend` MUST satisfy `TextGenerationBackend` structurally (Protocol conformance, no base class), verified by static type checking.

#### Scenario: pyright accepts TensorrtLlmTextBackend as a TextGenerationBackend

- GIVEN `TensorrtLlmTextBackend` and a variable typed `TextGenerationBackend`
- WHEN an instance is assigned to that variable
- THEN pyright reports no type error, and `TensorrtLlmTextBackend` inherits from no base class

### Requirement: Engine Compilation Is Never Invoked by the Runtime

The Runtime MUST consume only a precompiled TensorRT-LLM engine artifact, supplied by configuration as a filesystem path. No code path in `TensorrtLlmTextBackend` — construction, `acquire()`, or `generate()` — MUST invoke `trtllm-build`, the `LLM(model=hf_checkpoint)` JIT-build path, or any other compilation/conversion call. Engine compilation is an out-of-band operator/provisioning concern, never a Worker responsibility, regardless of how long a hypothetical compilation would take.

#### Scenario: No compilation call exists in the Backend's call path

- GIVEN the `engines/tensorrt.py` source and its full call graph
- WHEN inspected for a call to `trtllm-build`, an `LLM(model=...)` constructor supplied a non-engine checkpoint, or any other compilation/conversion entry point
- THEN none is found — the Backend only opens an existing engine artifact, and construction never blocks on a build step

### Requirement: Missing or Incompatible Engine Artifact Is a Configuration Error, Never Recovered Dynamically

A missing engine artifact path, a path that does not exist on disk, or an artifact incompatible with the running TensorRT-LLM SDK/GPU MUST surface as an explicit, attributable configuration/wiring failure at Backend construction time. It MUST NOT trigger an on-demand build, a silent fallback to another backend, a retry loop, or any other dynamic recovery behavior.

#### Scenario: Unset artifact path leaves the capability unwired, not crashed

- GIVEN `TIBIOS_RAY_TENSORRT_ENGINE_PATH` is unset
- WHEN `build_runtime()` runs
- THEN it returns a `WorkerRuntime` without raising, and `tensorrt_llm` is absent from `ChatProvider`'s injected mapping (per `worker-configuration`'s existing absent-configuration behavior)

#### Scenario: A configured but nonexistent or incompatible artifact fails construction explicitly

- GIVEN an engine artifact path that is configured but does not exist, or exists but is incompatible with the installed TensorRT-LLM SDK
- WHEN `TensorrtLlmTextBackend` is constructed
- THEN construction raises an explicit, attributable error before any session can be acquired — no build is attempted and no other backend is silently substituted

### Requirement: Shared Refcounted Model Runtime, Mirroring vllm-text-backend

The Model Runtime MUST construct at most one engine instance per distinct model, lazily on first `acquire()`, serialized against concurrent first-acquires (single-flight), and reused by every subsequent `acquire()` for that model. Releasing the last session for a model MUST shut the engine down; releasing a non-last session MUST leave it running.

#### Scenario: First acquire constructs the engine, second acquire reuses it

- GIVEN no session has yet been acquired for a given model
- WHEN `acquire(plan)` is awaited twice in sequence for that model
- THEN exactly one engine instance is constructed, and both sessions reference it

#### Scenario: Releasing the last session shuts the engine down

- GIVEN a model with exactly one acquired session
- WHEN that session is released
- THEN the engine's shutdown is invoked and the Model Runtime no longer holds an instance for that model

### Requirement: Native-Async Streaming, No Thread Bridge

`generate()` MUST consume the engine's async generator directly, with no background thread, queue, or polling loop. `TextChunk.finished` MUST be sourced from the underlying output's terminal field, never inferred by lookahead. `generate()` MUST yield only `TextChunk` values; no gRPC type MUST be imported anywhere in `engines/tensorrt.py`.

#### Scenario: generate() streams via native async iteration with no gRPC dependency

- GIVEN a stubbed engine yielding multiple outputs
- WHEN `TensorrtLlmTextBackend.generate()` is iterated
- THEN chunks are yielded in production order, only `TextChunk` values are produced, and no `Thread`, `asyncio.Queue`, polling loop, or gRPC import exists in the call path

### Requirement: Uniform Cancellation on Every Exit Path

Abandoning or cancelling a `generate()` stream MUST issue an explicit engine-level abort call in a `finally` block, on exhaustion, `aclose()`, and cancellation alike, so the Worker-visible cancellation contract does not vary by SDK version.

#### Scenario: Abandoning a stream mid-flight issues an explicit abort

- GIVEN a `generate()` iteration in progress on a stubbed engine
- WHEN the consumer closes or cancels the iteration before exhaustion
- THEN the stub's abort method is called exactly once with that request's identifier

### Requirement: Injectable SDK Protocol for SDK-Free Unit Testing

`TensorrtLlmTextBackend` MUST accept an injectable engine factory satisfying a local structural Protocol, defaulting to the real SDK class imported lazily inside the factory via `importlib`. Importing `engines/tensorrt.py` MUST NOT require `tensorrt_llm` or CUDA to be present.

#### Scenario: Unit tests run without tensorrt_llm or CUDA installed

- GIVEN `tensorrt_llm` is not installed in the test environment
- WHEN `engines/tensorrt.py` is imported and `TensorrtLlmTextBackend` is constructed with a stub factory
- THEN import and construction both succeed with no `ImportError`

#### Scenario: The default factory imports the SDK only when invoked

- GIVEN no factory override is supplied
- WHEN the module is imported without acquiring any session
- THEN `tensorrt_llm` is not imported; the import occurs only inside the factory function, at first-acquire time

### Requirement: tensorrt_llm Is an Optional Extra

`tensorrt_llm` MUST be declared as an optional dependency extra (`[project.optional-dependencies]`), not a core dependency. The unit test tier MUST pass with the extra absent.

#### Scenario: Core install excludes tensorrt_llm

- GIVEN a base install of `tibios-ray` without the `tensorrt_llm` extra
- WHEN dependencies are resolved
- THEN `tensorrt_llm` is absent and the unit test suite still passes

### Requirement: supports() Is a Backend-Family Check Only, Never Model Selection

`supports(plan)` MUST check only `plan.backend == BackendId("tensorrt_llm")`. It MUST NOT branch on model identity, model family, or any model-specific logic; that responsibility belongs exclusively to `ModelSelectionPolicy`, upstream of the Engine.

#### Scenario: supports() checks backend family only

- GIVEN a `ServingPlanLike` with `backend == BackendId("tensorrt_llm")`
- WHEN `supports(plan)` is called, regardless of which model the plan targets
- THEN it returns `True` with no model-name comparison performed

### Requirement: Zero-Diff Integration — No Backend-Specific Branching Outside the Composition Root

`ChatProvider.execute()` and `PreferenceOrderPolicy` (the `ModelSelectionPolicy` implementation) MUST require no code change to support `tensorrt_llm`. Neither module MUST contain any conditional referencing `tensorrt_llm`, `TensorrtLlmTextBackend`, or any other TensorRT-LLM-specific identifier; both MUST remain generic over `BackendId`. Only `worker.py::build_runtime()` and its `_BACKEND_PREFERENCE` tuple MUST reference the concrete class or the `tensorrt_llm` identifier as a data value.

#### Scenario: capabilities/chat.py has zero diff for this change

- GIVEN `capabilities/chat.py` before and after this change
- WHEN diffed
- THEN no lines differ

#### Scenario: No backend-specific branching exists in ChatProvider or PreferenceOrderPolicy

- GIVEN `capabilities/chat.py` and `selection/preference.py` source
- WHEN inspected for a conditional referencing `tensorrt_llm` or `TensorrtLlmTextBackend` by name
- THEN none is found — `tensorrt_llm` appears only as an opaque `BackendId` value in configuration/composition code
