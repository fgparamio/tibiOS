# Proposal: The llama.cpp Text Generation Backend

## Intent

`capability-providers` (archived) made the capability catalog truthful but inert: all seven Providers raise `NoBackendAvailableError`, and `backend-adapter` froze `TextGenerationBackend` with **zero implementations**. tibios-ray advertises `chat.generate` with `streaming=True` and `BackendId("llama_cpp")` and cannot execute a single token. This change (roadmap Phase 4) delivers the **first concrete Backend Adapter** — proving the engine-agnostic contract survives contact with a real SDK.

## Scope

### In Scope

- New package `src/tibios_ray/engines/`, module `llamacpp.py`, class `LlamaCppTextBackend` satisfying `TextGenerationBackend` structurally.
- Residency: `acquire`/`release` construct/free one `Llama` per `BackendSession`; `supports(plan)` is `plan.backend == BackendId("llama_cpp")` **only** (see GGUF debt).
- Real streaming `generate() -> AsyncIterator[TextChunk]` — per-token, never buffered; `max_tokens`, `temperature`, `stop` mapped through; `finished=True` on the terminal chunk.
- One `asyncio.Lock` per session, held for the **whole generator lifetime** and released on exhaustion, `aclose()`, or cancellation.
- Injectable `Llama` factory seam + local structural `LlamaLike` Protocol, so unit tests stub the SDK entirely (`RecordingBackend` / `FakeTextBackend` precedent). SDK imported **lazily inside the default factory** — importing the module never requires `llama_cpp`.
- `llama-cpp-python>=0.3.34,<0.4` as an **optional extra** (`[project.optional-dependencies] llamacpp`), not a core dependency: CI's unit tier must not compile C++.
- Strengthen `tests/unit/backends/test_no_engine_imports.py` from `glob` to `rglob` — a non-recursive glob would silently permit `backends/engines/`.
- One opt-in integration test, skipped unless a real tiny GGUF path is supplied via env var. Zero CI cost; closes the "the stub could be lying about the SDK call signature" gap.

### Out of Scope

**Wiring `ChatProvider` — decided, deferred.** CP1 made `ChatProvider` a zero-field slotted dataclass *precisely so* "holds no backend" is a language guarantee. Reversing it means a new field, a construction/composition story (nothing composes Providers yet — `worker.py` is still blocked on `proto-worker-contract`), `ExecutionContext` → `TextRequest` translation, and Channel emission per chunk. Bundling that here would double review size and couple a *provably-correct-in-isolation* adapter to an unresolved composition question. Follow-up: `chat-provider-wiring`.

Also out: GGUF resolution from `ResolvedModelRef` · non-text llama.cpp modalities (embeddings, multimodal) · vLLM/TensorRT-LLM/ONNX adapters · a session pool · tool-calling, JSON mode, reasoning traces (advertised flags, not this change) · GPU layer/`n_ctx` tuning policy.

## Capabilities

### New Capabilities

- `llamacpp-text-backend`: residency lifecycle, streaming semantics, serialization under concurrency, and the engine-isolation boundary for the first concrete adapter.

### Modified Capabilities

- `backend-adapter`: its engine-agnostic requirement is phrased as a **Phase 1** prohibition on "any concrete backend implementation". This change makes that false. The requirement must be restated durably — the `backends/` *tree* never imports an engine SDK; concrete adapters live outside it — plus a scenario asserting the recursive guard.

## Approach

`backends/` is the **contract** package; `engines/` is the **SDK-bound** package. That split (not `backends/engines/`) makes the guard trivially honest and preserves the layer direction `runtime -> capabilities -> selection -> backends`, with `engines -> backends` and nothing depending on `engines/` until composition exists. Module named `llamacpp.py`, not `llama_cpp.py`, to avoid shadowing the SDK's own name. Strict TDD throughout — the injectable seam exists so a test can drive every path without weights.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `src/tibios_ray/engines/{__init__,llamacpp}.py` | New | Adapter + `LlamaLike` seam |
| `pyproject.toml` | Modified | `llamacpp` optional extra |
| `tests/unit/backends/test_no_engine_imports.py` | Modified | `glob` -> `rglob` |
| `tests/unit/engines/**` | New | Residency, streaming, concurrency, cancellation |
| `tests/integration/**` | New | Opt-in real-GGUF smoke |
| `src/tibios_ray/capabilities/chat.py` | Untouched | CP1 preserved; see Out of Scope |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `Llama` is not thread-safe/reentrant | High | Per-session lock; `sdd-design` MUST specify an explicit interleaved-concurrency test, not just a docstring |
| `create_completion(stream=True)` is a **blocking** sync generator — pulling it inline stalls the event loop | High | Design must pick a thread-bridge (per-token `to_thread` vs producer thread + queue) and prove non-blocking by test |
| Lock leak if a consumer abandons the stream mid-flight | Med | Release in the generator's `finally`; test early-`aclose()` |
| Stubbed seam diverges from the real SDK signature | Med | Opt-in integration test is the only thing that catches this — keep it runnable, not rotting |
| GGUF path is out-of-band, so `supports()` cannot verify the model | Med | Accepted debt, documented in-module (`ray-worker-runtime` precedent: `ExecutionContext` enrichment deferred pending tibios-core) |
| `llama-cpp-python` build friction on Python 3.14 | Med | Optional extra — core install and CI unit tier stay unaffected; verify version in apply |

## Rollback Plan

Additive except two edits (`pyproject.toml` extra, guard `glob`->`rglob`). No Provider, contract, or runtime behavior changes — `ChatProvider` still raises `NoBackendAvailableError` before and after. `git revert` of the slice commits restores the archived `model-catalog` state exactly.

## Delivery

`auto-chain`. Estimated ~700 changed lines — **over the 400-line budget**, so chained PRs by work unit:

1. `engines/` package, `LlamaLike` seam, residency (`backend_id`/`supports`/`acquire`/`release`), recursive guard, optional extra.
2. Streaming `generate()` + thread bridge + chunk/stop-sequence mapping.
3. Concurrency serialization, cancellation/abandon release, opt-in integration test.

## Dependencies

- `capability-providers`, `model-catalog` (archived, merged) — **satisfied**.
- `proto-worker-contract` (sibling) — **not blocking**; only composition needs it.

## Success Criteria

- [ ] `LlamaCppTextBackend` satisfies `TextGenerationBackend` (pyright-verified, no base class)
- [ ] Unit suite passes with `llama_cpp` **not installed** — no weights, no network
- [ ] `generate()` yields more than one chunk for a multi-token stub completion (proves no buffering) and exactly one `finished=True` terminal chunk
- [ ] Two concurrent `generate()` calls on one session are provably serialized, never interleaved
- [ ] Abandoning a stream mid-flight releases the lock and stops the underlying generator
- [ ] `backends/` tree imports no engine SDK under recursive inspection
- [ ] `ChatProvider` still raises `NoBackendAvailableError`; no field added
- [ ] Opt-in integration test passes against a real tiny GGUF when a path is supplied
