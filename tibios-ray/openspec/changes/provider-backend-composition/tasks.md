# Tasks: Provider-Backend Composition

Source of truth for slice boundaries: `design.md`'s `File Changes` table and
`Slice Plan` (7 slices, `auto-chain`). `proposal.md`'s Delivery section
(6 slices) is superseded by `design.md`'s more detailed table, which maps
every file to a slice number explicitly — this checklist follows
`design.md`.

Strict TDD (`uv run pytest`): within each slice, the test task for a unit
precedes its implementation task. `uv run pytest && uv run ruff check &&
uv run pyright` MUST be green at the end of every slice before opening the
next PR.

ADRs 0001-0004 are ground truth and are not re-justified here. Design
decisions D18-D29 are referenced by number; see `design.md` for rationale.

## Review Workload Forecast

- **Total estimated size**: ~1000-1300 hand-written lines (per
  `design.md`'s `Slice Plan`, revised up from `proposal.md`'s original
  600-900 estimate once the `engines/llamacpp.py` pool work (slice 6,
  ADR-0003) was accounted for in `Affected Areas`).
- **400-line review budget risk**: **High**. Every slice below is sized to
  land as its own PR near or under ~250 lines of hand-written code, but the
  total across all 7 slices is 2.5-3.25x the single-PR budget.
- **Chained/stacked PRs recommended**: **Yes** — `design.md`'s `Slice Plan`
  already designates this `auto-chain` (7 chained PRs, each independently
  green under the full check suite). Slice 6 (`llama.cpp` pool) is the one
  exception: it depends only on slice 1 (config) and may land as a
  **parallel**, not chained, PR alongside slices 2-5.
- **Decision needed before `sdd-apply` runs**: **Yes.** Delivery strategy
  is cached as `ask-on-risk`; this forecast crosses the size and chaining
  thresholds that trigger it. The orchestrator MUST stop and confirm
  chained/stacked PRs (default, matching `design.md`) vs. a
  maintainer-approved `size:exception` for a single PR before `sdd-apply`
  begins slice 1.
- **Per-slice rough sizing** (implementation + tests, hand-written lines
  only — generated/boilerplate excluded): Slice 1 ~120-160; Slice 2
  ~150-200; Slice 3 ~200-260; Slice 4 ~150-200; Slice 5 ~150-200; Slice 6
  ~150-200; Slice 7 ~100-150. Sum lands inside the ~1000-1300 total above.

## Dependency Graph

```
Slice 1 (config)         ──────────────┬──────────────► Slice 7 (composition root)
Slice 2 (policy+doubles) ─► Slice 3 ─► Slice 4 ─► Slice 5 ─┘
Slice 1 ─────────────────────────────────────────► Slice 6 (llama.cpp pool) ─┘
```

- Slices 1 and 2 have no dependencies — both may start immediately, in
  parallel.
- Slice 3 depends on slice 2 only (needs `PreferenceOrderPolicy`/`ARTIFACT_DEFINED`/`UnsatisfiablePlanError` and the fakes for its own tests).
- Slice 4 depends on slice 3. Slice 5 depends on slice 4.
- Slice 6 depends on slice 1 only (needs `LlamaCppConfig`/pool-size config)
  and is **independent of slices 3-5** — it may land in parallel with them.
- Slice 7 depends on all of 1-6 (it is the Composition Root wiring
  everything together, plus the conformance-test narrowing that only makes
  sense once slices 4/5 exist).

## Slice 1 — Config surface

No dependencies. May run in parallel with Slice 2.

- [x] 1.1 Test: `tests/unit/config/__init__.py` + `tests/unit/config/test_config.py` — empty `env` mapping → every `WorkerConfig` field `None`; one engine's env vars present → only that engine's config object is non-`None`; ONNX model path present without tokenizer path → raises; `TIBIOS_RAY_LLAMACPP_POOL_SIZE="abc"` and `"0"` → both raise; a configured path is returned byte-identical to the input string (D19 test table, `worker-configuration` spec: Process-Supplied Per-Engine Artifact Configuration, Absent configuration is represented as absent, Malformed configuration fails startup explicitly)
- [x] 1.2 Implement: `src/tibios_ray/config.py` — `LlamaCppConfig`, `VllmConfig`, `OnnxConfig` (frozen, slots, kw-only dataclasses), `WorkerConfig` aggregating all four engine slots, `WorkerConfig.from_env(env: Mapping[str, str] | None = None)` reading `TIBIOS_RAY_LLAMACPP_{GGUF,POOL_SIZE}`, `TIBIOS_RAY_VLLM_MODEL`, `TIBIOS_RAY_ONNX_{EMBEDDING,RERANK}_{MODEL,TOKENIZER,OUTPUT_NAME}` (D19)
- [x] 1.3 Test: pool-size default — artifact configured, `TIBIOS_RAY_LLAMACPP_POOL_SIZE` absent → construction succeeds with the documented default pool size, not treated as absent artifact config (`worker-configuration` spec: Backend-Internal Resource Sizing Is Independently Configurable, both scenarios)
- [x] 1.4 Implement/confirm: default pool size constant documented alongside `LlamaCppConfig` (satisfies 1.3)
- [x] 1.5 Test: `rg`-style guard in `tests/unit/config/test_config_isolation.py` — no module outside `worker.py`/`config.py` reads `os.environ` or imports `tibios_ray.config` (D19 guard row; `worker-configuration` spec: Composition Root Is the Configuration Surface's Sole Consumer)
- [x] 1.6 Verify slice 1 green: `uv run pytest tests/unit/config/ && uv run ruff check src/tibios_ray/config.py && uv run pyright src/tibios_ray/config.py`

## Slice 2 — Policy + test doubles

No dependencies. May run in parallel with Slice 1.

- [ ] 2.1 Test: `tests/unit/selection/test_preference.py` — `PreferenceOrderPolicy.plan()` deterministic across two identical calls; preference order honoured when multiple ranked backends are available; an unranked `BackendId` present in `available_backends` falls back to the lexicographically smallest `.value`; empty `available_backends` raises `UnsatisfiablePlanError`; the returned `plan.backend` is always a member of `available_backends` (D28; `model-selection-policy` spec: A Concrete ModelSelectionPolicy Implementation Exists — both scenarios, plan() Never Returns a Backend Outside Availability Constraints — both scenarios)
- [ ] 2.2 Test: quantization sentinel — `plan().quantization == ARTIFACT_DEFINED` for every resolved plan (D23, part 1)
- [ ] 2.3 Implement: `src/tibios_ray/selection/errors.py` — `UnsatisfiablePlanError` (D21, D28; `selection/` MUST NOT import `capabilities/`)
- [ ] 2.4 Implement: `src/tibios_ray/selection/preference.py` — `ARTIFACT_DEFINED = Quantization(scheme="artifact-defined", bits=0)` sentinel (D23), `PreferenceOrderPolicy(preference: tuple[BackendId, ...])` (D28)
- [ ] 2.5 Modify: `src/tibios_ray/selection/__init__.py` — re-export `PreferenceOrderPolicy`, `ARTIFACT_DEFINED`, `UnsatisfiablePlanError` in `__all__`
- [ ] 2.6 Test: `tests/unit/testing/test_testing_policy.py`, `test_testing_text_backend.py`, `test_testing_embedding_backend.py`, `test_testing_rerank_backend.py` — each fake conforms to its Protocol and its recording/injection knobs behave as documented (following `RecordingBackend`'s existing test pattern)
- [ ] 2.7 Implement: `src/tibios_ray/testing/policy.py` — a fake/injectable `ModelSelectionPolicy` for Provider tests (returns a caller-supplied plan or raises on demand)
- [ ] 2.8 Implement: `src/tibios_ray/testing/text_backend.py`, `testing/embedding_backend.py`, `testing/rerank_backend.py` — fakes conforming to `TextGenerationBackend`/embedding/rerank Backend Protocols, following `RecordingBackend`'s shape (records acquired/released sessions; injectable to raise at `acquire`/execute/`release`)
- [ ] 2.9 Modify: `src/tibios_ray/testing/__init__.py` — register the four new fakes in `__all__` (naming-audit guard in `tests/unit/runtime/test_naming_audit.py` applies — no "Worker"-named identifier)
- [ ] 2.10 Verify slice 2 green: `uv run pytest tests/unit/selection/ tests/unit/testing/ && uv run ruff check src/tibios_ray/selection/ src/tibios_ray/testing/ && uv run pyright src/tibios_ray/selection/ src/tibios_ray/testing/`

## Slice 3 — Requests + failure taxonomy + dispatch helpers

Depends on Slice 2 (needs the fakes and `PreferenceOrderPolicy`/`ARTIFACT_DEFINED` for its own tests).

- [ ] 3.1 Test: `tests/unit/capabilities/test_requests.py` — table-driven over every Required/Rejected row in `design.md`'s Key Contracts table for `ChatRequest`, `EmbeddingRequest`, `RerankRequest` (prompt/max_tokens/temperature/stop; inputs; query/documents), plus "unknown key present → parse succeeds" (D22; ADR-0004)
- [ ] 3.2 Implement: `src/tibios_ray/capabilities/requests.py` — `CapabilityRequest` Protocol (`parse(parameters: Mapping[str, str]) -> Self`), `ChatRequest`, `EmbeddingRequest`, `RerankRequest` (D22)
- [ ] 3.3 Test: extend `tests/unit/capabilities/test_errors.py` (or a new `test_errors_taxonomy.py`) — each of the five `ProviderExecutionError` subclasses raised from its own trigger; `BackendExecutionError.__cause__` is the wrapped backend exception and `.stage` distinguishes `acquire`/`execute`/`release`; `NoBackendAvailableError` remains a plain `Exception` subclass so existing `pytest.raises` calls still hold (D21)
- [ ] 3.4 Modify: `src/tibios_ray/capabilities/errors.py` — add `ProviderExecutionError(Exception)` base; re-parent `NoBackendAvailableError` under it (signature unchanged); add `UnresolvableBackendError`, `BackendExecutionError`, `MissingModelDependencyError`, `RequestParseError`; update the module docstring's CP3 rationale (no longer "exactly one catch site") (D21)
- [ ] 3.5 Test: `tests/unit/capabilities/test_dispatch.py` — `resolve_model_ref`: 0 deps → `MissingModelDependencyError`; 1 dep → that ref reaches `plan()`; 3 deps → `dependencies[0]` reaches `plan()` twice identically across two calls, and exactly one `Warning` event with `code="extra_dependencies"` is emitted (D20; `provider-backend-composition` spec: Model Reference Selection From Context Dependencies — all three scenarios)
- [ ] 3.6 Test: extend `test_dispatch.py` — `resolve_backend`: empty mapping → `NoBackendAvailableError`; `plan.backend` absent from mapping → `UnresolvableBackendError` (never falls back to another entry); a present `plan.backend` returns `(backend, plan)` (D21; `provider-backend-composition` spec: Failure Outcomes Are Behaviorally Distinguishable — first two scenarios; `capability-providers` spec: Wired Provider fails when mapping is empty / when plan names an absent backend)
- [ ] 3.7 Test: extend `test_dispatch.py` — `completed_report`/`cancelled_report` builders never populate an output-carrying field (`provider-backend-composition` spec: ExecutionReport never carries application output)
- [ ] 3.8 Implement: `src/tibios_ray/capabilities/dispatch.py` — `resolve_model_ref(context, *, capability)`, `resolve_backend(backends, policy, model, *, capability)`, `completed_report(*, started_at, trace_id)`, `cancelled_report(*, started_at, trace_id)` — module-level pure functions, no state (D18/D20/D21)
- [ ] 3.9 Test: `.quantization` guard — no file under `src/tibios_ray/engines/` contains `.quantization` (D23, part 2; can live in `test_dispatch.py` or a small dedicated `test_no_quantization_reads.py`)
- [ ] 3.10 Verify slice 3 green: `uv run pytest tests/unit/capabilities/test_requests.py tests/unit/capabilities/test_errors.py tests/unit/capabilities/test_dispatch.py && uv run ruff check src/tibios_ray/capabilities/ && uv run pyright src/tibios_ray/capabilities/`

## Slice 4 — ChatProvider (streaming, hardest case first)

Depends on Slice 3.

- [ ] 4.1 Test: extend `tests/unit/capabilities/test_provider_conformance.py::test_provider_declares_no_fields` — parameterize: unwired Providers (Vision, Speech-transcribe, Speech-synthesize, OCR) keep zero fields; `ChatProvider` declares exactly `backends` + `selection_policy`, both immutable (D18; `provider-backend-composition` spec: A wired Provider holds exactly its two injected fields)
- [ ] 4.2 Test: extend conformance — mutating `chat_provider.backends` raises; mutating the source `dict` passed to the constructor does not change `provider.backends` afterwards (D18; `provider-backend-composition` spec: The injected mapping is immutable after construction)
- [ ] 4.3 Test: `tests/unit/capabilities/test_chat.py` — successful dispatch: non-empty mapping + resolving policy → `acquire()` called with the plan, `generate()` runs, `release()` called, one or more `OutputChunk`s emitted, `ExecutionReport.phase == COMPLETED`, direct `execute()` call emits **no** `EndOfStream` (D25; `provider-backend-composition` spec: Successful dispatch streams output and returns COMPLETED)
- [ ] 4.4 Test: extend `test_chat.py` — chat codec (D24): N non-empty `TextChunk` deltas → N `OutputChunk`s, `sequence` 0..N-1, `data == text.encode()`; the terminal empty/`finished=True` delta emits no chunk
- [ ] 4.5 Test: extend `test_chat.py` — cooperative cancellation: `context.cancellation` signals mid-stream → Provider stops driving further output, still calls `release()` on the acquired session, returns `ExecutionReport.phase == CANCELLED` and raises nothing (`provider-backend-composition` spec: Cooperative cancellation is observed mid-execution, Cancellation yields CANCELLED)
- [ ] 4.6 Test: extend `test_chat.py` — release guarantee: backend raises mid-stream → `release()` still called exactly once with that session before the error propagates; `acquire()` itself raises → `release()` never called (`provider-backend-composition` spec: Backend Session Release Is Guaranteed — both scenarios)
- [ ] 4.7 Test: extend `test_chat.py` — empty mapping → `NoBackendAvailableError`; plan names a `BackendId` absent from a non-empty mapping → `UnresolvableBackendError`, never falls back to the mapping's existing entry (`capability-providers` spec: Wired Provider fails when mapping is empty / when plan names an absent backend)
- [ ] 4.8 Implement: `src/tibios_ray/capabilities/chat.py` — add `backends: Mapping[BackendId, TextGenerationBackend]` and `selection_policy: ModelSelectionPolicy` fields (`__post_init__` normalizing via `MappingProxyType`, D18), real `execute()` using `capabilities/dispatch.py` + `capabilities/requests.py` helpers, chat's D24 codec
- [ ] 4.9 Test: `tests/unit/capabilities/test_provider_conformance.py::test_execute_always_raises_no_backend_available_error` — split: unwired Providers still unconditional; `ChatProvider` raises only with an empty/mismatched mapping and dispatches otherwise (Test Impact table, row 2 — chat-only slice of the split)
- [ ] 4.10 Test: no-scoring / no-branching check for `chat.py` — every conditional in `execute()` guards only empty mapping, unresolvable `plan.backend`, cancellation, or dependency-count validation; no logic chooses among backends by model/family/size/cost (`provider-backend-composition` spec: No scoring or capability-matching code exists, Every conditional present is dispatch-mechanical; `capability-providers` spec: Dispatch-mechanical conditionals in wired Providers are not routing violations)
- [ ] 4.11 Verify slice 4 green: `uv run pytest tests/unit/capabilities/ && uv run ruff check src/tibios_ray/capabilities/chat.py && uv run pyright src/tibios_ray/capabilities/chat.py`

## Slice 5 — EmbeddingProvider + RerankProvider (batch cases)

Depends on Slice 4 (reuses the same conformance-split pattern and `dispatch.py`/`requests.py` seams `chat.py` exercised first).

- [ ] 5.1 Test: extend `test_provider_conformance.py::test_provider_declares_no_fields` — `EmbeddingProvider` and `RerankProvider` also declare exactly `backends` + `selection_policy`, immutable, completing the parameterization started in 4.1
- [ ] 5.2 Test: `tests/unit/capabilities/test_embedding.py` — successful dispatch (`embed()` via `acquire`/`release`), release guarantee (raise mid-execute / `acquire()` raises), empty-mapping and absent-plan-backend failures, cancellation → `CANCELLED` — same coverage shape as `test_chat.py` 4.3/4.5/4.6/4.7, embedding-specific
- [ ] 5.3 Test: extend `test_embedding.py` — D24 embedding codec: exactly one `OutputChunk`, `sequence=0`, `json.loads(data)` round-trips `{"vectors": [[...], ...]}` in input order; `ExecutionReport` carries none of the vectors (`provider-backend-composition` spec: Embedding output appears on the channel, not the report)
- [ ] 5.4 Implement: `src/tibios_ray/capabilities/embedding.py` — two injected fields, real `execute()` using `dispatch.py`/`requests.py`, D24 embedding codec
- [ ] 5.5 Test: `tests/unit/capabilities/test_rerank.py` — successful dispatch, release guarantee, empty-mapping/absent-plan-backend failures, cancellation — same shape as embedding, rerank-specific
- [ ] 5.6 Test: extend `test_rerank.py` — D24 rerank codec: exactly one `OutputChunk`, `sequence=0`, `json.loads(data)` round-trips `{"results": [{"index": i, "score": s}, ...]}` in order; `ExecutionReport` carries none of the scores (`provider-backend-composition` spec: Rerank output appears on the channel, not the report)
- [ ] 5.7 Implement: `src/tibios_ray/capabilities/rerank.py` — two injected fields, real `execute()`, D24 rerank codec
- [ ] 5.8 Test: complete `test_provider_conformance.py::test_execute_always_raises_no_backend_available_error` split for embedding + rerank (Test Impact table, row 2 — completing the split started in 4.9)
- [ ] 5.9 Test: no-scoring / no-branching check for `embedding.py` and `rerank.py`, mirroring 4.10
- [ ] 5.10 Verify slice 5 green: `uv run pytest tests/unit/capabilities/ && uv run ruff check src/tibios_ray/capabilities/{embedding,rerank}.py && uv run pyright src/tibios_ray/capabilities/{embedding,rerank}.py`

## Slice 6 — llama.cpp pool (independent of Slices 3-5; depends only on Slice 1)

May land as a parallel PR alongside slices 2-5, not chained after them.

- [ ] 6.1 Test: `tests/unit/engines/test_llamacpp_pool.py` — pool size N → the `Llama` factory is called exactly N times at construction and never again across M > N subsequent `acquire()` calls (D26/D27; success criterion "constructed once at startup and never per-request")
- [ ] 6.2 Test: extend `test_llamacpp_pool.py` — N+1 concurrent `acquire()`s with only N instances available → the (N+1)th waits, then succeeds once one instance is `release()`d
- [ ] 6.3 Test: extend `test_llamacpp_pool.py` — none released before `TIBIOS_RAY_LLAMACPP_ACQUIRE_TIMEOUT_SECONDS` elapses → `PoolExhaustedError` raised and `release()` never called (no session existed) (D26)
- [ ] 6.4 Test: extend `test_llamacpp_pool.py` — `release()` returns the instance to the pool without calling `close()` on it (D26 — instances are process-scoped, ADR-0001)
- [ ] 6.5 Test: extend `test_llamacpp_pool.py` — `pool_size=0` raises before any factory call; a missing/unreadable `model_path` raises before the factory is called (D27 pre-checks)
- [ ] 6.6 Test: extend `test_llamacpp_pool.py` — factory raising on the 2nd of 3 eager constructions → construction raises and propagates out of `build_runtime()` (used later by Slice 7's boot-failure assertion, defined here since it's this module's contract) (D27)
- [ ] 6.7 Implement: `src/tibios_ray/engines/llamacpp.py` — `PoolExhaustedError`; replace per-call `Llama` construction with an `asyncio.Queue`-backed pool of N pre-warmed instances built eagerly in `__init__`; `acquire()` = `await queue.get()` under `asyncio.timeout(acquire_timeout)`; `release()` = join the pump thread off-loop then `put_nowait`; keep `_Residency.lock`; two pre-checks (`pool_size >= 1`, `model_path` exists and is readable) before eager construction (D26/D27)
- [ ] 6.8 Verify slice 6 green: `uv run pytest tests/unit/engines/ && uv run ruff check src/tibios_ray/engines/llamacpp.py && uv run pyright src/tibios_ray/engines/llamacpp.py`

## Slice 7 — Composition Root

Depends on Slices 1-6 (all of them: needs `config.py`, the policy, the three wired Providers, and the pooled `LlamaCppTextBackend`).

- [ ] 7.1 Test: `tests/unit/test_worker.py` — `build_runtime() is not build_runtime()` still holds (existing "independent registries" test, D29 — unchanged, must survive)
- [ ] 7.2 Test: extend `test_worker.py` — zero configuration present → `build_runtime()` returns a `WorkerRuntime` without raising, and every wired Provider's mapping is empty (`worker-configuration` spec: Worker starts with zero configuration present; success criterion "no crash, no fabricated backend")
- [ ] 7.3 Test: extend `test_worker.py` — exactly one engine configured → only that engine's `BackendId` is present in its matching Provider's injected mapping, other Providers' mappings omit it (`worker-configuration` spec: A partially configured deployment wires only the configured engines)
- [ ] 7.4 Test: extend `test_worker.py` — construction-count assertion: engines (including the llama.cpp pool) are built exactly once per `build_runtime()` call, never per request (success criterion; D29)
- [ ] 7.5 Implement: `src/tibios_ray/worker.py` — real Composition Root: `build_runtime(config: WorkerConfig | None = None)`, `config or WorkerConfig.from_env()`, construct `PreferenceOrderPolicy`, build per-engine Backend instances only when their config is present, assemble the `text`/`embedding`/`rerank` mappings, inject `ChatProvider`/`EmbeddingProvider`/`RerankProvider` plus the four unwired Providers unchanged (D29)
- [ ] 7.6 Test: `worker.py` is the sole importer of concrete engine classes — `rg` guard over `src/tibios_ray/` for `LlamaCppTextBackend`/`VllmTextBackend`/`OnnxEmbeddingBackend`/`OnnxRerankBackend` imports finds only `worker.py` (`provider-backend-composition` spec: Composition Root Exclusive Backend Ownership)
- [ ] 7.7 Modify: `tests/unit/capabilities/test_catalog_conformance.py::test_no_branching_exists_in_any_provider_module` — scope the AST no-branching scan to the four unwired modules only, and assert the exemption list itself (naming the three wired modules) (Test Impact table, row 3; `capability-providers` spec: No hardcoded model/local-infer/routing conditional in unwired modules)
- [ ] 7.8 Test: end-to-end wiring smoke — a `WorkerConfig` with every engine configured, passed through `build_runtime()`, produces a `WorkerRuntime` whose registry resolves all three wired capabilities to Providers with non-empty mappings (ties slices 1-6 together; not a real-SDK integration test — uses the fakes/stubs already in `tests/unit/engines/`)
- [ ] 7.9 Verify success criteria end-to-end: `uv run pytest && uv run ruff check && uv run pyright` — full suite, including layering/naming/`no_engine_imports` guards, zero violations
- [ ] 7.10 Verify slice 7 green and full success-criteria checklist from `proposal.md` satisfied

## Cross-Slice Guards (re-run at the end of every slice, not just once)

- [ ] G.1 `capabilities/` imports nothing from `runtime/` (`capability-providers` spec: capabilities/ imports nothing from runtime/) — unaffected by this change but re-verified as new files land in `capabilities/`
- [ ] G.2 Existing layering (`tests/unit/catalog/test_layering.py`, `tests/unit/engines/test_engines_layering.py`), naming (`tests/unit/runtime/test_naming_audit.py`), and `no_engine_imports` (`tests/unit/backends/test_no_engine_imports.py`) guards stay at zero violations after every slice
- [ ] G.3 `selection/` imports nothing from `capabilities/` (D21 constraint on `UnsatisfiablePlanError`'s placement)
