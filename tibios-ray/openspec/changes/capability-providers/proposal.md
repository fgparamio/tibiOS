# Proposal: The Six Official Capability Providers

## Intent

`ray-worker-runtime` (archived) froze the contracts — `CapabilityProvider`, `CapabilityDescriptor`, `CapabilityRegistry`, `ModelSelectionPolicy`, per-modality `BackendAdapter` — but zero Providers implement them, so tibios-ray still advertises an empty catalog. This change (roadmap Phase 2, "the 6 Official Capability Providers as empty interfaces + tests") makes the Worker's capability catalog **real and truthful** before any engine exists, which is exactly what Scheduling's Capability Filter matches on.

## Scope

### In Scope — MVP capability map (capability-first, never model-pinned)

| Module | Capability | Families | Backends |
|---|---|---|---|
| `chat.py` | `chat.generate` | qwen, llama, deepseek, gemma, mistral, kimi | llama_cpp, tensorrt_llm, vllm |
| `embedding.py` | `embedding.generate` | bge, nomic, e5, jina | onnxruntime |
| `rerank.py` | `rerank.documents` | bge_reranker, jina_reranker | onnxruntime |
| `vision.py` | `vision.understand` | qwen_vl, gemma_vision, llama_vision | vllm, tensorrt_llm |
| `speech.py` | `speech.transcribe` / `speech.synthesize` | whisper / kokoro | faster_whisper / onnxruntime |
| `ocr.py` | `ocr.extract` | paddleocr | onnxruntime |

Descriptors are **genuinely correct catalog data**, plus realistic `CapabilityFlags` (e.g. Chat: streaming+tools+json+reasoning; Embedding/Rerank: none).

**Decision — `execute()` without a backend: raise, never fake.** Each Provider holds **no** backend reference and raises `NoBackendAvailableError` (new `capabilities/errors.py`; a plain `Exception`, since `capabilities/` must not import `runtime/`). `WorkerRuntime._dispatch` already catches any Provider exception and returns a Failed `ExecutionReport`, so this is contract-correct, not a crash. Delegating to a `BackendAdapter` was rejected: no `ServingPlan`/policy implementation exists, and vision, OCR and synthesis have **no modality adapter protocol at all** — inventing three is Phase 4. Returning a fake COMPLETED report was rejected outright: it would lie to the Runtime.

**Decision — 6 modules, 7 registrable Providers.** `CapabilityDescriptor.capability` is singular and the registry is one-provider-per-capability, so Speech ships two classes (transcribe, synthesize) in one module.

**Delivery**: `auto-chain` — one Provider module per chained PR slice (~7), each ≤400 lines. Slice 1 also carries `errors.py` and the shared conformance harness.

### Out of Scope

Real engine integration (Phase 4) · Model Catalog metadata (Phase 3) · new backend protocols for vision/OCR/synthesis · registering Providers in `worker.py` (blocked on `proto-worker-contract`) · all `ray-worker-runtime` non-goals (dynamic plugins, marketplace, hot-reload, auto-discovery, benchmark policies, multi-model routing, agent frameworks).

## Capabilities

### New Capabilities

- `capability-providers`: the six official Providers — descriptor correctness/stability, uniform no-backend `execute()` failure, registry co-registration, and the no-model-pinning / no-`local-infer`-routing invariants. One spec, not six near-identical ones: behavior is uniform, only catalog data varies.

### Modified Capabilities

- None. The foundation specs are frozen; this change implements against them without changing a requirement.

## Approach

Per design decision **D2** ("Phase 2 drops six Providers here"), Providers live in `src/tibios_ray/capabilities/`, **not** a new `providers/` package. Each is a frozen, slotted dataclass satisfying `CapabilityProvider` structurally (D1 — no base class), exposing a module-level descriptor constant. Strict TDD: tests first, mirroring package layout. No `local-infer` vs tibios-ray rule anywhere — the boundary emerges from advertised capabilities matched generically by tibios-core.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `src/tibios_ray/capabilities/{chat,embedding,rerank,vision,speech,ocr}.py` | New | One module per Provider |
| `src/tibios_ray/capabilities/errors.py` | New | `NoBackendAvailableError` |
| `src/tibios_ray/capabilities/__init__.py` | Modified | Exports |
| `tests/unit/capabilities/**` | New | Per-Provider + shared conformance/registry tests |
| `src/tibios_ray/worker.py` | Untouched | Composition still blocked on `.proto` |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Advertising capabilities that cannot execute | Med | Nothing can dispatch yet (no gRPC transport, Providers not wired into `worker.py`); failure is an explicit Failed Report, never silent |
| `ModelFamily` label vocabulary undecided (`qwen` vs `qwen2.5-vl`) | Med | Open question for `sdd-design`; labels are additive catalog data |
| Catalog drifts from reality as families evolve | Low | Tests assert stability + shape, not exhaustiveness |
| Temptation to invent vision/OCR/synthesis backend protocols | Med | Explicit non-goal; Providers hold no backend reference |
| Chained slices diverge in error/descriptor style | Low | Shared conformance harness lands in slice 1 |

## Rollback Plan

Purely additive: new modules, new tests, one `__init__.py` export edit. No existing behavior, contract, or data is touched. `git revert` of the slice commits restores the archived `ray-worker-runtime` state exactly.

## Dependencies

- `ray-worker-runtime` (archived, merged) — **satisfied**.
- `proto-worker-contract` (sibling, in progress) — **not blocking**; only composition/transport needs it.

## Success Criteria

- [ ] Seven Providers across six modules satisfy `CapabilityProvider` (pyright-verified, no base class)
- [ ] All seven register together in one `CapabilityRegistry` with no duplicate-capability or empty-catalog rejection; `catalog()` returns the union
- [ ] Every descriptor matches the map above and is asserted stable by test
- [ ] `execute()` raises `NoBackendAvailableError` for all seven; no Provider ever returns a COMPLETED report
- [ ] `WorkerRuntime` dispatch to any Provider yields a Failed `ExecutionReport` with a clear failure, never a bare exception
- [ ] No model name, no `local-infer` reference, and no size/cost routing conditional exists in any Provider
- [ ] `capabilities/` still imports no `runtime/` symbol; no new backend protocol added
