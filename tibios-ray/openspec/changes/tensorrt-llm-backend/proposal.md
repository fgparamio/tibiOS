# Proposal: TensorRT-LLM Text Backend (the third engine the contract already named)

## Intent

`backends/text.py`'s module docstring has said it since day one — `TextGenerationBackend` is "the Chat/Reasoning capability's engine-facing contract (llama.cpp, vLLM, TensorRT-LLM in Phase 4)". `catalog/entries/chat.py` and the frozen `CHAT_GENERATE_DESCRIPTOR.backends` table in the living `capability-providers` spec already commit `tensorrt_llm` as a legitimate backend for `chat.generate` on the large/high-VRAM tiers (Qwen3-32B, Llama-3.3-70B, DeepSeek-V3/R1, Kimi-K2). The advertisement is shipped and asserted-stable; the engine does not exist.

Today a deployment on matched NVIDIA hardware whose plan resolves to `tensorrt_llm` gets an absent-backend failure, because `worker.py::build_runtime()` can only ever put `llama_cpp`, `vllm`, and `onnxruntime` into the injected mapping. This change adds the third `TextGenerationBackend` implementation and wires it — nothing else. `provider-backend-composition` (archived) built every seam this needs; this change is the first proof that those seams generalize to a fourth `BackendId` without touching a Protocol, a Provider, or the selection mechanism.

Design decision numbering continues at **D30** (`provider-backend-composition` ended at D29).

## Core Principle: Engine Compilation Is a Provisioning Concern, Not a Runtime One

**TensorRT-LLM consumes precompiled engine artifacts. Engine compilation (`trtllm-build`) is an external provisioning concern and is outside the Runtime lifecycle.**

This is continuous with the two engines already shipped, not a new kind of concern. `LlamaCppConfig.model_path` points at an already-quantized GGUF. `VllmConfig.model` points at an already-prepared model. `TensorrtLlmConfig` will point at an already-compiled engine artifact. Same shape, same reasoning as D23/D19 — *the artifact IS its quantization*: the choice was made out of band, at artifact-production time, and the Worker's only job is to consume what it was handed.

D27 makes this structural rather than stylistic. "Startup viability validation = eager construction" means whatever `build_runtime()` does at boot is what an operator waits for. A `trtllm-build` inside the Composition Root — 10 to 90 minutes per (model, GPU, dtype) combination, non-portable across GPUs — would convert a boot-time check into a multi-hour outage. The Worker consumes artifacts; it never produces them.

## Operational Model

1. Engine artifacts are **precompiled**.
2. The Runtime **never** invokes `trtllm-build` or any compilation step.
3. A missing or incompatible engine artifact is reported as a **configuration/wiring error** — never recovered dynamically, never built on demand.

**Illustrative operator flow** (not a spec requirement — the exact tooling is the operator's choice; this is what the three invariants above mean in practice for whoever provisions a TibiOS deployment — a person installing a TibiBox, an ops team, or a Docker Compose / Ansible / Kubernetes pipeline):

```
download model → trtllm-build → TensorRT engine artifact
    → copy engine to the host → set TIBIOS_RAY_TENSORRT_ENGINE_PATH
    → start tibios-ray
```

`worker.py::build_runtime()` then does nothing more than `TensorrtLlmConfig(engine_path=...)` → `TensorrtLlmTextBackend(...)`: it opens an artifact that already exists. It never runs `trtllm-build`. This is the same reason a `llama.cpp` deployment can start instantly from a GGUF while a TensorRT-LLM deployment's *build* step (potentially the better part of an hour) happens once, out of band, before the Worker's lifecycle even begins — not on every boot.

## Scope

### In Scope

- **`engines/tensorrt.py`**: one class satisfying the *existing* `backends/text.py::TextGenerationBackend` Protocol structurally — no new Protocol, no base class (D1), a sibling of `llamacpp.py` and `vllm.py`.
- **vLLM's residency shape, not llama.cpp's**: a single lazily-constructed, refcounted engine instance shared across sessions, natively-async streaming, no thread bridge. TensorRT-LLM's `LLM.generate_async(..., streaming=True)` is architecturally `AsyncLLM`, not a pool of blocking `Llama` objects.
- **`TensorrtLlmConfig` in `config.py`** mirroring `VllmConfig`'s single-field shape (an engine-artifact path), env-sourced under the existing `TIBIOS_RAY_*` convention. Absent → `None` → engine not built → capability unwired, never a crash.
- **One `worker.py` composition line** plus one new entry in `_BACKEND_PREFERENCE`. No new selection mechanism: `PreferenceOrderPolicy` already generalizes to N backends.
- **The SDK-free test posture, unchanged**: lazy `importlib` seam (LC11/VL8), injectable structural Protocols for the SDK surface, a `testing/` fake, and an opt-in `tests/integration/test_tensorrt_smoke.py` mirroring `test_vllm_smoke.py`. The unit tier requires no CUDA and no extra installed.
- **`pyproject.toml`** optional extra, and the `engines/__init__.py` re-export (API aliasing, explicitly non-violating per D29).
- A new living spec, `tensorrt-llm-text-backend`, mirroring `vllm-text-backend`.

### Out of Scope

- **Engine compilation.** `trtllm-build` and the `LLM(model=hf_checkpoint)` JIT-build path are both excluded — see the Core Principle above. This is the load-bearing cut, not a convenience one.
- **Distributed / multi-GPU / multi-node serving** (tensor or pipeline parallelism). Single-GPU only, matching the repo's single-process-per-Worker shape; neither existing text engine has a config surface for it either.
- **`embedding.generate` / `rerank.documents`.** `tensorrt_llm` appears in neither catalog, and `TextGenerationBackend` is chat-only by shape (`TextRequest`/`TextChunk`).
- **`vision.understand`.** `tensorrt_llm` *is* in the vision descriptor, but `VisionProvider` is entirely unwired: no `backends/vision.py` Protocol exists. That prerequisite predates and is independent of TensorRT-LLM. In scope for a future change once vision wiring exists.
- **Quantization runtime selection.** Same accepted D23 limitation as both existing engines: `ServingPlanLike` exposes only `.backend`.
- **Pool-based concurrency** (llama.cpp's shape). If any concurrency strategy beyond the shared refcounted engine is needed, that is a design-phase finding, not an assumed inheritance.
- **Any change to `capabilities/`, `backends/`, `selection/`, `runtime/`, `transport/`, or `../proto/`.** `ChatProvider.execute()` requires zero code changes — confirmed by reading its full body: it holds no backend-specific branching.
- **A Model Catalog / `ModelArtifact` domain.** `TensorrtLlmConfig.engine_path` is one more hardcoded single-path field, exactly like `LlamaCppConfig.model_path` and `VllmConfig.model` today — a config surface, not a catalog. A future domain that maps `ModelId → ModelArtifact → compatible backend → physical path`, letting `ModelSelectionPolicy` return a `ServingPlan` carrying both `backend` and `artifact` instead of relying on one hardcoded path per engine in `config.py`, is a plausible and likely-valuable evolution once TibiBox needs to manage many installed models uniformly — but it is a separate domain with a separate responsibility (`TensorRT-LLM` knows how to run an engine; a Model Catalog knows what models exist and where) and does not belong in this change.

## Capabilities

### New Capabilities

- `tensorrt-llm-text-backend`: structural conformance to `TextGenerationBackend`; shared refcounted residency and its teardown; native-async streaming; cancellation; the injectable SDK seam; the optional extra; and the Operational Model's three invariants as testable requirements (notably: a missing or incompatible engine artifact surfaces as a configuration/wiring failure, never a build).

### Modified Capabilities

**None.** `provider-backend-composition`, `worker-configuration`, and `model-selection-policy` are engine-agnostic by construction and already quantify over N backends; `capability-providers`' frozen descriptor table already lists `tensorrt_llm` for `chat.generate`. This change *exercises* those requirements — it does not alter any of them. That is the evidence that `provider-backend-composition` got the seams right.

## Approach

Pattern-match `engines/vllm.py` end to end. Define module-local structural Protocols for the SDK surface (`LLMLike`, `RequestOutputLike`) so unit tests never import `tensorrt_llm`; construct the real SDK behind a `default_engine_factory` using `importlib.import_module` with the same actionable `ModuleNotFoundError` message the other two engines raise. `supports()` is a backend-family identity check (LC12/VL4), never selection. `acquire()`/`release()` drive a refcounted `_ModelRuntime` under a lock that guards residency transitions only, never `generate()`. `generate()` is a bare `async for` over the SDK stream, emitting `TextChunk`s.

`config.py` gains `TensorrtLlmConfig` and one `_tensorrt_config()` parser; `worker.py` gains one `if config.tensorrt_llm is not None:` branch and one `_BACKEND_PREFERENCE` entry. Layering is unchanged and already legal: `engines/` imports only from `tibios_ray.backends` (enforced by `tests/unit/engines/test_engines_layering.py`'s AST scan).

Strict TDD throughout (`uv run pytest`).

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `src/tibios_ray/engines/tensorrt.py` | New | The third `TextGenerationBackend` implementation |
| `src/tibios_ray/engines/__init__.py` | Modified | Re-export the class + `TENSORRT_LLM_BACKEND_ID` (aliasing, D29) |
| `src/tibios_ray/config.py` | Modified | `TensorrtLlmConfig` + one `WorkerConfig` field + parser |
| `src/tibios_ray/worker.py` | Modified | One composition branch; one `_BACKEND_PREFERENCE` entry |
| `src/tibios_ray/testing/` | Modified | Stub SDK double, mirroring `StubAsyncLLM` |
| `tests/unit/engines/test_tensorrt.py` | New | SDK-free unit tier |
| `tests/integration/test_tensorrt_smoke.py` | New | Opt-in, real-SDK, skipped unless the engine-artifact env var is set |
| `tests/unit/{config,test_worker}.py` | Modified | New config slot; new preference entry; construction-scan guard |
| `pyproject.toml` | Modified | Optional extra + version pin |
| `openspec/specs/tensorrt-llm-text-backend/spec.md` | New | Living spec |
| `src/tibios_ray/{capabilities,backends,selection,runtime,transport}/**` | Untouched | Contracts and Providers unchanged — the point of the change |

## Open Design Questions

For `sdd-design`. Continue design-decision numbering at **D30**.

1. **Preference ranking of `tensorrt_llm` relative to `vllm` in `_BACKEND_PREFERENCE` — deliberately unresolved here.** Both sides are real. *For TensorRT-LLM first*: best per-token latency and throughput on matched NVIDIA hardware, and the engine artifact is already hardware-optimized for exactly that box — an operator who went to the trouble of compiling one has declared intent. *For vLLM first*: broader hardware compatibility, materially less operational friction, no engine-build step, and continuous batching that degrades more gracefully under concurrent load. D28 established that this tuple is a *deployment belief* expressed by the Composition Root, which is precisely why it deserves an explicit D-numbered decision rather than a default. Also open: whether the order should become operator-configurable at all.
2. **Delta vs. cumulative token semantics.** vLLM needed an explicit `RequestOutputKind.DELTA` (VL9) to avoid O(n²) concatenation. Whether TensorRT-LLM's per-iteration `output.outputs[0].text` is incremental or cumulative is unverified and is a correctness question, not a tuning knob.
3. **Extra name and version pin** in `[project.optional-dependencies]`, downstream of Risks A and B below.

## Risks

Risks A and B are **design-phase risks, not proposal blockers** — they gate `sdd-design`'s conclusions, not this proposal's validity. Neither is softened into an assumption here.

| Risk | Likelihood | Mitigation |
|---|---|---|
| **A — Python version.** TensorRT-LLM's documented baseline is Python 3.10; this repo is `requires-python = ">=3.14"`. Actual wheel/interpreter support must be *verified*, not inferred from docs, before `sdd-design` commits to a `python_version` marker strategy (mirroring vLLM's existing `python_version < '3.14'` marker, which exists for exactly this class of problem) or to a different isolation approach entirely. | High | Verification spike gates `sdd-design`; the fallback shape (marker-gated extra, unit tier unaffected) is already proven by the `vllm` extra |
| **B — Installability, framed correctly.** The architectural question is *not* "does `pip install` work". It is: **can an operator install TensorRT-LLM without turning the Worker into a compilation environment?** If official prebuilt wheels (e.g. via `pypi.nvidia.com`) suffice, proceed exactly as with `vllm`/`llamacpp` — a lazy-`importlib` optional extra. If they do not, and a source build or full engine-build toolchain is required in-process, then `sdd-design` likely needs containerization or a separate provisioning process, because an in-Worker source build violates the Operational Model above. | Med | Resolve before the extra is pinned; the answer selects between two different deployment shapes, and Invariant 2 is the acceptance test either way |
| CI/unit tier acquires a CUDA or SDK dependency | Med | Structural SDK Protocols + `importlib` seam + `testing/` fake, exactly as `vllm.py` does; integration smoke test stays opt-in and skipped by default |
| The engine grows a build/convert escape hatch under operational pressure | Med | Operational Model invariant 2 becomes a spec requirement with a scenario asserting no compilation entry point exists |
| Preference-order change silently reroutes existing vLLM deployments | Med | Q1 is an explicit D-numbered decision with a test asserting the resolved order |
| The construction-scan guard trips on the new engine | Low | One `worker.py` branch; the `engines/__init__.py` re-export is already carved out by D29 |

## Rollback Plan

Almost purely additive. `engines/tensorrt.py`, its tests, its spec, and its `testing/` double are new files — deleting them is a clean removal. The `config.py` dataclass and field, the `engines/__init__.py` re-export, the `pyproject.toml` extra, and the `worker.py` composition branch are each single-hunk reverts. The **only** non-additive edit in the entire change is the `_BACKEND_PREFERENCE` tuple; reverting it restores `(vllm, llama_cpp, onnxruntime)` exactly. No Protocol, no Provider, no existing engine, and nothing in `runtime/` or `transport/` is touched, so nothing downstream can regress.

## Dependencies

- `provider-backend-composition` (archived) — the Composition Root, `PreferenceOrderPolicy`, `WorkerConfig`, and the wired `ChatProvider`. **Satisfied.**
- ADR-0001 through ADR-0004 — all Accepted; axioms here, not re-justified. **Satisfied.**
- `backends/text.py::TextGenerationBackend` — shipped, unmodified, and explicitly anticipates this engine. **Satisfied.**
- **External, deliberately unsatisfied and out of band**: an NVIDIA GPU, CUDA ≥12.2, and a **precompiled engine artifact** produced by the operator. Per the Operational Model, this change consumes that artifact and never produces it.
- No cross-repo coordination: `../proto/` and `tibios-core` are untouched.

## Delivery

Estimated **~700–950 hand-written lines** (`engines/vllm.py` is 374 lines and its unit tier is larger still) — over the 400-line review budget, so **chained PRs are expected**. The natural split is the one `vllm.py`'s own docstring records for its predecessor: **PR 1** — config slot + Model Runtime and residency seam (`backend_id`, `supports`, `acquire`, `release`) + SDK stub; **PR 2** — native-async `generate()`, cancellation/finalize, Composition Root wiring, `_BACKEND_PREFERENCE` decision, and the extra. `sdd-tasks` owns the final split and MUST emit the Review Workload Forecast.

## Success Criteria

- [ ] A `chat.generate` execution against a configured TensorRT-LLM engine artifact streams `OutputChunk`s and returns a `COMPLETED` `ExecutionReport`
- [ ] `capabilities/chat.py` has zero diff — the new backend is reachable purely through the injected mapping
- [ ] `backends/text.py` has zero diff — no Protocol change was required
- [ ] The Runtime contains no call path to `trtllm-build` or any compilation/conversion step, asserted by test
- [ ] A missing or incompatible engine artifact surfaces as a configuration/wiring failure — never a build, never a dynamic recovery
- [ ] With `TIBIOS_RAY_TENSORRT_*` unset, the Worker starts normally and `tensorrt_llm` is simply absent from the injected mapping
- [ ] The unit tier passes with neither `tensorrt_llm` nor CUDA installed; the integration smoke test skips by default
- [ ] `worker.py` remains the only module constructing the new engine; the `engines/` layering scan still finds zero violations
- [ ] The `_BACKEND_PREFERENCE` order is a recorded D-numbered decision with a test asserting it
- [ ] `uv run pytest` / `ruff check` / `pyright` pass
