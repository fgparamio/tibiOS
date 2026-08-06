# 01 — Worker Runtime (tibios-ray)

## Status

Foundation (interfaces/skeletons only — see `openspec/changes/ray-worker-runtime/`). No inference engine, no Ray distribution logic, no gRPC wiring yet.

## Read this first

This document is a summary and orientation pointer for tibios-ray's own architecture track. It is **not** a replacement for tibios-core's architecture docs and does not restate them.

- **The Worker Contract itself** — Execution Context, Execution Channel, Execution Events, Execution Report, Execution Pulse, cancellation, the four execution patterns — is defined in `../tibios-core/docs/architecture/18-worker-model.md` (tag `architecture-v1.0`). That document is the single source of truth for what a Worker is and how it behaves as seen by tibios-core's Runtime. This doc cites it, never duplicates it.
- `../tibios-core/docs/architecture/25-ai-runtime.md` confirms tibios-ray gets no special treatment from the Runtime's perspective — it is one interchangeable Worker Contract implementation among others (`local-infer` is the other), distinguished only by advertised capabilities/resources.
- The full proposal, spec, design, and task trail for everything below lives in `openspec/changes/ray-worker-runtime/` (`proposal.md`, `specs/`, `design.md`, `tasks.md`). Read `design.md` for the actual architecture decisions and rationale (D1-D7); this doc only orients you toward it.

## Why tibios-ray has its own (modest) architecture track

tibios-core has a 31-document architecture structure. tibios-ray deliberately does not replicate that by symmetry — see `ray-worker-runtime`'s proposal Non-Goals. This directory holds only what is specific to *how tibios-ray implements* the Worker Contract behind the boundary; everything about the boundary itself stays in tibios-core.

## The flow

```
Worker (gRPC)  ->  WorkerRuntime  ->  CapabilityRegistry  ->  CapabilityProvider  ->  ModelSelectionPolicy  ->  BackendAdapter
```

The word "Worker" appears exactly once, at the gRPC-facing entity. Everything past that step is described in tibios-ray's own vocabulary:

1. **Worker Runtime** (`src/tibios_ray/runtime/worker_runtime.py`, `WorkerRuntime`) drives the per-execution lifecycle described in `18-worker-model.md` — dispatch, cooperative cancellation, always producing a final `ExecutionReport` — and delegates capability resolution to the registry. It never lets a Capability Provider exception escape the boundary.
2. **Capability Registry** (`src/tibios_ray/runtime/registry.py`, `CapabilityRegistry`) is the immutable, constructor-built index of registered Capability Providers. It resolves a capability name to a provider and advertises the aggregated catalog.
3. **Capability Provider** (`src/tibios_ray/capabilities/provider.py`, `CapabilityProvider` protocol) implements one capability (e.g. `chat.generate`), advertising a catalog of supported model families, backends, and flags instead of a hardcoded model list.
4. **Model Selection Policy** (`src/tibios_ray/selection/policy.py`, `ModelSelectionPolicy`) takes an already-resolved `ResolvedModelRef` and decides how to serve it — backend and quantization. It cannot accept a bare model-family string; that is a compile-time-enforced guarantee (see `design.md` D3 and the pyright fixture in `tests/unit/selection/pyright_fixtures/`).
5. **Backend Adapter** (`src/tibios_ray/backends/adapter.py` + per-modality protocols in `text.py`/`embedding.py`/`rerank.py`/`speech.py`) is the engine-agnostic contract Capability Providers execute against — no llama.cpp/TensorRT-LLM/vLLM/ONNX/Faster-Whisper import anywhere in this layer today.

See `design.md`'s Key Contracts and Data Flow sections for the exact signatures and sequencing; this doc intentionally does not reproduce them.

## Binding terminology rule

**"Worker" is reserved exclusively for the entity that implements the gRPC Worker Contract** (`18-worker-model.md`) as seen by tibios-core's Runtime. Internal units are never called "Worker" — a `ChatProvider` is a Capability Provider, not a Worker, and must never be misread as implementing the gRPC contract itself.

The sole sanctioned exception is `WorkerRuntime` (`runtime/worker_runtime.py`) — named for the thing it *is*: the host that directly drives the Worker Contract lifecycle inside tibios-ray.

This rule is enforced by a permanent, AST-identifier-based test (`tests/unit/runtime/test_naming_audit.py`), scanning `capabilities/`, `selection/`, `backends/`, `runtime/`, and `testing/` for any identifier containing "Worker" outside the `WorkerRuntime` exception. Docstrings that merely *discuss* the Worker Contract as a concept (e.g. quoting this rule, or citing `18-worker-model.md`) are not violations — only real code identifiers are.

## Module layout

| Path | Contents |
|---|---|
| `src/tibios_ray/execution/` | Worker Contract vocabulary: `ObjectId`/`ObjectVersion`/`ContentHash`, `ExecutionContext`/`AllocationContract`/`ResolvedModelRef`, `ExecutionChannel`/`CancellationToken`, `ExecutionEvent`, `ExecutionReport`/`ExecutionPulse`/`ExecutionPhase` |
| `src/tibios_ray/backends/` | `BackendAdapter` contract + per-modality execution protocols (text, embedding, rerank, speech) |
| `src/tibios_ray/selection/` | `ModelSelectionPolicy`, `ServingConstraints`, `ServingPlan`, `Quantization` |
| `src/tibios_ray/capabilities/` | `CapabilityProvider` protocol, `CapabilityDescriptor`/`CapabilityFlags`/`CapabilityCatalog`, `CapabilityName` |
| `src/tibios_ray/runtime/` | `WorkerRuntime` (lifecycle host), `CapabilityRegistry`, Worker Contract-conformant error types |
| `src/tibios_ray/testing/` | Shared test fakes (`InMemoryExecutionChannel`, `FakeExecutionContext`, `ManualCancellation`, `StubProvider`, `RecordingBackend`). Shipped inside the `tibios_ray` package so later phases can reuse them, but it is a **test-support package**, not part of the Worker Contract dispatch surface — nothing in `runtime/`, `capabilities/`, `selection/`, or `backends/` imports from it. |
| `src/tibios_ray/worker.py` | The composition root — the one place "Worker" names the gRPC contract entity. Builds a `CapabilityRegistry` from the registered Capability Providers and owns one `WorkerRuntime`. Still docstring-only: the actual gRPC wiring is blocked on the shared `.proto` Worker Contract definition, not yet present in this repo (tracked in tibios-core as a separate, in-progress change). |
| `src/tibios_ray/server.py` | Future gRPC entry point. Empty until the `.proto` contract exists. |

Dependencies point right-to-left only (`execution/` has no dependents inside this list depending on it circularly; `runtime/` depends on `capabilities/`, which depends on `selection/`, which depends on `backends/`) — see `design.md`'s Technical Approach diagram for the full one-way layering rationale.

## Where to go next

- Full proposal, specs, design, and task trail: `openspec/changes/ray-worker-runtime/`
- The contract this whole package implements behind: `../tibios-core/docs/architecture/18-worker-model.md`
