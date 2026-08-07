# Backend Adapter Specification

## Purpose

The Backend Adapter is the engine-agnostic contract Capability Providers execute against, decoupling them from concrete inference engines. The contract is defined as a protocol/ABC expressing execution in terms independent of any specific engine (llama.cpp, TensorRT-LLM, vLLM, ONNX Runtime, Faster-Whisper). Concrete backend implementations live exclusively outside the `backends/` tree, in separate engine packages (e.g., `engines/`), maintaining the structural boundary.

## Requirements

### Requirement: Backend Adapter Contract Is Engine-Agnostic

The `backends/` package tree MUST express execution in terms independent of any specific engine (llama.cpp, TensorRT-LLM, vLLM, ONNX Runtime, Faster-Whisper), at any depth. Concrete engine SDK wiring MUST live exclusively outside `backends/` (e.g. in `engines/`); `backends/` itself MUST NOT import an engine SDK, directly or through a nested module.

(Previously: phrased as a Phase 1 prohibition on "any concrete backend implementation" — that phrasing became false once `engines/` introduced the first concrete adapter. Restated as a permanent structural boundary: the contract tree stays engine-agnostic no matter how many concrete adapters exist elsewhere.)

#### Scenario: Backend Adapter contract has no concrete backend implementation

- GIVEN the `src/tibios_ray/backends/` source, including any nested subpackage
- WHEN inspected for imports of llama.cpp, TensorRT-LLM, vLLM, ONNX Runtime, or Faster-Whisper SDKs
- THEN none are found — only the abstract contract type exists

#### Scenario: A Capability Provider executes only against the contract type

- GIVEN a Capability Provider implementation that performs inference
- WHEN it invokes execution
- THEN it calls only the Backend Adapter protocol/ABC, with no reference to a concrete engine

#### Scenario: The import guard inspects backends/ recursively, not just top-level

- GIVEN a hypothetical concrete adapter placed at `backends/engines/rogue.py`, nested under the contract tree
- WHEN the engine-SDK import guard test runs
- THEN it discovers and scans that nested file too (recursive traversal, not a top-level-only glob), failing the test if it imports a forbidden SDK

### Requirement: Capability Providers Depend on the Contract, Not the Engine

Capability Provider implementations MUST depend exclusively on the Backend Adapter contract type. They MUST NOT import or reference a specific engine's SDK or types directly.

#### Scenario: Dependency direction is Provider → Adapter, never reversed

- GIVEN the Phase 1 module dependency graph
- WHEN traced from any Capability Provider module
- THEN it depends only on the Backend Adapter contract module, and the Backend Adapter module has no dependency back on any Capability Provider

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
