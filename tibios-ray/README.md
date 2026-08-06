# tibios-ray

Python AI execution Worker for **TibiOS**, a distributed operating system. `tibios-ray` is one of two Worker implementations for [`tibios-core`](../tibios-core)'s Runtime — the heavy AI execution path, reached over gRPC. (`local-infer`, in-process and CPU-bound via llama.cpp, is the other. From the Runtime's perspective they are interchangeable.)

> **tibios-ray is an implementation of the TibiOS Worker Contract specialized in distributed AI execution. It extends the architecture behind the Worker boundary, never the boundary itself.**

This repository lives inside the [`tibiOS`](https://github.com/fgparamio/tibiOS) monorepo, as a sibling of `tibios-core` (Rust — the distributed OS control plane, architecture frozen at `architecture-v1.0`).

## Table of contents

- [Position in TibiOS](#position-in-tibios)
- [Core principle: the Worker boundary](#core-principle-the-worker-boundary)
- [Terminology — read this before naming anything](#terminology--read-this-before-naming-anything)
- [Architecture](#architecture)
- [Design principles](#design-principles)
- [Capability Providers](#capability-providers)
- [Model family naming (FLC)](#model-family-naming-flc)
- [Project status](#project-status)
- [Development](#development)
- [Spec-Driven Development (SDD)](#spec-driven-development-sdd)
- [Cross-repo dependency: the gRPC contract](#cross-repo-dependency-the-grpc-contract)
- [Non-goals](#non-goals)
- [Further reading](#further-reading)

## Position in TibiOS

TibiOS's Runtime treats AI inference as an ordinary Workload, not a special case:

> "The AI Runtime introduces no new architectural primitives. It composes the Runtime's existing primitives — Object, Resource, Scheduling, Allocation, Worker, Object Store, Replication — to execute AI workloads." — `tibios-core/docs/architecture/25-ai-runtime.md`

Concretely: a chat/embedding/vision/etc. request is an ordinary Workload carrying AI-shaped Objects (`Model`, `Prompt`, `Conversation Context`, …). Scheduling's Capability Filter matches the Workload's declared capability requirement against whichever Worker (`local-infer` or `tibios-ray`) advertises it — the Runtime never "routes to AI" as a special decision, and it never knows or cares whether a Worker is backed by llama.cpp, Ray, vLLM, or TensorRT.

**There is no local-infer-vs-tibios-ray rule anywhere in this codebase, and there must never be one.** The boundary between them is *purely* a function of advertised capabilities and resources, matched generically by the Scheduler — never a hardcoded "if model is small, run locally" conditional. A permanent test (`tests/unit/runtime/test_no_local_infer_routing.py`) guards this invariant.

## Core principle: the Worker boundary

The gRPC Worker Contract (`tibios-core/docs/architecture/18-worker-model.md`, pinned at tag `architecture-v1.0`) is the **sole formal boundary** between `tibios-core` and `tibios-ray`. It is referenced throughout this codebase, never redefined or duplicated. Everything this repository builds lives *behind* that boundary — invisible to `tibios-core`, free to evolve on its own architecture track.

That contract, in one line: the Runtime creates an immutable **Execution Context**, hands it to a **Worker**, the Worker streams **Execution Events** over an **Execution Channel** while it works, and produces one final **Execution Report** on completion. *"Execution produces events. Completion produces a report."*

## Terminology — read this before naming anything

**"Worker" is reserved exclusively for the entity implementing the gRPC Worker Contract as seen by `tibios-core`'s Runtime.** Internal, capability-specific units inside `tibios-ray` are called **Capability Providers** — never "Worker", "Handler", or "Adapter":

- *"Handler"* was rejected — it implies a callback/endpoint, too small a concept.
- *"Adapter"* was rejected — it implies one unit per model family, but a Provider can support several families at once.

The **one sanctioned exception** is `WorkerRuntime` (`src/tibios_ray/runtime/worker_runtime.py`) — it directly drives the Worker Contract lifecycle, so "Worker" legitimately reappears there and only there. A permanent AST-based test (`tests/unit/runtime/test_naming_audit.py`) scans every package and fails on any other "Worker"-named identifier.

Flow, and where the word "Worker" is (and isn't) allowed to appear:

```
Worker (gRPC entity)
    │
    ▼
Worker Runtime                  ← the ONE sanctioned exception
    │
    ▼
Capability Registry
    │
    ▼
Capability Provider (e.g. Chat Provider)
    │
    ▼
Model Selection Policy
    │
    ▼
Backend Adapter
    │
    ▼
concrete model
```

The word "Worker" never reappears past the first two steps.

## Architecture

Modules are layered strictly one-way — dependencies point right-to-left, no cycles:

```
execution/                                    Worker Contract vocabulary
    ▲        ▲             ▲            ▲     (ExecutionContext, Channel, Event,
    │        │             │            │      Report, Pulse, cancellation)
runtime/ → capabilities/ → selection/ → backends/
    │                                          testing/  — shared fakes, reused
    └── the only place "Worker" may reappear       by every layer above
```

| Package | Purpose |
|---|---|
| `execution/` | Worker Contract vocabulary: `ExecutionContext`, `ExecutionChannel`, `ExecutionEvent` (closed 6-variant tagged union), `ExecutionReport`, `ExecutionPulse`, `ResolvedModelRef`, `ObjectId`/`ObjectVersion`/`ContentHash`. Frozen, slotted dataclasses throughout — identity types are proof-carrying, never `NewType[str]` aliases. |
| `backends/` | `BackendAdapter` — the engine-agnostic contract Capability Providers execute against. No unified `infer()`: text generation, embedding, and speech share only load/unload/health (model residency); per-modality protocols (`TextGenerationBackend`, `EmbeddingBackend`, `RerankBackend`, `TranscriptionBackend`) hold the rest. |
| `selection/` | `ModelSelectionPolicy` — given an **already-resolved** `ResolvedModelRef`, decides backend + quantization/precision *only*. Structurally incapable of accepting a raw family string (pyright-fixture-guarded) — picking *which* model is scheduling-time discovery, forbidden for Workers. |
| `capabilities/` | `CapabilityProvider` Protocol, `CapabilityDescriptor` (the outward catalog: capability name, families, backends, flags), `CapabilityRegistry`'s provider-side contract, and the seven concrete Providers (see below). |
| `runtime/` | `WorkerRuntime` (drives the Worker Contract lifecycle, dispatches via the registry — never holds direct references to Providers) and `CapabilityRegistry` (immutable, built once at the composition root from a fixed provider sequence; rejects duplicate capabilities and empty catalogs). |
| `testing/` | Shared fakes (`InMemoryExecutionChannel`, `FakeExecutionContext`, `ManualCancellation`, `StubProvider`, `RecordingBackend`) — a fake Execution Context plus an in-memory channel, no real infrastructure, per `18-worker-model.md`'s own testability principle. |

## Design principles

Seven binding architecture decisions, established in the `ray-worker-runtime` foundation and never revisited casually:

1. **`typing.Protocol` everywhere, no base classes.** Structural typing removes the import edge from every Provider/Adapter back to the framework; fakes need no base class; an adapter implementing two modalities is naturally both without multiple inheritance.
2. **Frozen/slotted dataclasses for identity, never `NewType`.** `NewType[str]` is a no-op at runtime — `ObjectId("deepseek")` would type-check fine. A dataclass requiring a `ContentHash` makes model resolution *proof-carrying*: only the Runtime's already-resolved Dependency References can produce one.
3. **No unified Backend Adapter.** Forcing text/embedding/speech into one `infer(input) -> output` would push every parameter into `dict[str, Any]` and destroy type safety.
4. **Cooperative cancellation**, never raw `asyncio.CancelledError` — the Worker Contract requires acknowledge → cleanup → final events → Report; an unwound task would skip all four.
5. **`CapabilityRegistry` is immutable**, built once from an explicit provider sequence at the composition root — no `register()` mutation, no auto-discovery (both are explicit non-goals).
6. **`ExecutionEvent` is a closed tagged union** (`OutputChunk | Progress | Warning | CheckpointCreated | MetricsSnapshot | EndOfStream`) — adding a variant breaks every consumer loudly via exhaustiveness checking, by design.
7. **Capability-first, never model-pinned.** Providers are organized by capability (`chat.generate`, `embedding.generate`, …), never by vendor. Each Provider advertises a *catalog* of supported families/backends/flags instead of a hardcoded model list, so models can evolve without breaking the design.

## Capability Providers

Six modules, seven registrable classes (`speech.py` holds two — `CapabilityDescriptor.capability` is singular, so transcription and synthesis can't share one Provider):

| Module | Capability | Families | Backend(s) |
|---|---|---|---|
| `chat.py` | `chat.generate` | qwen, llama, deepseek, gemma, mistral, kimi | llama_cpp, tensorrt_llm, vllm |
| `embedding.py` | `embedding.generate` | bge, nomic_embed, e5, jina_embeddings | onnxruntime |
| `rerank.py` | `rerank.documents` | bge_reranker, jina_reranker | onnxruntime |
| `vision.py` | `vision.understand` | qwen_vl, gemma, llama_vision | vllm, tensorrt_llm |
| `speech.py` | `speech.transcribe` | whisper | faster_whisper |
| `speech.py` | `speech.synthesize` | kokoro | onnxruntime |
| `ocr.py` | `ocr.extract` | paddleocr | onnxruntime |

Note `gemma` legitimately appears under **both** `chat.generate` and `vision.understand` — Google publishes no distinct "Gemma Vision" lineage (Gemma 3 is natively multimodal), so the family label is correctly shared, not duplicated or renamed.

All seven Providers are **zero-field, frozen, slotted dataclasses** — mechanically guaranteeing they hold no backend reference. Every `execute()` currently raises `NoBackendAvailableError` rather than faking success: no real inference engine is wired in yet (that's Phase 4, still future, and partly blocked — see below). `WorkerRuntime` catches this and returns a Failed `ExecutionReport`, never a bare exception across the Worker Contract boundary.

## Model family naming (FLC)

`ModelFamily` labels follow the **Family Label Convention** — a pure, context-free function of a model's *published lineage name*: shape `^[a-z][a-z0-9_]*$`, drop org prefix / version / size / quantization / tuning-stage (`instruct`, `it`) / locale tokens, **keep** every other published token (including modality tokens the publisher actually used, e.g. `vl`, `reranker`, `embed`).

Purity is the load-bearing property: the same function will be applied on the Model Catalog side (Phase 3, in progress) to a *resolved* model, so exact `ModelFamily` equality works across that boundary with no synonym table needed. (`paddleocr` staying `paddleocr` rather than collapsing to `paddle` — a DL framework, not a model lineage — is the canonical test of whether a proposed simplification of this rule is actually correct.)

## Project status

Each phase is its own Spec-Driven Development change under `openspec/changes/` (archived ones move to `openspec/changes/archive/` once done, and their specs merge into `openspec/specs/`).

| Phase | Change | Status |
|---|---|---|
| 0 | `python-foundation` — pytest/ruff/pyright, package skeleton | ✅ Applied |
| 1 | `ray-worker-runtime` — Worker Runtime, Capability Registry, Model Selection Policy, Backend Adapter (interfaces only) | ✅ Archived |
| 2 | `capability-providers` — the 7 official Capability Providers (real catalogs, no real inference yet) | ✅ Archived |
| 3 | `model-catalog` — per-model reference data: versions, context windows, min VRAM, backend/quantization compatibility | 🚧 In progress |
| 4 | Real backend integrations (llama.cpp, TensorRT-LLM, vLLM, ONNX Runtime, Faster-Whisper) | ⏳ Not started |
| — | `worker.py`/`server.py` gRPC wiring | ⏳ Blocked on the shared `.proto` contract (see below) |
| v2 | Translation, Code, Reasoning, Diffusion, Video, Agent Providers | 📋 Roadmap only, not scoped |

Current test count: **284 passing** (`uv run pytest`), ruff and pyright clean. Strict TDD Mode is permanently active for this project — every unit of work is expected to land as a failing-test commit followed by a passing-implementation commit.

## Development

Requires Python ≥3.13 and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync                    # install dependencies
uv run pytest              # run the test suite
uv run ruff check          # lint
uv run pyright             # type check
```

No build step exists or is needed — this is a library/service package, not a compiled artifact.

## Spec-Driven Development (SDD)

This project follows a proposal → spec → design → tasks → apply → verify → archive cycle for every substantial change, tracked under `openspec/`:

- `openspec/specs/` — the current, frozen contract for every capability that has shipped (read these to understand *what exists*).
- `openspec/changes/<name>/` — an in-progress change's proposal/spec/design/tasks.
- `openspec/changes/archive/<date>-<name>/` — a completed change's full history, including its verification report.

Each change is also mirrored to persistent memory (Engram) under topic keys like `sdd/<change-name>/proposal`, `.../spec`, `.../design`, `.../tasks`, `.../apply-progress`, `.../verify-report`, `.../archive-report`, for cross-session continuity.

## Cross-repo dependency: the gRPC contract

The `.proto` contract between `tibios-core` and `tibios-ray` does not exist yet. Its proposed location is `../TibiOS/proto/` — a sibling of both repos, since both a Rust and a Python build must compile against it. Until it exists, `18-worker-model.md` is the source of truth for what the interface must express, and `worker.py`/`server.py` remain docstring-only composition-root stubs.

A sibling change, `proto-worker-contract`, is in progress on the `tibios-core` side. Known shape agreed so far (cross-repo coordination, not yet finalized):

- Three RPCs: `SubmitJob` (server-streaming), `Cancel`, `Pulse` — not a single bidirectional stream.
- An `ExecutionResponse { oneof { event, report } }` envelope, since `ExecutionReport` has no variant in the closed `ExecutionEvent` union and needs somewhere to travel on the same stream.
- An open question: `ExecutionContext` here is missing Security Context, Observability Context, and Execution Parameters relative to `18-worker-model.md` — logged as pending debt, deliberately not retrofitted until the `.proto` pins exact shapes (to avoid guessing twice).

## Non-goals

Explicitly out of scope, repeated across every phase's proposal so they don't creep back in one at a time: dynamic plugins, a model marketplace, hot-reload of models, auto-discovery, benchmark-based advanced selection policies, multi-model routing, agent frameworks, and an "AI Convenience Library" / `Profile` concept (that belongs client-side, in a future `Application → AI Convenience Library → TibiOS SDK → Runtime API` layer — architecturally opposite this repository, which sits behind the Worker Contract on the execution side).

## Further reading

- `tibios-core/docs/architecture/18-worker-model.md` — the Worker Contract itself.
- `tibios-core/docs/architecture/25-ai-runtime.md` — why AI workloads need no special Runtime treatment.
- `tibios-core/docs/architecture/27-sdk.md` — why client-side conveniences (like `Profile`) can never live in the generic SDK, and by extension not in this repo either.
- `tibios-core/docs/architecture/23-object-store.md` — the still-missing generic metadata query this project's model resolution will eventually depend on.
- `docs/architecture/01-worker-runtime.md` (this repo) — a short pointer/orientation doc into the `ray-worker-runtime` design, deliberately not a restatement of it.
