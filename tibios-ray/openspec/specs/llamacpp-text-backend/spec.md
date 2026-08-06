# LlamaCpp Text Backend Specification

## Purpose

Defines `LlamaCppTextBackend` — the first concrete Backend Adapter, executing `chat.generate` against `llama-cpp-python`. Lives in `engines/`, structurally satisfies `TextGenerationBackend`, never in `backends/`.

## Requirements

### Requirement: Structural Conformance to TextGenerationBackend

`LlamaCppTextBackend` MUST satisfy `TextGenerationBackend` structurally (Protocol conformance, no base class), verified by static type checking.

#### Scenario: pyright accepts LlamaCppTextBackend as a TextGenerationBackend

- GIVEN `LlamaCppTextBackend` and a variable typed `TextGenerationBackend`
- WHEN an instance is assigned to that variable
- THEN pyright reports no type error, and `LlamaCppTextBackend` inherits from no base class

### Requirement: An Engine Never Performs Model Selection

The Engine's `supports(plan)` MUST check only `plan.backend == BackendId("llama_cpp")` — a backend-family check. It MUST NOT branch on model identity, model family, or any model-specific logic (e.g. no `if "deepseek" in model_name`). That responsibility belongs exclusively to Model Selection Policy, upstream of the Engine.

#### Scenario: supports() checks backend family only

- GIVEN a `ServingPlanLike` with `backend == BackendId("llama_cpp")`
- WHEN `supports(plan)` is called, regardless of which model the plan targets
- THEN it returns `True` for every such plan, with no model-name comparison performed

#### Scenario: A model-specific branch inside the engine fails the boundary check

- GIVEN the `engines/llamacpp.py` source
- WHEN inspected for conditionals referencing a model name, family, or `ResolvedModelRef` field
- THEN none are found — the engine holds no model-identity logic

### Requirement: Residency Lifecycle Constructs and Frees One Model Per Session

`acquire(plan)` MUST construct exactly one `Llama` instance and return one `BackendSession` wrapping it, with one `asyncio.Lock` created alongside it. `release(session)` MUST free that instance.

#### Scenario: acquire creates one Llama, one session, one lock

- GIVEN a valid plan with `backend == BackendId("llama_cpp")`
- WHEN `acquire(plan)` is awaited
- THEN exactly one `Llama` is constructed and one `BackendSession` is returned, holding a fresh, dedicated lock

#### Scenario: release frees the underlying model

- GIVEN an acquired session
- WHEN `release(session)` is awaited
- THEN the underlying `Llama` instance is discarded and the session is no longer usable for `generate()`

### Requirement: Streaming Output Is Transport-Agnostic

`generate()` MUST yield only `TextChunk` values via `AsyncIterator[TextChunk]`. The engine MUST NOT construct, reference, or import any gRPC type anywhere in its implementation.

#### Scenario: generate() yields only TextChunk instances, no gRPC dependency

- GIVEN an acquired session and a `TextRequest`
- WHEN `generate()` is iterated
- THEN every yielded value is a `TextChunk` (`text: str`, `finished: bool`), and no gRPC type is imported anywhere in `engines/llamacpp.py`

### Requirement: Non-Blocking Thread-Bridge Streaming

`generate()` MUST run the blocking `create_completion(stream=True)` sync generator on a background thread, feeding an `asyncio.Queue` consumed via `async for` on the event-loop side. Chunks MUST be delivered in production order, with exactly one terminal chunk carrying `finished=True`. Abandoning the stream MUST stop the underlying generator and free the thread/queue.

#### Scenario: Event loop stays responsive during generation

- GIVEN a stubbed `LlamaLike` whose `create_completion` blocks synchronously per token
- WHEN `generate()` is consumed concurrently with another coroutine
- THEN the other coroutine keeps progressing while tokens stream, proving the loop is never blocked

#### Scenario: Chunks arrive in order with exactly one finished=True terminal chunk

- GIVEN a stubbed multi-token completion
- WHEN `generate()` is fully consumed
- THEN chunks arrive in production order, more than one chunk is yielded (no buffering), and only the last chunk has `finished=True`

#### Scenario: Abandoning the stream mid-flight releases resources

- GIVEN a `generate()` iteration in progress
- WHEN the consumer calls `aclose()` or the task is cancelled before exhaustion
- THEN the background thread's generator stops and the session's lock is released

### Requirement: Per-Session Lock Serializes Only Calls Sharing That Session

Each `BackendSession` MUST hold its own `asyncio.Lock`, acquired for the whole `generate()` lifetime and released on exhaustion, `aclose()`, or cancellation. Two sessions of the same model backend MUST run `generate()` concurrently without blocking each other; two concurrent `generate()` calls on the *same* session MUST be serialized.

#### Scenario: Two sessions of the same model run concurrently

- GIVEN two independently acquired sessions for the same model
- WHEN `generate()` is called concurrently on each
- THEN both streams progress interleaved in wall-clock time, neither waiting on the other's lock

#### Scenario: Two calls on the same session are provably serialized

- GIVEN one acquired session
- WHEN `generate()` is called twice concurrently on that session
- THEN the second call's chunks do not begin until the first call's stream is fully exhausted or closed — no interleaving of the two chunk sequences

### Requirement: Injectable Llama Factory for SDK-Free Unit Testing

`LlamaCppTextBackend` MUST accept an injectable model factory satisfying a local structural `LlamaLike` Protocol, defaulting to the real `Llama` class imported lazily inside the factory. Importing `engines/llamacpp.py` MUST NOT require `llama_cpp` to be installed.

#### Scenario: Unit tests run without llama_cpp installed

- GIVEN `llama_cpp` is not installed in the test environment
- WHEN `engines/llamacpp.py` is imported and `LlamaCppTextBackend` is constructed with a stub `LlamaLike` factory
- THEN import and construction both succeed with no `ImportError`

#### Scenario: The default factory imports the SDK only when invoked

- GIVEN no factory override is supplied
- WHEN the module is imported without acquiring any session
- THEN `llama_cpp` is not imported; the import occurs only inside the factory function, at acquire time

### Requirement: llama-cpp-python Is an Optional Extra

`llama-cpp-python` MUST be declared as an optional dependency extra (`[project.optional-dependencies] llamacpp`), not a core dependency. The unit test tier MUST pass with the extra absent.

#### Scenario: Core install excludes llama-cpp-python

- GIVEN a base install of `tibios-ray` without the `llamacpp` extra
- WHEN dependencies are resolved
- THEN `llama-cpp-python` is absent and the unit test suite still passes

### Requirement: ChatProvider Composition Stays Out of Scope

This change MUST NOT modify `src/tibios_ray/capabilities/chat.py`. `ChatProvider` MUST remain a zero-field dataclass whose `execute()` unconditionally raises `NoBackendAvailableError`.

#### Scenario: ChatProvider is unchanged and still raises

- GIVEN `ChatProvider` after this change
- WHEN its fields are inspected and `execute()` is awaited
- THEN it has zero fields, `execute()` still raises `NoBackendAvailableError`, and `capabilities/chat.py` has no reference to `LlamaCppTextBackend`
