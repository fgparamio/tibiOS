# vLLM Text Backend Specification

## Purpose

Defines `VllmTextBackend` — the second concrete Backend Adapter, executing `chat.generate` against vLLM's `AsyncLLM`. Lives in `engines/`, structurally satisfies `TextGenerationBackend`, never in `backends/`. Unlike `llamacpp-text-backend`'s one-model-per-session shape, this Backend owns a shared, refcounted **Model Runtime**: one engine instance per distinct model, reused across every session of that model.

## Requirements

### Requirement: Structural Conformance to TextGenerationBackend

`VllmTextBackend` MUST satisfy `TextGenerationBackend` structurally (Protocol conformance, no base class), verified by static type checking.

#### Scenario: pyright accepts VllmTextBackend as a TextGenerationBackend

- GIVEN `VllmTextBackend` and a variable typed `TextGenerationBackend`
- WHEN an instance is assigned to that variable
- THEN pyright reports no type error, and `VllmTextBackend` inherits from no base class

### Requirement: Model Runtime Shares One Engine Per Model

The Model Runtime MUST construct at most one engine instance per distinct model, lazily — on the first `acquire()` for that model, never eagerly. Every subsequent `acquire()` for the same model MUST reuse that same instance rather than constructing a new one.

#### Scenario: First acquire constructs the engine, second acquire reuses it

- GIVEN no session has yet been acquired for a given model
- WHEN `acquire(plan)` is awaited twice in sequence for that same model
- THEN exactly one `AsyncLLMLike` instance is constructed, and both returned `BackendSession`s reference that same instance

#### Scenario: Two distinct models get two distinct engine instances

- GIVEN two acquired sessions targeting different models
- WHEN their underlying engine instances are inspected
- THEN they are two distinct `AsyncLLMLike` instances, one per model

### Requirement: Single-Flight Construction Prevents Duplicate Engines

Concurrent first-`acquire()` calls for the same model MUST NOT race into constructing two engine instances. Construction MUST be serialized so exactly one caller builds the engine while the others await and reuse its result.

#### Scenario: Concurrent first acquires build exactly one engine

- GIVEN no engine yet exists for a model
- WHEN N `acquire()` calls for that model are awaited concurrently
- THEN exactly one `AsyncLLMLike` construction occurs, and all N sessions reference the same instance

### Requirement: Refcounted Teardown on Last Release

The Model Runtime MUST track a reference count per engine instance, incremented on `acquire()` and decremented on `release()`. Releasing a session MUST shut down and discard the engine only when its refcount reaches zero; releasing a non-last session MUST leave the engine running.

#### Scenario: Releasing the last session shuts the engine down

- GIVEN a model with exactly one acquired session
- WHEN that session is released
- THEN the engine's shutdown is invoked and the Model Runtime no longer holds an instance for that model

#### Scenario: Releasing a non-last session keeps the engine running

- GIVEN a model with two acquired sessions
- WHEN one session is released
- THEN the engine is not shut down, and the other session's `generate()` still succeeds

### Requirement: Native-Async Streaming, No Thread Bridge

`generate()` MUST consume the engine's `generate()` directly as an `AsyncGenerator`, with no background thread, queue, or polling loop bridging it to the event loop. Each yielded `TextChunk.finished` MUST be sourced from the underlying output's `finished` field, never inferred by lookahead.

#### Scenario: generate() streams via native async iteration

- GIVEN a stubbed `AsyncLLMLike.generate()` yielding multiple outputs
- WHEN `VllmTextBackend.generate()` is iterated
- THEN chunks are yielded in production order with no buffering, and no `Thread`, `asyncio.Queue`, or polling loop is present in the call path

#### Scenario: finished is sourced from the engine output, not inferred

- GIVEN a stubbed output stream whose last item sets `finished=True`
- WHEN `generate()` is fully consumed
- THEN exactly one yielded `TextChunk` has `finished=True`, corresponding to the output that set `finished=True`

### Requirement: Streaming Output Is Transport-Agnostic

`generate()` MUST yield only `TextChunk` values via `AsyncIterator[TextChunk]`. The engine MUST NOT construct, reference, or import any gRPC type anywhere in its implementation.

#### Scenario: generate() yields only TextChunk, no gRPC dependency

- GIVEN an acquired session and a `TextRequest`
- WHEN `generate()` is iterated
- THEN every yielded value is a `TextChunk`, and no gRPC type is imported anywhere in `engines/vllm.py`

### Requirement: Uniform Cancellation Hides Engine-Version Inconsistency

Abandoning or cancelling a `generate()` stream MUST issue an explicit engine-level abort call, in a `finally` block, on every exit path (exhaustion, `aclose()`, cancellation). vLLM v0/v1's differing engine-cancellation behavior on generator garbage collection MUST be treated as Known Engine Behavior absorbed inside this Backend — the Worker-visible cancellation contract MUST NOT vary by engine version.

#### Scenario: Abandoning a stream mid-flight issues an explicit abort

- GIVEN a `generate()` iteration in progress on a stubbed engine
- WHEN the consumer closes or cancels the iteration before exhaustion
- THEN the stub's abort method is called exactly once with that request's identifier

#### Scenario: Abort still fires when the engine version's GC behavior differs

- GIVEN a stub simulating an engine that does not auto-cancel on generator garbage collection
- WHEN the stream is abandoned without explicit closure
- THEN the explicit `finally`-block abort still runs, producing the same Worker-visible outcome as a stub that does auto-cancel

### Requirement: Injectable AsyncLLMLike Protocol for SDK-Free Unit Testing

`VllmTextBackend` MUST accept an injectable engine factory satisfying a local structural `AsyncLLMLike` Protocol, defaulting to the real `AsyncLLM` imported lazily inside the factory. Importing `engines/vllm.py` MUST NOT require `vllm`, `torch`, or CUDA to be present.

#### Scenario: Unit tests run without vllm, torch, or CUDA installed

- GIVEN `vllm` and `torch` are not installed in the test environment
- WHEN `engines/vllm.py` is imported and `VllmTextBackend` is constructed with a stub `AsyncLLMLike` factory
- THEN import and construction both succeed with no `ImportError`

#### Scenario: The default factory imports the SDK only when invoked

- GIVEN no factory override is supplied
- WHEN the module is imported without acquiring any session
- THEN `vllm` is not imported; the import occurs only inside the factory function, at first-acquire time

### Requirement: vllm Is an Optional Extra

`vllm` MUST be declared as an optional dependency extra (`[project.optional-dependencies] vllm`), not a core dependency. The unit test tier MUST pass with the extra absent.

#### Scenario: Core install excludes vllm

- GIVEN a base install of `tibios-ray` without the `vllm` extra
- WHEN dependencies are resolved
- THEN `vllm` (and its torch/CUDA transitive weight) is absent and the unit test suite still passes
