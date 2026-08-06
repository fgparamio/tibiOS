# Backend Adapter Specification

## Purpose

The Backend Adapter is the engine-agnostic contract Capability Providers execute against, decoupling them from concrete inference engines. Phase 1 defines the contract only — no real backend wiring for llama.cpp, TensorRT-LLM, vLLM, ONNX Runtime, or Faster-Whisper.

## Requirements

### Requirement: Backend Adapter Contract Is Engine-Agnostic

The Backend Adapter MUST be defined as a protocol/ABC expressing execution in terms independent of any specific engine (llama.cpp, TensorRT-LLM, vLLM, ONNX Runtime, Faster-Whisper). Phase 1 MUST NOT include any concrete backend implementation or engine SDK wiring.

#### Scenario: Backend Adapter contract has no concrete backend implementation

- GIVEN the Phase 1 `src/tibios_ray/backends/` source
- WHEN inspected for imports of llama.cpp, TensorRT-LLM, vLLM, ONNX Runtime, or Faster-Whisper SDKs
- THEN none are found — only the abstract contract type exists

#### Scenario: A Capability Provider executes only against the contract type

- GIVEN a Capability Provider implementation that performs inference
- WHEN it invokes execution
- THEN it calls only the Backend Adapter protocol/ABC, with no reference to a concrete engine

### Requirement: Capability Providers Depend on the Contract, Not the Engine

Capability Provider implementations MUST depend exclusively on the Backend Adapter contract type. They MUST NOT import or reference a specific engine's SDK or types directly.

#### Scenario: Dependency direction is Provider → Adapter, never reversed

- GIVEN the Phase 1 module dependency graph
- WHEN traced from any Capability Provider module
- THEN it depends only on the Backend Adapter contract module, and the Backend Adapter module has no dependency back on any Capability Provider
