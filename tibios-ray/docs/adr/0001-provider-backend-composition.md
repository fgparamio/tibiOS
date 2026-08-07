# 1. Provider-Backend Composition

## Status

Accepted

## Context

Every Capability Provider (`ChatProvider`, `EmbeddingProvider`,
`RerankProvider`, `VisionProvider`, `SpeechTranscriptionProvider`,
`SpeechSynthesisProvider`) is currently a zero-field frozen dataclass whose
`execute()` unconditionally raises `NoBackendAvailableError`. No Provider
holds a reference to any Backend, and nothing in the codebase constructs
that link.

Backends (`OnnxEmbeddingBackend`, `OnnxRerankBackend`, `VllmTextBackend`,
the llama.cpp backend, and future TensorRT-LLM) are stateful objects:
loaded model weights, tokenizer, KV cache, CUDA context/engine/streams,
scheduler state, or thread pools, and already hold a `_sessions` map
populated via `acquire()`/`release()`. Constructing one per request would
discard all of that reused state and destroy performance.

## Decision

- Backends are constructed exactly once, during process startup, and live
  for the lifetime of the process.
- Providers receive their Backend dependency via constructor injection, as
  a plain field typed against a capability-scoped `Protocol`
  (e.g. `ChatBackend`, `EmbeddingBackend`, `RerankBackend`) — the same
  structural-typing style already used for `InferenceSessionLike` and
  `TokenizerLike` in `engines/onnxrt.py`. No `Arc`/reference-counting
  wrapper — Python doesn't need one.
- Providers never construct, look up, or select a Backend. They only
  execute against the one they were given.
- A Composition Root — a single module, run at startup — is the only place
  in the codebase that references concrete Backend implementations
  (`OnnxEmbeddingBackend`, `VllmTextBackend`, etc.) and wires each into its
  matching Provider.
- No `BackendRegistry` indirection between Provider and Backend. Backend
  *selection* (which concrete implementation a Provider gets) is a
  Composition Root / configuration concern, resolved once at startup — not
  a runtime lookup the Provider performs.

## Consequences

- Backend state (sessions, caches, engine handles) is created once and
  reused across requests.
- Providers become trivially testable: inject a fake `Protocol`
  implementation, no framework or container needed.
- Swapping a Backend implementation (e.g. ONNX Runtime → TensorRT-LLM for
  the same capability) is a one-line change in the Composition Root; no
  Provider code changes.
- The set of concrete Backend classes in use is visible in exactly one
  place, instead of being discoverable only by grepping the codebase.
- Backend selection is fixed at startup: switching backends at runtime
  (e.g. per-request routing between two Chat backends) is out of scope for
  this decision and would need its own ADR if it becomes a requirement.
