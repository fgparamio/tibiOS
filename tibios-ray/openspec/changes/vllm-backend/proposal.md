# Proposal: The vLLM Text Generation Backend

## Intent

`llamacpp-backend` (archived) proved the engine-agnostic contract survives contact with **one** SDK. One adapter cannot prove a contract is engine-agnostic — it can only prove it fits llama.cpp. The catalog already advertises `BackendId("vllm")` for Kimi K3, DeepSeek R1, Qwen 3, Llama 4, Gemma and Mistral (`catalog/entries/{chat,vision}.py`) and cannot serve a token. This change delivers the **second** concrete adapter, chosen because vLLM's residency shape is structurally *opposite* to llama.cpp's — which is exactly what makes it a real test of the contract rather than a copy of it.

## The architectural decision

llama.cpp's shape is `Session → Model Instance → Generator`: one dedicated `Llama` per `acquire()`, locked during generation. vLLM's shape is `GPU → AsyncLLM → Continuous Batching → {Session A, B, C}`. Mirroring llamacpp literally — one `AsyncLLM` per `acquire()` — would duplicate the model in VRAM per session and defeat continuous batching, converting vLLM into something that stops being vLLM. **What Backends share is the contract, not the implementation.** We adopt a shared, refcounted engine instance and name the layer that holds it:

```
Backend        (the contract: supports / acquire / generate / release)
  ↓
Model Runtime  (shared; owns model residency and reuse)
  ↓
BackendSession (one execution context)
  ↓
Token Stream
```

Principle: **a BackendSession does not own model residency; it owns an execution context. Residency is an implementation detail of each Backend.**

### Where that principle lives — decided: split

| Piece | Home | Why |
|---|---|---|
| The invariant (`BackendSession` carries no residency) | **`backend-adapter` delta** | It constrains `BackendSession`, a type `vllm-backend` does not own. It already binds `llamacpp-text-backend` (its `_Residency` side table). A rule governing two capabilities belongs to the shared contract, not one of them. Verified non-breaking: `BackendSession` is already `{backend_id, session_id}` — spec-level formalization, zero code change. Precedent: `llamacpp-backend` promoted the engine-agnostic requirement from Phase-1 phrasing to permanent the same way. |
| The **Model Runtime** layer itself | **`vllm-text-backend` spec + design** | Generalizing a named mechanism from N=2 is the trap the user warned about ("llama.cpp works this way, therefore all Engines must"). Described generally enough to be reused by TensorRT-LLM/SGLang, but *permitted*, not *mandated*. |

Promote the invariant. Do not promote the mechanism.

Note: the phrase "`acquire/generate/release/health`" names a `health()` the contract does not have today (`BackendAdapter` = `backend_id/supports/acquire/release` + per-modality `generate`). Adding it is a separate contract change — out of scope here.

## Scope

### In Scope

- `src/tibios_ray/engines/vllm.py` — `VllmTextBackend`, structurally satisfying `TextGenerationBackend`; `engines/__init__.py` re-exports.
- Shared **Model Runtime**: one lazily-constructed engine, refcounted across sessions; single-flight construction; shutdown when the last session releases.
- Native-async `generate()`: `AsyncLLM.generate()` is already an `AsyncGenerator` and `output.finished` maps directly to `TextChunk.finished`. The llamacpp thread bridge (pump `Thread`, bounded queue, `threading.Event`, one-token lookahead) is **explicitly not reused** — confirmed by exploration, not assumed.
- Uniform cancellation: abandonment/cancel drives an explicit engine-level abort in `finally`, never generator GC. Upstream v0/v1 inconsistency (vllm#20362, vllm#24584) is **Known Engine Behavior**, absorbed by the Backend — the Worker's cancellation semantics never vary by engine version.
- Injectable `AsyncLLMLike` Protocol + lazy SDK import (LC11 precedent): the unit tier runs with no `vllm`, no torch, no CUDA, no GPU.
- `vllm` optional extra in `pyproject.toml`; one opt-in GPU integration smoke test, env-var/GPU gated (opt-in-GGUF precedent).

### Out of Scope

- **`ChatProvider`/`VisionProvider` wiring** — same deferral as `llamacpp-backend`: no composition root exists, `worker.py` still blocked pending tibios-core's `capability` field work. Tracked separately.
- **Multi-model residency/eviction policy** — this change is *one* Model Runtime correctly shared across sessions of *the same* model. A GPU-budget eviction manager across different models is a larger, separate concern.
- TensorRT-LLM / SGLang adapters · a `health()` contract method · tensor/pipeline-parallel and GPU-memory tuning policy · non-text vLLM modalities.
- `tests/unit/backends/test_no_engine_imports.py` — **no change needed**: `"vllm"` is already in `FORBIDDEN_ENGINE_MODULES` and the guard is already recursive.

## Capabilities

### New Capabilities

- `vllm-text-backend`: the Model Runtime layer, refcounted residency lifecycle, native-async streaming, uniform cancellation over Known Engine Behavior, SDK-free testability, optional-extra packaging.

### Modified Capabilities

- `backend-adapter`: add a durable requirement — a `BackendSession` is an opaque execution-context handle and MUST NOT carry model residency; residency shape is each Backend's private choice. Formalization only; no field or code change.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `src/tibios_ray/engines/vllm.py` | New | Backend + Model Runtime + `AsyncLLMLike` seam |
| `src/tibios_ray/engines/__init__.py` | Modified | Re-exports |
| `pyproject.toml` | Modified | `vllm` optional extra |
| `tests/unit/engines/test_vllm_*.py` | New | Refcount, streaming, cancellation, SDK-free import |
| `tests/integration/**` | New | Opt-in GPU smoke |
| `src/tibios_ray/backends/adapter.py` | Untouched | Delta is spec-level; fields already comply |
| `src/tibios_ray/capabilities/*` | Untouched | Providers still raise `NoBackendAvailableError` |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Refcount leak — a lost `release()` pins the model in VRAM forever | High | `release()` authoritative and idempotent-by-rejection (`UnknownSessionError`, LC2); test that refcount→0 shuts the runtime down |
| Concurrent first `acquire()` builds two engines (double VRAM) | High | Single-flight async lock around construction; design MUST specify it, test with concurrent acquires |
| v0/v1 cancellation inconsistency leaks to the Worker | Med | Explicit abort in `finally`; test abandonment mid-stream on the stub; documented as Known Engine Behavior |
| Stub diverges from the real `AsyncLLM` signature | Med | Opt-in GPU integration test is the only thing that catches it — keep it runnable |
| `vllm` wheel is GB-scale, CUDA/torch-pinned | High | Optional extra + lazy import; harder than llamacpp (torch import alone is slow) — unit tier must never touch it |
| Sharing one engine couples sessions (head-of-line, OOM) | Med | Accepted for this change; multi-model residency policy is explicitly out of scope |
| Over-generalizing Model Runtime from N=2 | Med | Layer stays descriptive in `vllm-text-backend`; only the invariant is promoted to `backend-adapter` |

## Rollback Plan

Additive except two edits (`pyproject.toml` extra, `engines/__init__.py` re-exports) and one spec formalization. No contract fields, Provider, or runtime behavior change — Providers raise `NoBackendAvailableError` before and after, and `llamacpp-text-backend` is untouched. `git revert` of the slice commits restores the archived `llamacpp-backend` state exactly.

## Delivery

Estimated ~450–550 changed lines — **over the 400-line budget**. Chained PRs by work unit:

1. Model Runtime + refcounted `acquire`/`release` + `backend_id`/`supports` + `AsyncLLMLike` seam + optional extra + `backend-adapter` delta.
2. Native-async `generate()` streaming + uniform cancellation/abort + opt-in GPU integration smoke.

## Dependencies

- `llamacpp-backend`, `capability-providers`, `model-catalog` (archived) — **satisfied**.
- `proto-worker-contract` (sibling) — **not blocking**; only composition needs it.

## Success Criteria

- [ ] `VllmTextBackend` satisfies `TextGenerationBackend` (pyright-verified, no base class)
- [ ] Unit suite passes with `vllm`, torch and CUDA **absent** — no GPU, no weights, no network
- [ ] N concurrent sessions of the same model share **exactly one** engine instance; concurrent first-acquire builds one, not two
- [ ] Releasing the last session shuts the Model Runtime down; releasing a non-last session does not
- [ ] `generate()` streams without buffering, exactly one `finished=True` terminal chunk, `finished` sourced from `output.finished`
- [ ] Abandoning a stream mid-flight issues an explicit engine abort and drops that session's refcount correctly
- [ ] `backends/` imports no engine SDK under recursive inspection (guard unchanged)
- [ ] `backend-adapter` spec states the residency invariant; `llamacpp-text-backend` still passes unchanged
- [ ] Opt-in GPU integration smoke passes on a real vLLM install when enabled
