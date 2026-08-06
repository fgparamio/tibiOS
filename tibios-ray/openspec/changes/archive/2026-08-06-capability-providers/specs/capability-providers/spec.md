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

### Requirement: Uniform No-Backend Execution Failure

Every Provider's `execute()` MUST raise `NoBackendAvailableError` unconditionally — no Provider holds a backend reference, so none can ever return a COMPLETED `ExecutionReport` or fabricate success.

#### Scenario: Direct execute() call raises NoBackendAvailableError

- GIVEN any of the seven Providers and a valid `ExecutionContext`
- WHEN `execute()` is awaited directly
- THEN `NoBackendAvailableError` is raised and no `ExecutionReport` is returned

#### Scenario: WorkerRuntime dispatch surfaces a Failed report, not a bare exception

- GIVEN a `WorkerRuntime` whose registry resolves to one of the seven Providers for the requested capability
- WHEN `WorkerRuntime.execute()` dispatches to that Provider
- THEN `WorkerRuntime` catches the raised `NoBackendAvailableError` and returns an `ExecutionReport` with `phase == FAILED` — no exception escapes the Worker Contract boundary

### Requirement: Binding Invariants Carried Forward From the Frozen Contracts

No Provider MUST hardcode a concrete model name outside its descriptor's catalog data, reference `local-infer`, encode a size/cost routing conditional, hold any backend reference, or invent a new backend protocol for vision, speech, or OCR. `src/tibios_ray/capabilities/` MUST NOT import from `src/tibios_ray/runtime/`.

#### Scenario: No hardcoded model, local-infer reference, or routing conditional exists

- GIVEN the seven Provider module source files
- WHEN searched for hardcoded model names, `local-infer` references, or size/cost conditionals
- THEN none are found

#### Scenario: Providers hold no backend reference and invent no new protocol

- GIVEN the seven Provider classes
- WHEN inspected for fields/attributes and imports
- THEN none holds a `BackendAdapter` (or other backend) reference, and no new backend protocol type is defined for vision, speech, or OCR

#### Scenario: capabilities/ imports nothing from runtime/

- GIVEN the `src/tibios_ray/capabilities/` module tree after this change
- WHEN its imports are traced
- THEN none resolve to `src/tibios_ray/runtime/`
