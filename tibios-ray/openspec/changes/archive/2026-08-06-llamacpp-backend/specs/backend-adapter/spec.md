# Delta for Backend Adapter

## MODIFIED Requirements

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
