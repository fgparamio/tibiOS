# Delta for Backend Adapter

## ADDED Requirements

### Requirement: BackendSession Carries No Model Residency

**Backend Independence Principle**: a Backend defines what operations are available, never how model residency is implemented. Model residency may be session-owned, shared, pooled, or remote, provided the Backend Contract (`supports`/`acquire`/`generate`/`release`) stays unchanged. `llamacpp-text-backend` (session-owned) and `vllm-text-backend` (shared) are the first two proofs of this principle, not exceptions to it.

A `BackendSession` MUST be an opaque execution-context handle only — identity (`backend_id`, `session_id`) and nothing else. It MUST NOT carry model residency (loaded weights, engine handles, or any Backend-internal state). Model residency MUST remain each Backend's private implementation detail, held outside `BackendSession`.

#### Scenario: BackendSession's fields are exactly identity, no residency

- GIVEN the `BackendSession` dataclass definition
- WHEN its fields are inspected
- THEN they are exactly `backend_id` and `session_id` — no model handle, engine reference, or weights field is present

#### Scenario: Two structurally opposite residency shapes both satisfy the invariant

- GIVEN `llamacpp-text-backend`'s per-session `_Residency` side table (one dedicated model instance per session) and `vllm-text-backend`'s shared, refcounted Model Runtime (one engine instance reused across sessions of the same model)
- WHEN both Backends' `acquire()` return values are inspected
- THEN both return a `BackendSession` carrying only `backend_id`/`session_id`, with residency held entirely outside it — proving the invariant permits opposite residency shapes without contradiction
