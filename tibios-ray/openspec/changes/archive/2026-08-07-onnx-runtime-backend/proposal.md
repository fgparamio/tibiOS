# Proposal: The ONNX Runtime Embedding and Rerank Backend

## Intent

`llamacpp-backend` and `vllm-backend` (both archived) delivered two concrete adapters — and **both serve `chat.generate`**. The engine-agnostic contract has therefore only ever been tested against one modality. Design decision D4 refused a unified `infer()` and split the contract into per-modality protocols (`text.py`, `embedding.py`, `rerank.py`, `speech.py`); `embedding.py`'s own docstring names *"ONNX Runtime in Phase 4"*. Meanwhile `EMBEDDING_GENERATE_DESCRIPTOR` and `RERANK_DOCUMENTS_DESCRIPTOR` advertise `BackendId("onnxruntime")`, the catalog carries six `ModelDescriptor` entries whose every `BackendSupport` row is `onnxruntime` — and `EmbeddingProvider`/`RerankProvider` cannot produce a single vector.

This change delivers the **first non-text-generation Backend Adapter**, and the first to satisfy **two** modality protocols from one engine. That is what makes D4 a proven split rather than an asserted one.

## Open Questions — for `sdd-design`, deliberately unresolved here

ONNX Runtime's residency shape is a **third** shape, structurally unlike both predecessors: `InferenceSession.run()` is synchronous, stateless per call, and holds no KV cache. Neither llama.cpp's per-acquire lock + thread/queue pump (LC1–LC12) nor vLLM's native-async continuous batching (VL1–VL14) transfers. The obvious reading — a shared refcounted session driven by `asyncio.to_thread(session.run, ...)`, no pump, no lock — is **plausible, not decided**. Assuming it is exactly the mistake `vllm-backend` warned about (do not generalize a mechanism from N=2).

| # | Question | Must be settled by |
|---|---|---|
| 1 | Shared-refcounted (vLLM-like) vs per-acquire (llama.cpp-like) ORT session residency — and is concurrent `run()` on one session safe for every execution provider we target, or only CPU? | `sdd-design`, with a concurrency test, not a docstring |
| 2 | One class or two (`OnnxEmbeddingBackend` / `OnnxRerankBackend`) sharing a session-loading helper — driven by whether `supports()` can distinguish the two modalities from `backend` alone | `sdd-design` |
| 3 | Tokenizer artifact resolution: ORT consumes token ids, not text. Second out-of-band artifact, same debt class as llama.cpp's GGUF path | `sdd-design` (seam shape); resolution-from-`ResolvedModelRef` stays deferred |
| 4 | Execution-provider (CPU/CUDA) selection policy and where it is supplied — `ServingPlanLike` exposes only `.backend` today | `sdd-design` |

## Scope

### In Scope

- `src/tibios_ray/engines/onnxrt.py` — module named to shadow neither the `onnxruntime` SDK nor the `onnx` format package (llamacpp's `llamacpp.py`-not-`llama_cpp.py` rule).
- Backend class(es) structurally satisfying `EmbeddingBackend` and `RerankBackend`; `engines/__init__.py` re-exports.
- Residency lifecycle per OQ1; `supports(plan)` on `BackendId("onnxruntime")`.
- `embed()` → one `Vector` per input, order-preserving. `rerank()` → one `RerankResult` per document, `index` referring back into the input sequence. Neither streams.
- Non-blocking execution: the synchronous ORT call must never stall the event loop; proven by test.
- Injectable `InferenceSessionLike` Protocol + tokenizer seam + lazy SDK import (LC11/VL8 precedent): the unit tier runs with no `onnxruntime`, no numpy in `backends/`, no model files, no network.
- `onnx` optional extra in `pyproject.toml`; one opt-in integration smoke against a real small ONNX model, env-var gated.

### Out of Scope

- **`EmbeddingProvider`/`RerankProvider` wiring** — same deferral as both predecessors: no composition root exists, `worker.py` still blocked. Providers keep raising `NoBackendAvailableError`.
- `speech.synthesize` (kokoro) and `ocr.extract` (paddleocr) — also `onnxruntime`, but different protocols (`speech.py`; no OCR protocol exists at all).
- Tokenizer/model artifact resolution from `ResolvedModelRef` · CUDA/TensorRT EP tuning · dynamic batching or a request scheduler · runtime quantization selection · multi-model residency and eviction.
- `tests/unit/backends/test_no_engine_imports.py` — **no change needed**: `"onnxruntime"` is already in `FORBIDDEN_ENGINE_MODULES` and the guard is already recursive.

## Capabilities

### New Capabilities

- `onnxruntime-backend`: residency lifecycle, non-blocking synchronous-engine execution, batch embedding and rerank semantics, tokenizer/session seams, SDK-free testability, optional-extra packaging. **One spec, not two** — the two execution methods differ only in output shape; residency, EP policy, tokenizer handling and isolation are identical. Capability ≠ class; this does not prejudge OQ2.

### Modified Capabilities

- `backend-adapter`: its Backend Independence Principle names the contract as "`supports`/`acquire`/`generate`/`release`". `generate` is a *text* method — `EmbeddingBackend` has `embed`, `RerankBackend` has `rerank`. The first non-text adapter makes that phrasing false. Restate the principle modality-agnostically (residency + identity, plus *a* per-modality execution method). Same pattern as `llamacpp-backend` restating the Phase-1 prohibition. Formalization only; zero code change.

## Approach

Reuse the proven seams, not the proven mechanisms. Both predecessors converged on the same three things — a structural SDK Protocol, a lazy import inside a default factory, an optional extra — and those transfer verbatim because they are about *isolation*, not about engine shape. What does **not** transfer is residency and the async bridge: that is OQ1's job. `engines/` stays the SDK-bound package, `backends/` stays the contract package, layer direction unchanged. Strict TDD throughout.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `src/tibios_ray/engines/onnxrt.py` | New | Backend(s) + `InferenceSessionLike` + tokenizer seam |
| `src/tibios_ray/engines/__init__.py` | Modified | Re-exports |
| `pyproject.toml` | Modified | `onnx` optional extra |
| `tests/unit/engines/test_onnxrt_*.py` | New | Residency, concurrency, embed/rerank shape, SDK-free import |
| `tests/integration/**` | New | Opt-in real-model smoke |
| `openspec/specs/backend-adapter/spec.md` | Modified | Modality-agnostic contract phrasing |
| `src/tibios_ray/backends/{embedding,rerank}.py` | Untouched | Protocols already final |
| `src/tibios_ray/capabilities/*` | Untouched | Providers still raise `NoBackendAvailableError` |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `InferenceSession.run()` is blocking; called inline it stalls the event loop | High | Thread offload; design must prove non-blocking by test (LC precedent) |
| Assumed concurrent-`run()` safety is wrong for some execution provider | High | Do not assume — OQ1 decides with a concurrent-call test; fall back to per-acquire or a lock if unproven |
| Tokenizer and model are two independent out-of-band artifacts that must match | Med | Accepted debt, documented in-module (GGUF-path precedent) |
| Two modality protocols in one change doubles review surface | Med | Chained PRs — embedding first, rerank reuses the session helper |
| Stub diverges from the real ORT signature (`run(output_names, input_feed)`, numpy I/O) | Med | Opt-in integration smoke is the only thing that catches it — keep it runnable |
| `onnxruntime` cp314 wheel availability unknown | Med | Optional extra + lazy import; verify wheel and any `python_version` marker during apply (vllm marker precedent) |
| numpy enters the graph via ORT I/O | Low | Confined behind the lazy seam in `engines/`; `backends/` stays numpy-free, guard already enforces it |

## Rollback Plan

Additive except two edits (`pyproject.toml` extra, `engines/__init__.py` re-exports) and one spec formalization. No contract fields, Provider, or runtime behavior change — Providers raise `NoBackendAvailableError` before and after, and `llamacpp-text-backend` / `vllm-text-backend` are untouched. `git revert` of the slice commits restores the archived `vllm-backend` state exactly.

## Delivery

Estimated ~550–650 changed lines — **over the 400-line budget**. Chained PRs by work unit:

1. `onnxrt.py` session + tokenizer seams, residency (`backend_id`/`supports`/`acquire`/`release`), optional extra, `backend-adapter` delta.
2. `embed()` + `rerank()` execution, non-blocking bridge, concurrency behavior, opt-in integration smoke.

## Dependencies

- `capability-providers`, `model-catalog`, `llamacpp-backend`, `vllm-backend` (archived) — **satisfied**.
- `proto-worker-contract` (tibios-core) — **not blocking**; only composition needs it.

## Success Criteria

- [ ] The backend(s) satisfy `EmbeddingBackend` and `RerankBackend` (pyright-verified, no base class)
- [ ] Unit suite passes with `onnxruntime` **absent** — no model files, no network, no GPU
- [ ] `embed()` returns exactly one `Vector` per input, in input order, all of equal length
- [ ] `rerank()` returns one `RerankResult` per document with `index` valid against the input sequence
- [ ] The synchronous ORT call is provably off the event loop (a concurrent unrelated coroutine makes progress during a slow `run()`)
- [ ] Residency behaves exactly as OQ1 resolves it, proven by a concurrency test — not by a docstring
- [ ] `backends/` imports no engine SDK under recursive inspection (guard unchanged)
- [ ] `backend-adapter` states the contract modality-agnostically; `llamacpp-text-backend` and `vllm-text-backend` still pass unchanged
- [ ] Opt-in integration smoke passes against a real small ONNX model when enabled
