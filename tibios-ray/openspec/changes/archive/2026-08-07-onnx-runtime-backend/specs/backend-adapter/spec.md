# Delta for Backend Adapter

## MODIFIED Requirements

### Requirement: BackendSession Carries No Model Residency

**Backend Independence Principle**: a Backend defines what operations are available, never how model residency is implemented, and never which specific execution method its modality exposes. Model residency may be session-owned, shared, pooled, or remote, provided the Backend Contract — `supports`/`acquire`/*a per-modality execution method*/`release` — stays unchanged. `llamacpp-text-backend` and `vllm-text-backend` (both exposing `generate`) were the first two proofs of this principle; `onnxruntime-backend` (exposing `embed`/`rerank` instead of `generate`) is the third, proving the execution method itself — not only its residency shape — is not part of the invariant.

A `BackendSession` MUST be an opaque execution-context handle only — identity (`backend_id`, `session_id`) and nothing else. It MUST NOT carry model residency (loaded weights, engine handles, or any Backend-internal state). Model residency MUST remain each Backend's private implementation detail, held outside `BackendSession`.

(Previously: named the execution method explicitly as `generate` in the Backend Contract tuple. That phrasing was accurate while every adapter served `chat.generate`; the first non-text adapter, `onnxruntime-backend` with `embed`/`rerank`, makes it false. Restated so the Contract names *a* per-modality execution method, not `generate` specifically.)

#### Scenario: BackendSession's fields are exactly identity, no residency

- GIVEN the `BackendSession` dataclass definition
- WHEN its fields are inspected
- THEN they are exactly `backend_id` and `session_id` — no model handle, engine reference, or weights field is present

#### Scenario: Two structurally opposite residency shapes both satisfy the invariant

- GIVEN `llamacpp-text-backend`'s per-session `_Residency` side table (one dedicated model instance per session) and `vllm-text-backend`'s shared, refcounted Model Runtime (one engine instance reused across sessions of the same model)
- WHEN both Backends' `acquire()` return values are inspected
- THEN both return a `BackendSession` carrying only `backend_id`/`session_id`, with residency held entirely outside it — proving the invariant permits opposite residency shapes without contradiction

#### Scenario: A non-text execution method still satisfies the Backend Contract

- GIVEN `onnxruntime-backend`, whose Backend Contract execution method is `embed` (via `EmbeddingBackend`) and/or `rerank` (via `RerankBackend`) rather than `generate`
- WHEN its `acquire()` return value is inspected
- THEN it returns a `BackendSession` carrying only `backend_id`/`session_id`, identical in shape to `llamacpp-text-backend` and `vllm-text-backend` — proving the Backend Contract's residency/identity surface is independent of which execution method a modality exposes
