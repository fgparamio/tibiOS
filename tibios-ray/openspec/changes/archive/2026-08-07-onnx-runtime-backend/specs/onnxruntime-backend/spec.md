# ONNX Runtime Backend Specification

## Purpose

Defines the ONNX Runtime Backend(s) — the first non-text-generation Backend Adapter, executing `embedding.embed` and `rerank.rerank` against ONNX Runtime's `InferenceSession`. Lives in `engines/`, structurally satisfies `EmbeddingBackend` and `RerankBackend`, never in `backends/`. Whether one class or two provides both protocols, and how residency is held between `acquire()` and `release()`, are implementation decisions this spec does not prescribe.

## Requirements

### Requirement: Structural Conformance to EmbeddingBackend and RerankBackend

The ONNX Runtime backend(s) MUST satisfy `EmbeddingBackend` and `RerankBackend` structurally (Protocol conformance, no base class), verified by static type checking — regardless of whether one concrete type or two provides both protocols.

#### Scenario: pyright accepts the backend type(s) as EmbeddingBackend and RerankBackend

- GIVEN the concrete ONNX Runtime backend type(s) and variables typed `EmbeddingBackend` and `RerankBackend`
- WHEN an instance is assigned to each variable
- THEN pyright reports no type error for either assignment, and no concrete type inherits from a base class

### Requirement: An Engine Never Performs Model Selection

`supports(plan)` MUST check only `plan.backend == BackendId("onnxruntime")` — a backend-family check. It MUST NOT branch on model identity, model family, or any model-specific logic.

#### Scenario: supports() checks backend family only

- GIVEN a `ServingPlanLike` with `backend == BackendId("onnxruntime")`
- WHEN `supports(plan)` is called, regardless of which model the plan targets
- THEN it returns `True` for every such plan, with no model-name comparison performed

### Requirement: Residency Lifecycle Governs Model Access Through Acquire and Release

`acquire(plan)` MUST return a `BackendSession` valid for invoking `embed()` and/or `rerank()` against the model `plan` targets. `release(session)` MUST render that session no longer usable for execution. Neither operation MUST corrupt the residency state of any other concurrently acquired session, whether for the same model or a different one. The residency mechanism itself (shared, per-acquire, pooled, or otherwise) is an implementation detail this requirement does not prescribe.

#### Scenario: acquire returns a usable session, release ends it

- GIVEN a valid plan with `backend == BackendId("onnxruntime")`
- WHEN `acquire(plan)` is awaited, an execution method succeeds on the returned session, then `release(session)` is awaited
- THEN acquire succeeds before release, and any execution attempted on that session after release fails or is refused

#### Scenario: Concurrent acquires for the same model all succeed

- GIVEN no session yet acquired for a given model
- WHEN N `acquire(plan)` calls for that same model are awaited concurrently
- THEN all N calls return a usable `BackendSession`, and each session's subsequent execution call succeeds independently

#### Scenario: Concurrent acquire/release across different models are independent

- GIVEN two distinct models
- WHEN `acquire` is awaited for model A concurrently with `acquire` then `release` for model B
- THEN model A's `acquire` is unaffected by model B's `acquire`/`release` — neither errors nor blocks on the other

### Requirement: The Synchronous ORT Call Never Blocks the Event Loop

Every call into the underlying `InferenceSessionLike.run()`, invoked from `embed()` and `rerank()`, MUST be offloaded such that a concurrent, unrelated coroutine keeps making progress while it executes. The event loop MUST NOT be blocked for the duration of the synchronous call.

#### Scenario: Event loop stays responsive during a slow inference call

- GIVEN a stubbed `InferenceSessionLike` whose `run()` blocks synchronously for a measurable duration
- WHEN `embed()` (or `rerank()`) is awaited concurrently with another coroutine
- THEN the other coroutine keeps progressing while the inference call is in flight, proving the loop is never blocked

### Requirement: embed() Returns One Order-Preserving Vector Per Input

`embed(session, inputs)` MUST return exactly one `Vector` per element of `inputs`, in the same order, with all vectors of equal length. It MUST NOT stream.

#### Scenario: embed returns vectors in input order, one-to-one

- GIVEN a session and a sequence of N distinct text inputs
- WHEN `embed(session, inputs)` is awaited
- THEN exactly N `Vector`s are returned, the i-th `Vector` corresponds to the i-th input, and all `Vector`s share the same length

#### Scenario: Empty input sequence returns an empty result

- GIVEN a session and an empty `inputs` sequence
- WHEN `embed(session, [])` is awaited
- THEN an empty sequence of `Vector`s is returned, with no error

### Requirement: rerank() Returns One Scored Result Per Document With a Valid Back-Reference

`rerank(session, query, documents)` MUST return exactly one `RerankResult` per element of `documents`. Each result's `index` MUST equal the position of the document it scores within the original `documents` sequence, and every index in `documents`'s range MUST appear exactly once across the results.

#### Scenario: rerank returns one result per document with correct back-reference

- GIVEN a session, a query, and a sequence of N documents
- WHEN `rerank(session, query, documents)` is awaited
- THEN exactly N `RerankResult`s are returned, and their `index` values are a permutation of `0..N-1`, each referring back to the document it scored

#### Scenario: A result's index resolves to its scored document regardless of return order

- GIVEN results reordered by score rather than by input position
- WHEN each result's `index` is used to look up `documents[result.index]`
- THEN it resolves to the exact document that was scored, regardless of the result's position in the returned sequence

### Requirement: Injectable InferenceSessionLike and Tokenizer Seams Enable SDK-Free Unit Testing

The backend(s) MUST accept an injectable session factory satisfying a local structural `InferenceSessionLike` Protocol, and an injectable tokenizer seam, both defaulting to lazily-imported real implementations. Importing `engines/onnxrt.py` MUST NOT require `onnxruntime` or `numpy` to be installed.

#### Scenario: Unit tests run without onnxruntime or numpy installed

- GIVEN `onnxruntime` and `numpy` are not installed in the test environment
- WHEN `engines/onnxrt.py` is imported and the backend is constructed with stub `InferenceSessionLike` and tokenizer factories
- THEN import and construction both succeed with no `ImportError`

#### Scenario: The default factories import the SDK only when invoked

- GIVEN no factory override is supplied
- WHEN the module is imported without acquiring any session
- THEN `onnxruntime` is not imported; the import occurs only inside the factory function, at first-acquire time

### Requirement: onnx Is an Optional Extra

`onnxruntime` MUST be declared as an optional dependency extra (`[project.optional-dependencies] onnx`), not a core dependency. The unit test tier MUST pass with the extra absent.

#### Scenario: Core install excludes onnxruntime

- GIVEN a base install of `tibios-ray` without the `onnx` extra
- WHEN dependencies are resolved
- THEN `onnxruntime` is absent and the unit test suite still passes

### Requirement: EmbeddingProvider and RerankProvider Composition Stays Out of Scope

This change MUST NOT modify `src/tibios_ray/capabilities/embedding.py` or `rerank.py` to wire in this backend. `EmbeddingProvider` and `RerankProvider` MUST remain unchanged, their `execute()` still unconditionally raising `NoBackendAvailableError`.

#### Scenario: Providers are unchanged and still raise

- GIVEN `EmbeddingProvider` and `RerankProvider` after this change
- WHEN their `execute()` methods are awaited
- THEN both still raise `NoBackendAvailableError`, and neither capabilities module references the ONNX Runtime backend
