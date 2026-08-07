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

### Requirement: Residency Is Backend-Owned, Not Request-Owned

A ready-to-use model residency MUST exist before any request is served.
Constructing a residency MUST belong to the Backend's own lifecycle
([ADR-0003](../../../docs/adr/0003-backend-resource-ownership.md)),
never to a request's `acquire()` call — `acquire(plan)` MUST return an
existing residency without constructing one, and MUST NOT block on model
construction. `release(session)` MUST return the residency to the Backend
for reuse, not discard it. When no residency is available, `acquire(plan)`
MUST wait up to a configured timeout for one to become free, then raise
`PoolExhaustedError` if none does within that timeout — the timeout bounds
the wait for an available residency, not the duration of any inference. The
number of residencies the Backend maintains MUST be operator-configurable,
not a fixed constant.

This requirement constrains observable behavior only. It does not name a
pool, a queue, or any other concurrency mechanism — those are implementation
choices documented in `design.md`, free to change without revisiting this
requirement.

#### Scenario: No model is constructed while serving a request

- GIVEN a Backend that has already finished constructing its residencies
- WHEN `acquire(plan)` is awaited for any request
- THEN no model-construction call happens during that `acquire(plan)` — the
  underlying model already existed

#### Scenario: Construction happens exactly once per residency, at Backend construction time

- GIVEN a Backend configured for `N` residencies
- WHEN the Backend is constructed, followed by `M > N` sequential
  `acquire()`/`release()` cycles
- THEN the model-construction call is made exactly `N` times, all during
  Backend construction, and never again regardless of `M`

#### Scenario: release returns the residency for reuse, not destruction

- GIVEN an acquired residency
- WHEN `release(session)` is awaited
- THEN the underlying model instance remains usable and becomes available
  to a subsequent `acquire(plan)` — it is not torn down

#### Scenario: Exhaustion waits, then fails explicitly — no other behavior is invented

- GIVEN every residency is currently acquired and none is released before
  the configured timeout elapses
- WHEN another `acquire(plan)` is awaited
- THEN it waits up to the configured timeout and then raises
  `PoolExhaustedError`; `release(session)` is never called for that
  attempt, since no residency was ever handed out

#### Scenario: Residency count is operator-configured, not hardcoded

- GIVEN two Backends of the same kind configured with different residency
  counts
- WHEN each is constructed
- THEN each constructs exactly its own configured number of residencies —
  the count is read from configuration, not a constant in the Backend's
  source

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

