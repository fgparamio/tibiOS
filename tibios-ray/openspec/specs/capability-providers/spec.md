# Capability Providers Specification

## Purpose

The Capability Providers are the concrete implementations of the frozen `CapabilityProvider` contract (`capability-registry` spec) for the MVP capability map: chat, embedding, rerank, vision, speech (transcribe + synthesize), and OCR. This spec fixes each Provider's advertised catalog data, the uniform no-backend failure behavior of `execute()`, joint registration, and the binding invariants carried forward from `worker-runtime`, `capability-registry`, and `backend-adapter`.

## Requirements

### Requirement: Descriptor Catalog Correctness and Stability

Each of the seven Capability Providers MUST expose a `CapabilityDescriptor` whose `capability`, `families`, and `backends` match the following table exactly, asserted stable by an automated test:

| Provider | Capability | Families | Backends |
|---|---|---|---|
| Chat | `chat.generate` | qwen, llama, deepseek, gemma, mistral, kimi | llama_cpp, tensorrt_llm, vllm |
| Embedding | `embedding.generate` | bge, nomic, e5, jina | onnxruntime |
| Rerank | `rerank.documents` | bge_reranker, jina_reranker | onnxruntime |
| Vision | `vision.understand` | qwen_vl, gemma_vision, llama_vision | vllm, tensorrt_llm |
| Speech (transcribe) | `speech.transcribe` | whisper | faster_whisper |
| Speech (synthesize) | `speech.synthesize` | kokoro | onnxruntime |
| OCR | `ocr.extract` | paddleocr | onnxruntime |

#### Scenario: A Provider's descriptor matches its table entry and stays stable

- GIVEN one of the seven Capability Providers
- WHEN its `descriptor` property is read across repeated test runs
- THEN `capability`, `families`, and `backends` equal exactly the row above for that Provider, unchanged run to run

#### Scenario: Chat advertises realistic flags; Embedding/Rerank advertise none

- GIVEN the Chat Provider's descriptor
- WHEN its `flags` are read
- THEN `streaming`, `tools`, `json`, and `reasoning` are all `True`
- AND for Embedding and Rerank, all flags are `False`

### Requirement: Joint Registration Without Rejection

All seven Providers MUST register together in one `CapabilityRegistry` without triggering `DuplicateCapabilityError` or `EmptyCatalogError`, and `catalog()` MUST return the union of their seven descriptors.

#### Scenario: All seven Providers register successfully

- GIVEN the seven Provider instances (Chat, Embedding, Rerank, Vision, Speech-transcribe, Speech-synthesize, OCR)
- WHEN they are passed together to `CapabilityRegistry.__init__`
- THEN construction succeeds and raises neither `DuplicateCapabilityError` nor `EmptyCatalogError`

#### Scenario: Catalog returns the union of all seven descriptors

- GIVEN the registry built from all seven Providers
- WHEN `catalog()` is called
- THEN the returned `CapabilityCatalog.descriptors` contains exactly the seven Providers' descriptors, one per capability

### Requirement: No-Backend Execution Failure Is Wiring-Scoped

Chat, Embedding, and Rerank Providers (*wired*) dispatch to an injected
Backend via the [ADR-0002](../../../docs/adr/0002-provider-backend-selection-delegation.md)
flow instead of raising unconditionally; they fail only when their
injected backend mapping is empty or the resolved plan names a
`BackendId` absent from it (dispatch mechanics fixed by the
`provider-backend-composition` spec). Vision, Speech (transcribe and
synthesize), and OCR Providers (*unwired*) keep raising
`NoBackendAvailableError` unconditionally, exactly as before.
(Previously: "Uniform No-Backend Execution Failure" — every Provider's
`execute()` raised `NoBackendAvailableError` unconditionally, with no
wired/unwired distinction.)

#### Scenario: Unwired Provider direct execute() call raises NoBackendAvailableError

- GIVEN one of the four unwired Providers (Vision, Speech-transcribe, Speech-synthesize, OCR) and a valid `ExecutionContext`
- WHEN `execute()` is awaited directly
- THEN `NoBackendAvailableError` is raised and no `ExecutionReport` is returned

#### Scenario: Unwired Provider dispatch surfaces a Failed report, not a bare exception

- GIVEN a `WorkerRuntime` whose registry resolves to one of the four unwired Providers
- WHEN `WorkerRuntime.execute()` dispatches to that Provider
- THEN `WorkerRuntime` catches the raised `NoBackendAvailableError` and returns an `ExecutionReport` with `phase == FAILED` — no exception escapes the Worker Contract boundary

#### Scenario: Wired Provider dispatches instead of raising when its mapping and policy resolve a backend

- GIVEN Chat, Embedding, or Rerank Provider constructed with a non-empty backend mapping and a policy that resolves a valid plan
- WHEN `execute()` is awaited
- THEN `NoBackendAvailableError` is not raised — the Provider dispatches per the `provider-backend-composition` spec

#### Scenario: Wired Provider fails when its injected mapping is empty

- GIVEN Chat, Embedding, or Rerank Provider constructed with an empty backend mapping
- WHEN `execute()` is awaited
- THEN execution fails — no backend is available to dispatch to

#### Scenario: Wired Provider fails when the resolved plan names a backend absent from its mapping

- GIVEN Chat, Embedding, or Rerank Provider whose injected mapping does not contain the `BackendId` named by `ModelSelectionPolicy.plan()`
- WHEN `execute()` is awaited
- THEN execution fails — it never falls back to a different entry in the mapping

### Requirement: Binding Invariants Carried Forward From the Frozen Contracts

No Provider MUST hardcode a concrete model name outside its descriptor's catalog data, reference `local-infer`, encode a size/cost routing conditional, or invent a new backend protocol for vision, speech, or OCR. No Provider MUST construct, discover, or mutate a backend — only the Composition Root may construct Backend instances and wire them into Providers. Wired Providers may hold immutable references to injected Backend mappings; unwired Providers hold none. The no-branching AST scan MUST be scoped to the four unwired modules. `src/tibios_ray/capabilities/` MUST NOT import from `src/tibios_ray/runtime/`.

#### Scenario: No hardcoded model, local-infer reference, or routing conditional exists

- GIVEN the seven Provider module source files
- WHEN searched for hardcoded model names, `local-infer` references, or size/cost conditionals
- THEN none are found

#### Scenario: Wired Providers hold injected immutable mappings; unwired Providers hold no backend reference

- GIVEN the seven Provider classes
- WHEN inspected for fields/attributes
- THEN Chat, Embedding, and Rerank hold two immutable fields (backend mapping and selection policy), and Vision/Speech/OCR hold no backend reference

#### Scenario: No Provider constructs, discovers, or mutates a backend

- GIVEN the seven Provider module source files
- WHEN inspected for backend construction (with `BackendId`, `BackendSession`, engine class names) and mutation of injected mappings
- THEN none are found — the injected mapping is immutable at construction and not modified thereafter

#### Scenario: No new backend protocol is invented for unwired capabilities

- GIVEN the unwired Provider modules (Vision, Speech-transcribe, Speech-synthesize, OCR)
- WHEN inspected for backend protocol types and their imports
- THEN no new backend protocol type is defined; these modules remain zero-field

#### Scenario: capabilities/ imports nothing from runtime/

- GIVEN the `src/tibios_ray/capabilities/` module tree after this change
- WHEN its imports are traced
- THEN none resolve to `src/tibios_ray/runtime/`
