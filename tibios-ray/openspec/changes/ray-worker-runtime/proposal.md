# Proposal: Ray Worker Runtime (Foundation)

## Intent

**tibios-ray is an implementation of the TibiOS Worker Contract specialized in distributed AI execution. It extends the architecture behind the Worker boundary, never the boundary itself.**

This change opens tibios-ray's own architecture track. The Worker Contract (`../tibios-core/docs/architecture/18-worker-model.md`, tag `architecture-v1.0`) is the sole formal boundary with tibios-core and is referenced, never redefined or duplicated here. Everything proposed lives *behind* that boundary and is invisible to tibios-core.

## Design Principle: Capability-First, Not Model-Pinned

**Terminology**: "Worker" is reserved exclusively for the entity that implements the Worker Contract (`18-worker-model.md`) as seen by tibios-core's Runtime — one term, one concept. Internal units inside tibios-ray that provide a specific capability are called **Capability Providers**, never "Worker" — a `ChatProvider` does not implement the gRPC Worker Contract and must never be misread as if it did. ("Capability Handler" and "Model Family Adapter" were considered and rejected: "Handler" implies a callback/endpoint, and a Provider can support several model families at once, so it is not a single-family adapter.)

Capability Providers are organized by **capability**, never by vendor or model: `chat.generate`, `embedding.generate`, `rerank.documents`, `vision.understand`, `speech.transcribe` / `speech.synthesize`, `ocr.extract`. Each Capability Provider advertises a **catalog** of supported model families + backends + capability flags (streaming, tools, json, reasoning) instead of a hardcoded model list, so models evolve without breaking the design.

**MVP Capability Provider map (context, built in Phase 2):** Chat, Embedding, Reranker, Vision, Speech, OCR. Chat targets six strategic families — Qwen, Llama, DeepSeek (reasoning/code priority), Gemma, Mistral, Kimi (long-context/agents priority).

**Flow**: `Worker (gRPC)` → `Worker Runtime` → `Capability Registry` → `Capability Provider` (e.g. Chat Provider) → `Model Selection Policy` → `Backend Adapter` → concrete model. The word "Worker" never reappears past the first step.

## Boundary Rules (binding)

| Rule | Source |
|---|---|
| From the Runtime's perspective there is **no difference** between `local-infer` and tibios-ray — interchangeable Worker Contract implementations distinguished only by advertised capabilities/resources. Scheduling's Capability Filter does the matching. | `25-ai-runtime.md` |
| **No size/cost routing rule** (`if model < X then local-infer`) may exist anywhere. Explicitly rejected. | `25-ai-runtime.md` Anti-Patterns |
| **Model Selection Policy is narrow**: given an *already-resolved concrete Model ObjectId*, decide **how to serve it** (backend, quantization/precision). It MUST NEVER receive a raw family string and pick a model — that is scheduling-time discovery, forbidden for Workers. | `18-worker-model.md` ("Dependency References already resolved") |
| The AI Convenience Library / `Profile` concept (`Profile::Developer → family: deepseek`) is **client-side**, in a future layer `Application → AI Convenience Library → TibiOS SDK → Runtime API` — architecturally opposite this repo. Not proposed here. | `27-sdk.md` ("SDK contains no domain logic") |

## Scope

### In Scope — Phase 1 "Foundation"

Answer four architectural questions and produce **skeleton/interfaces, not implementations**:

1. **Worker Runtime** — what drives the Worker Contract lifecycle inside tibios-ray (Execution Context → Channel → Events → Report → Pulse, cancellation) and dispatches to Capability Providers.
2. **Capability Registry** — how Capability Providers register and advertise capabilities/catalog upward, and what a Capability Provider's interface is.
3. **Model Selection Policy** — narrow scope per boundary rules above.
4. **Backend Adapters** — the contract decoupling Capability Providers from engines.

### Out of Scope — Roadmap (documented, not this change)

| Phase | Content |
|---|---|
| 2 | The 6 Official Capability Providers as empty interfaces + tests |
| 3 | Model Catalog (families, versions, capabilities, minimum requirements, backend compatibility) — still no complex logic |
| 4 | Backend integrations: llama.cpp, TensorRT-LLM, vLLM, ONNX Runtime, Faster-Whisper |
| v2 Workers | Translation, Code (DeepSeek Coder), Reasoning, Diffusion, Video, Agent (composition of other Workers) |

## Non-Goals (not designed anywhere, pending real evidence of need)

Dynamic plugins · marketplace · hot-reload of models · auto-discovery · benchmark-based advanced selection policies · multi-model routing · agent frameworks.

Also non-goals: replicating tibios-core's 31-document architecture structure by symmetry; scaffolding test/quality tooling (owned by `python-foundation`).

## Capabilities

### New Capabilities

- `worker-runtime`: host that implements the Worker Contract inside tibios-ray and drives per-execution lifecycle, dispatching to Capability Providers via the Capability Registry.
- `capability-registry`: Capability Provider interface definition, registration, and capability/catalog advertisement.
- `model-selection-policy`: resolved-ObjectId → backend + quantization decision.
- `backend-adapter`: engine-agnostic contract Capability Providers execute against.

### Modified Capabilities

- None. (`python-foundation`'s naming constraint is confirmed and resolved — see Risks.)

## Approach

Define the four concepts as Python protocols/ABCs with docstrings citing `18-worker-model.md` / `25-ai-runtime.md`, plus interface-level tests. No inference engine, no Ray distribution logic, no gRPC wiring. Every type stays behind the Worker Contract; nothing introduces a Runtime-visible concept.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `src/tibios_ray/runtime/` | New | Worker Runtime + Capability Registry interfaces |
| `src/tibios_ray/selection/` | New | Model Selection Policy interface |
| `src/tibios_ray/backends/` | New | Backend Adapter contract |
| `docs/architecture/` | New | tibios-ray's own architecture track (modest, concept-driven) |
| `src/tibios_ray/worker.py` | Modified | stub docstring aligned with this proposal |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| **Cross-repo dependency (open question):** resolving `preferred_family: deepseek` → concrete Model ObjectId needs a generic metadata/tag query on the Object Store; `23-object-store.md` documents identity-based queries only (GetObject/GetVersion/ResolveContent/Exists/ListVersions/FindReferences). May require a future tibios-core proposal. | High | **Not resolved here by design.** Phase 1 assumes the ObjectId arrives resolved; nothing in this scope blocks on it. |
| **Terminology, resolved:** `python-foundation` forbade calling internal handlers "Workers" (reserving the word for the whole process, per `18-worker-model.md`) and suggested "Capability Handler"/"Model Family Adapter". This proposal agrees with the constraint and settles the name: **Capability Provider** — "Handler" implies a callback/endpoint (too small), "Adapter" implies one family per unit (a Provider can support several families at once). One term (`Worker`), one concept, kept exclusively for the gRPC contract entity; internal units never reuse it. | Low | `python-foundation`'s stub docstrings updated to reference "Capability Provider" during apply. |
| Interfaces drift from the not-yet-existing `.proto` at `../TibiOS/proto/` | Med | Interfaces cite `18-worker-model.md`; no transport types in Phase 1 |
| Over-scoping Model Selection Policy into model discovery | Med | Boundary rule stated as binding; verify phase must check it |
| Architecture track grows by symmetry with tibios-core rather than need | Low | Explicit non-goal |

## Rollback Plan

Additive only — new packages, new docs, no existing behavior touched. `git revert` of the change's commits restores the `python-foundation` state exactly. No data, schema, or contract migration exists to unwind.

## Dependencies

- `python-foundation` (test/lint/type tooling and package layout) applied first.
- `../tibios-core/docs/architecture/` at tag `architecture-v1.0` (read-only reference).
- **Open, non-blocking:** Object Store metadata/tag query capability (see Risks).

## Success Criteria

- [ ] Worker Runtime, Capability Registry, Model Selection Policy, Backend Adapter each exist as a documented interface with rationale
- [ ] Zero duplication of `18-worker-model.md` content — references only
- [ ] No routing rule between `local-infer` and tibios-ray exists anywhere in the code or docs
- [ ] Model Selection Policy signature accepts a resolved Model ObjectId and cannot accept a bare family string
- [ ] Capabilities are declared per-Capability-Provider; no model name is hardcoded in a Provider
- [ ] No internal type or identifier is named "Worker" — reserved exclusively for the gRPC Worker Contract entity; internal capability units are named "Capability Provider"
- [ ] Phases 2–4 and v2 Capability Providers are recorded as roadmap, with no Phase 1 code anticipating them
