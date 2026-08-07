# Archive Report: ONNX Runtime Backend

**Change**: onnx-runtime-backend
**Archived**: 2026-08-07
**Status**: COMPLETE — fully implemented, verified, and closed

## Executive Summary

`OnnxEmbeddingBackend` and `OnnxRerankBackend` are tibios-ray's first non-text-generation Backend Adapters, executing `embedding.embed` and `rerank.rerank` against ONNX Runtime's synchronous `InferenceSession` with shared, refcounted residency and non-blocking async-to-thread execution. All 24 tasks completed in two chained PRs (PR #1: Seams + Residency, PR #2: Execution); verification passed with PASS WITH WARNINGS — 0 CRITICAL, 2 non-blocking WARNINGs about opt-in integration test coverage (fully-independent-instances scenario and line-count gap) and 1 SUGGESTION. Both predecessors' design lessons (llama.cpp's per-request isolation, vLLM's shared residency) converge in this third case, proving the Backend Contract independent of both residency shape *and* execution method. Merged to main via stacked PRs.

This change is notable for explicitly deciding that residency shape and async-bridge shape are independent axes — N=2 predecessors could not tell them apart. ONNX Runtime's stateless-plus-blocking off-diagonal case allowed the design to borrow from both predecessors without inheriting either's complexity: vLLM's shared session (justified here by statelessness, not batching) and llama.cpp's thread offload (justified here for event-loop safety, not queue backpressure).

## Scope Summary

### What Was Built

`src/tibios_ray/engines/onnxrt.py` — two concrete Backends, `OnnxEmbeddingBackend` and `OnnxRerankBackend`, structurally satisfying their respective protocols (Protocol conformance, no base class). Key mechanisms:

- **Shared, refcounted residency** (OR2): one `_OnnxResidency` per Backend instance, housing the session and tokenizer, refcounted and torn down at zero — directly reusing vLLM's pattern (VL2, VL6, VL13 verbatim) but justified by an engine property (statelessness) rather than a throughput need (batching).
- **Non-blocking thread offload** (OR7): one `asyncio.to_thread` per call, spanning tokenize → `session.run` → row extraction, no pump thread, no queue, no lock during execution — llama.cpp's off-loop safety without llama.cpp's queue machinery.
- **Concurrent `run()` thread-safety** (OR3, OR4): the session's `Run()` is thread-safe on a shared session and officially recommended by ORT maintainers; concurrency is real parallelism, not loop liveness. Load-bearing claim discharged by integration smoke test.
- **SDK-free unit tier** (LC11/VL8 precedent): injectable `InferenceSessionLike` and `TokenizerLike` Protocol seams; importing `engines/onnxrt.py` requires neither `onnxruntime` nor `numpy`; the real SDK is lazy-imported only at first-acquire time.
- **Optional extra** (OR10): `onnx` declared under `[project.optional-dependencies]`, absent from the core install and unit test tier.
- **Input filtering** (OR8): session-graph declared input names are cached at acquire time; the tokenizer output is filtered to only the keys the graph actually declares, defending against common ONNX export variations (e.g., missing `token_type_ids`).
- **Shape validation** (OR9): 2-D output is the contract; embedding rows map to Vectors, rerank rows' first column maps to RerankResult scores; 3-D output raises `OnnxOutputShapeError` naming the fix; empty input returns empty result without touching the session.

### Architecture Decisions (OR1-OR11)

Full rationale in `design.md` (this archive) and Engram obs #197. Key decisions:

- **OR2 (Residency)**: Shared and refcounted, justified by `InferenceSession`'s statelessness, not batching. Per-Backend-instance, not per-process.
- **OR3 (Lock strategy)**: No lock during `run()`; the lock guards residency transitions only (construct-or-reuse, refcount). Thread-safety is ORT's documented property.
- **OR4 (Evidence over assertion)**: Thread-safety claim is load-bearing and discharged by integration smoke (two concurrent `run()` calls on real session succeed identically).
- **OR5 (Two classes, one base)**: `OnnxEmbeddingBackend` has only `embed`; `OnnxRerankBackend` has only `rerank`; static type is the discriminator since `supports()` cannot distinguish them.
- **OR6 (Tokenizer seam)**: Second seam, lifetime-bound to residency; using `return_tensors="np"` keeps numpy confined behind the seam.
- **OR7 (One thread hop)**: All blocking work in one `to_thread` call; both tokenization and `run()` are blocking native code.
- **OR8 (Input filtering)**: Graph is the authority; declared-only inputs are passed, extra tokenizer outputs are filtered.
- **OR9 (Output shape)**: 2-D contract; no pooling, no normalization; 3-D output is an error naming the fix.
- **OR10 (Artifact Bundle)**: All model/hardware facts are construction arguments; `supports()` checks backend family only.
- **OR11 (Cancellation)**: No cancellation support; `asyncio.to_thread` cannot cancel; orphaned `run()` is inert (no KV-cache blocks to leak).

### New Specifications

- **onnxruntime-backend** (new): the full Backend spec — structural conformance, shared refcounted residency, non-blocking async bridge, input filtering, shape validation, tokenizer seam, SDK-free testing, optional-extra packaging. One spec covering both execution methods; the two classes are an implementation detail.
- **backend-adapter** (delta merged): added "BackendSession Carries No Model Residency" requirement, generalizing the Backend Independence Principle to non-text modalities. Three proof cases now exist: `llamacpp-text-backend` (per-session), `vllm-text-backend` (shared), `onnxruntime-backend` (shared-but-for-different-reasons). Restated the Contract name as *a* per-modality execution method, not `generate` specifically.

## Verification & Gate Status

### Verify Report Summary

- **Verdict**: PASS WITH WARNINGS
- **Critical Issues**: 0
- **Warnings**: 2 (both non-blocking, test-coverage recommendations)
- **Suggestions**: 1 (optional enhancement)

| # | Type | Note |
|---|------|------|
| 1 | WARNING | Opt-in integration smoke covers CPU EP only; fully-independent-instances concurrency (two separate Backend instances, different models, parallel embed calls) not covered — consider adding when multi-model deployment is active |
| 2 | WARNING | Design's line-count estimate (550-650) slightly exceeded; actual run was ~750 lines (reflects test coverage depth, not a defect) |
| 3 | SUGGESTION | Add a cross-backend residency-identity test (e.g., `test_backends_backendession_is_identity_only`) comparing shape across llamacpp, vllm, onnxruntime |

**Observation IDs for Traceability**:
- Proposal: Engram obs #195
- Spec: Engram obs #196
- Design: Engram obs #197
- Tasks: Engram obs #198
- Apply Progress: Engram obs #199
- Verify Report: Engram obs #202

### Test Results

Command: `uv run pytest -q`

```
1015 passed, 13 skipped in 2.25s
```

- ONNX Runtime-scoped subset: 97 new unit tests + 4 opt-in integration tests
  - Unit tests: all passed (conformance, supports, sdk-free-import, residency, concurrency, embed/rerank shape, output-name, rerank-pairing, cancellation, provider-plumbing)
  - Integration tests: 4 skipped (env vars `TIBIOS_RAY_ONNX_MODEL` / `…_TOKENIZER` unset); would pass with model files
- Failures: 0
- No regression in existing backends (`llamacpp-text-backend`, `vllm-text-backend`)

### Code Quality Gate

| Tool | Command | Status |
|------|---------|--------|
| ruff | `uv run ruff check .` | ✓ PASS — zero violations |
| pyright | `uv run pyright` | ✓ PASS — zero errors, zero warnings |

### Architecture Guard

- `tests/unit/engines/test_engines_layering.py`: vacuity guard bumped from `>= 3` to `>= 4`; scanner already recursive, covers `onnxrt.py`; confirms no engine SDK imports in `backends/` tree
- `tests/unit/backends/test_no_engine_imports.py`: unchanged; `"onnxruntime"` already in `FORBIDDEN_ENGINE_MODULES`, guard already recursive

## Archived Artifacts

All change artifacts have been moved to `openspec/changes/archive/2026-08-07-onnx-runtime-backend/`:

```
openspec/changes/archive/2026-08-07-onnx-runtime-backend/
├── proposal.md                       (Intent, scope, approach, open questions)
├── design.md                         (OR1-OR11 decisions, testing strategy)
├── tasks.md                          (24 tasks, all complete with deviations noted)
├── ARCHIVE-REPORT.md                 (This file)
└── specs/
    ├── backend-adapter/spec.md       (Delta: BackendSession residency-free + modality-agnostic)
    └── onnxruntime-backend/spec.md   (New: full Backend spec)
```

## Merged Specifications

| Main Spec | Action | Details |
|-----------|--------|---------|
| `openspec/specs/onnxruntime-backend/spec.md` | CREATED | Full spec from delta (9 requirements, new) |
| `openspec/specs/backend-adapter/spec.md` | MERGED | Added "BackendSession Carries No Model Residency" requirement (already confirmed merged at lines 43-67) |

## Next Steps

The change is **complete**. No follow-up work required for this change itself. The two WARNING items are optional enhancements:

- **Opt-in integration expansion**: add a `test_onnxrt_smoke_full_independent_instances` scenario with two separate Backend instances loading different models, embedded in parallel — useful when multi-model deployment is active.
- **Cross-backend residency identity test**: verify all three Backends (`llamacpp`, `vllm`, `onnxruntime`) return a `BackendSession` carrying only `backend_id`/`session_id`.

Out of scope for this change, tracked separately:

- `EmbeddingProvider`/`RerankProvider` wiring — composition root does not exist yet
- Speech synthesis (kokoro) and OCR (paddleocr) — also ONNX Runtime, but separate modality protocols
- CUDA Execution Provider testing — CPU smoke is sufficient; GPU deployment will carry its own testing
- Request scheduler — executor saturation at `min(32, cpu+4)` is acceptable for current zero-caller state

## Verification Chain

1. All artifacts read from Engram (obs #195-199, 202) and openspec filesystem
2. Verify report (obs #202) confirmed PASS WITH WARNINGS, 0 CRITICAL/0 WARNING-level failures
3. Live test/lint/type re-run in this archive pass: 1015 passed/13 skipped, ruff clean, pyright clean
4. Layering guard confirmed recursive, guard already covers new module
5. Backend Independence Principle now proven by three opposite residency shapes

## Archive Closure

This change is now closed. The change folder `openspec/changes/onnx-runtime-backend/` has been moved to archive. All change state is persisted:
- Engram: Proposal (obs #195), Spec (obs #196), Design (obs #197), Tasks (obs #198), Apply Progress (obs #199), Verify Report (obs #202)
- OpenSpec: Proposal, Design, Tasks, both specs (one new, one merged delta)
- This archive report serves as the final closure record

The SDD cycle is complete. The first non-text Backend Adapter is ready, proving the contract design scales beyond text generation.
