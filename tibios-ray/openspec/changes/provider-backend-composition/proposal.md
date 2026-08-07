# Proposal: Provider-Backend Composition (the wiring the Providers were built to wait for)

## Intent

Every Capability Provider in `src/tibios_ray/capabilities/` is a zero-field frozen dataclass whose `execute()` unconditionally raises `NoBackendAvailableError`. Meanwhile `engines/` holds three working Backend Adapters (`LlamaCppTextBackend`, `VllmTextBackend`, `OnnxEmbeddingBackend`/`OnnxRerankBackend`), `selection/policy.py` holds a `ModelSelectionPolicy` Protocol, and `worker.py::build_runtime()` — a Composition Root that already exists — constructs all seven Providers **zero-arg**. The pieces are all built and none of them are connected: tibios-ray can accept a gRPC `SubmitJob` end-to-end and can only ever answer `FAILED`.

This change implements [ADR-0001](../../../docs/adr/0001-provider-backend-composition.md) (Backends constructed once at startup, owned by the Composition Root, never by a Provider), [ADR-0002](../../../docs/adr/0002-provider-backend-selection-delegation.md) (Providers delegate backend *selection* to an injected `ModelSelectionPolicy`), [ADR-0003](../../../docs/adr/0003-backend-resource-ownership.md) (resource ownership vs. Backend-internal concurrency strategy), and [ADR-0004](../../../docs/adr/0004-capability-request-boundary.md) (typed per-capability Requests decode `execution_parameters`, never the Provider or Backend) for the capabilities that actually have something to dispatch to. These four ADRs are axioms for this change — `spec.md` and `design.md` reference them, they do not re-justify them.

## Scope

### In Scope

- **Three capabilities only: `chat.generate`, `embedding.generate`, `rerank.documents`.** Each is injected with `backends: Mapping[BackendId, <capability Protocol>]` and `selection_policy: ModelSelectionPolicy`; each `execute()` performs the ADR-0002 flow instead of raising.
- **A concrete `ModelSelectionPolicy` implementation.** `selection/policy.py` defines the Protocol and *nothing implements it* — the Composition Root cannot inject a Protocol. A minimal, deterministic, non-scoring policy is net-new work this change owns.
- **A configuration surface** (`config.py`, env vars in `server.py`'s existing `os.environ.get` style) supplying per-backend artifact paths. Its *only* consumer is the Composition Root, deciding which concrete engines get built.
- **`worker.py::build_runtime()` becomes a real Composition Root**: builds engines from config, assembles the per-capability mappings, injects them plus the policy. It stays the only module naming a concrete engine class.
- **Absent config is a first-class outcome**, not a crash: an engine whose artifacts are unconfigured is not built, its `BackendId` is absent from the mapping, and that Provider still fails — honestly, at request time.
- Rewriting the conformance tests that assert the inverted invariant (see Test Impact).

### Out of Scope

- **`vision.understand`, `speech.transcribe`, `speech.synthesize`, `ocr.extract`.** They stay zero-field and keep raising `NoBackendAvailableError`. **This is a deliberate cut, not an oversight**: `backends/` has no execution Protocol at all for vision, OCR, or synthesis, and `engines/` has no concrete adapter for *any* of the four (`faster_whisper`, `tensorrt_llm`, and every vision/OCR/TTS engine are advertised in descriptors and implemented nowhere). Wiring them means net-new Protocol design plus net-new SDK integration per capability — work that is about *engines*, not about *composition*, and that would triple this change's blast radius. Each gets its own change once its Protocol and engine exist.
- Any change to `runtime/`. `WorkerRuntime._dispatch` already catches any `Exception` from `provider.execute()` and converts it to a `FAILED` report — the error path this change needs already exists.
- Any change to `transport/`, `../proto/`, or the engine implementations themselves.
- Model artifact *distribution* (download, cache, `ResolvedModelRef` → filesystem path resolution). `LlamaCppTextBackend`'s `model_path`-at-construction limitation is accepted debt, documented in `llamacpp-text-backend`; this change consumes it, it does not repay it.

## Capabilities

### New Capabilities

- `provider-backend-composition`: the injection shape (immutable `Mapping[BackendId, …]` + one `ModelSelectionPolicy`, both Composition-Root outputs), the Composition Root's exclusive ownership of concrete engine classes, and the per-request dispatch flow for the three wired capabilities.
- `worker-configuration`: the env-var surface, its reject-don't-guess parsing, and the rule that unconfigured artifacts yield an unwired capability rather than a startup crash or a fabricated backend.

### Modified Capabilities

- `capability-providers`: three requirements change. "Uniform No-Backend Execution Failure" stops being uniform — it must split into *wired* (chat/embedding/rerank: dispatches; fails only when the mapping is empty or the plan names an absent backend) and *unwired* (the other four: unconditional). "Providers hold no backend reference" must narrow to *constructs, discovers, or mutates* no backend — holding an injected immutable mapping is now required. The no-branching AST scan must be scoped to the four unwired modules.
- `model-selection-policy`: gains a concrete implementation requirement and the rejection rule for a `ServingPlan.backend` absent from `ServingConstraints.available_backends`. Today the spec constrains a Protocol nobody implements.

## Approach

Per ADR-0002, each wired Provider's `execute()`:

1. picks a `ResolvedModelRef` from `context.dependencies` (a **tuple**, not a keyed map — see Q2)
2. builds `ServingConstraints(available_backends=frozenset(self._backends))`
3. `plan = self._selection_policy.plan(model, constraints)`
4. `backend = self._backends[plan.backend]` — a fixed injected dict lookup, not a registry, not a service locator
5. `await backend.acquire(plan)` → capability method (`generate` / `embed` / `rerank`) → `release(session)` in a `finally`
6. streams results onto `context.channel` as `OutputChunk`s, terminated by `EndOfStream`, polling `context.cancellation` cooperatively
7. returns an `ExecutionReport` — never carrying application output (`18-worker-model.md`)

Providers contain **no selection logic** — no scoring, no capability matching, no backend branching. The only conditionals a Provider gains are dispatch-mechanical (empty mapping, unknown `plan.backend`, cancellation), and every one raises or terminates rather than choosing a backend.

Layering is unchanged and already legal: `capabilities/ -> selection/ -> backends/`, with injection arriving from `worker.py`. `capabilities/` still imports nothing from `runtime/`.

Strict TDD throughout (`uv run pytest`). Continue design-decision numbering at **D18** (`worker-context-wiring` ended at D17).

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `src/tibios_ray/capabilities/{chat,embedding,rerank}.py` | Modified | Two injected fields each; real `execute()` |
| `src/tibios_ray/capabilities/{vision,speech,ocr}.py` | Untouched | Deliberately still unwired |
| `src/tibios_ray/selection/policy.py` (+ new module) | Modified/New | First concrete `ModelSelectionPolicy` |
| `src/tibios_ray/config.py` | New | Env-var surface for engine artifacts |
| `src/tibios_ray/worker.py` | Modified | Real Composition Root: builds engines, injects mappings |
| `src/tibios_ray/testing/` | Modified | Fake backends + fake policy for Provider tests |
| `tests/unit/capabilities/test_provider_conformance.py` | Modified | Wired/unwired split |
| `tests/unit/capabilities/test_catalog_conformance.py` | Modified | No-branching scan narrowed to four modules |
| `tests/unit/{selection,test_worker}.py`, `tests/unit/config/` | New/Modified | Policy, composition, config |
| `src/tibios_ray/{runtime,transport,engines,backends}/**` | Untouched | Contracts and engines unchanged |

## Test Impact

Three existing tests assert exactly the invariant this change reverses. The archived `capability-providers/design.md` already documents all three as holding *"until Phase 4"* — breaking them is the plan, and each needs deliberate rewriting, not deletion:

| Test | Rewrite |
|---|---|
| `test_provider_conformance.py::TestProviderConformance::test_provider_declares_no_fields` | Parameterize: unwired Providers keep zero fields; wired Providers declare exactly `backends` + `selection_policy`, both immutable |
| `test_provider_conformance.py::TestProviderConformance::test_execute_always_raises_no_backend_available_error` | Split: unwired → still unconditional; wired → raises only with an empty/mismatched mapping, and dispatches otherwise |
| `test_catalog_conformance.py::test_no_branching_exists_in_any_provider_module` | Scope the AST scan to the four unwired modules; the wired three are exempted by name, with the exemption list asserted |

`test_worker.py`'s "independent registries" test must survive: `build_runtime()` still returns non-shared runtimes, but **backend instances are process-scoped by ADR-0001** — that tension needs an explicit test decision.

## Open Design Questions

For `sdd-design`. **Q6 is blocking; Q1 and Q3 are resolved (ADR-0004, ADR-0003).**

1. **~~Where does the request payload come from?~~ — RESOLVED by [ADR-0004](../../../docs/adr/0004-capability-request-boundary.md).** Each capability defines a typed `*Request` (`ChatRequest`, `EmbeddingRequest`, `RerankRequest`) implementing `CapabilityRequest.parse(parameters: Mapping[str, str]) -> Self`. All decoding of `execution_parameters` — including JSON-encoding of structured values like `documents` — lives exclusively there, with reject-don't-guess. `sdd-design` defines the concrete `*Request` shapes and their `parse()` rules; it does not reopen where the decoding lives.
2. **Which `ResolvedModelRef`?** `dependencies` is `tuple[ResolvedModelRef, ...]` — unkeyed (settled deliberately in `worker-context-wiring`). Define behavior for zero, one, and N.
3. **~~Residency lifetime.~~ — RESOLVED by [ADR-0003](../../../docs/adr/0003-backend-resource-ownership.md).** Resource ownership (created once at Backend init) is separate from concurrency strategy (Backend-internal). `LlamaCppTextBackend` moves from per-call `Llama` construction to a pool of N pre-warmed instances, sized via config, checked out/returned in `acquire()`/`release()`. `sdd-design` defines the pool's exhaustion behavior and startup-viability validation; it does not reopen whether pooling is the right strategy.
4. **Who acts on `ServingPlan.quantization`?** Neither `supports()` nor `acquire()` reads it today. ADR-0002 explicitly defers this to *this* change.
5. **Non-streaming results onto the channel.** `OutputChunk.data` is `bytes`; embedding vectors and rerank scores need a serialization decision (and the Report may not carry them).
6. **Failure taxonomy — BLOCKING.** Distinguish *no backend configured*, *plan names an absent backend*, *backend raised*, and *cancelled*. `NoBackendAvailableError` currently covers all of it by accident.
7. **Config shape.** Flat env vars per engine (e.g. `TIBIOS_RAY_LLAMACPP_MODEL_PATH`) vs. a structured file. Env matches `server.py`'s existing single-var precedent; a file scales better to N engines.

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Q6 unresolved → error paths collapse into one accidental catch-all | High | Blocking gate before apply; layered taxonomy per Capability/Backend/Provider/Worker |
| Pool sizing/exhaustion (ADR-0003) implemented inconsistently across the wired capabilities | Med | `sdd-design` fixes exhaustion behavior once; an explicit test asserting engine construction count (once at startup, never per-request) |
| Conformance tests get deleted instead of split, losing the unwired guarantee | Med | Rewrites are named deliverables above; unwired assertions must remain |
| Providers accrete selection logic while "just handling errors" | Med | ADR-0002 forbids it; keep an AST/branch guard on the wired three, allow-listing only dispatch-mechanical forms |
| Startup crashes when artifacts are absent (dev machines have no GGUF) | Med | Unconfigured → unwired capability, asserted by test; never a hard boot failure |
| Session leak on the failure path | Med | `release()` in `finally`; a test that raises mid-stream and asserts release |
| Naming audit / layering guards trip on new modules | Low | `capabilities/` still imports nothing from `runtime/`; run the existing guards early |
| Scope creep back into vision/speech/OCR | Low | Out-of-scope list is explicit and reasoned |

## Rollback Plan

Purely additive except three Provider constructors and `worker.py`. Reverting the slice commits restores zero-field Providers and the zero-arg composition — `runtime/`, `transport/`, `backends/`, and `engines/` are untouched, so nothing downstream of a Provider can regress. `config.py` and the concrete policy are new files: deleting them is a clean removal. The only non-mechanical revert is the conformance-test split, contained to `tests/unit/capabilities/`.

## Delivery

Estimated **~600–900 hand-written lines** — over the 400-line review budget, so **chained PRs are expected**. Natural slices: (1) config surface; (2) concrete `ModelSelectionPolicy` + test doubles; (3) `ChatProvider` wiring (the streaming case, hardest first); (4) `EmbeddingProvider` + `RerankProvider` (the batch cases); (5) Composition Root + conformance-test split. `sdd-tasks` owns the final split and MUST emit the Review Workload Forecast.

## Dependencies

- ADR-0001, ADR-0002, ADR-0003, ADR-0004 — all Accepted. **Satisfied.**
- `backends/{text,embedding,rerank}.py` Protocols and `engines/{llamacpp,vllm,onnxrt}.py` adapters — all shipped and archived. **Satisfied.**
- `worker-context-wiring` (`ExecutionContext` now carries `dependencies`, `execution_parameters`, `channel`, `cancellation`) — archived. **Satisfied.**
- No cross-repo coordination: `../proto/` and `tibios-core` are untouched.

## Success Criteria

- [ ] A `chat.generate` execution with a configured llama.cpp or vLLM backend streams `OutputChunk`s and returns a `COMPLETED` `ExecutionReport`
- [ ] `embedding.generate` and `rerank.documents` return `COMPLETED` against a configured ONNX Runtime backend
- [ ] No Provider constructs, discovers, or mutates a backend; `worker.py` is the only module importing `engines/`
- [ ] No Provider contains selection logic — the injected `ModelSelectionPolicy` makes every backend choice
- [ ] With no configuration present, the Worker starts and every capability fails cleanly as unwired — no crash, no fabricated backend
- [ ] Vision, speech (both), and OCR still raise `NoBackendAvailableError` unconditionally, asserted by test
- [ ] Backends, and any pooled resources they own (ADR-0003), are constructed once at startup and never per-request, asserted by a construction-count test
- [ ] `uv run pytest` / `ruff check` / `pyright` pass; layering and naming guards still find zero violations
