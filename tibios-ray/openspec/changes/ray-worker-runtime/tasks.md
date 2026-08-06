# Tasks: Ray Worker Runtime (Foundation)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~900-1400 total, ~130-260 per slice |
| 400-line budget risk | Low per slice / High if delivered as one PR |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 execution/ -> PR 2 backends/ -> PR 3 selection/ -> PR 4 capabilities/ -> PR 5 runtime/ -> PR 6 testing/ -> PR 7 wiring+docs |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | `execution/` vocabulary | PR 1 | base=main; no deps |
| 2 | `backends/` contract | PR 2 | base=PR1; needed by selection+capabilities |
| 3 | `selection/` policy | PR 3 | base=PR2; needs `BackendId` |
| 4 | `capabilities/` provider+descriptor | PR 4 | base=PR3; needs `BackendId` |
| 5 | `runtime/` registry+lifecycle | PR 5 | base=PR4; needs `CapabilityProvider` |
| 6 | `testing/` shared fakes | PR 6 | base=PR5; dedupes ad-hoc doubles |
| 7 | wiring + docs | PR 7 | base=PR6; small |

**Deviation note**: design's illustrative slice order (`execution -> runtime -> capabilities -> selection -> backends`) mirrors the Module Layout table row order, but `registry.py` requires `CapabilityProvider` and `ServingPlan`/`CapabilityDescriptor` require `BackendId` — building `runtime/` or `capabilities/` before `backends/`/`selection/` exist creates forward references. Reordered to the actual import chain: `execution -> backends -> selection -> capabilities -> runtime -> testing`.

## Phase 0: Precondition

- [x] 0.1 Apply `python-foundation` (own change, proposal-only today, no tasks.md) — pytest/ruff/pyright + package layout must land before any task below. Applied directly 2026-08-06 (see `sdd/python-foundation/apply-progress`).

## Phase 1: execution/ vocabulary (PR 1)

- [x] 1.1 `ids.py`: `ObjectId`, `ObjectVersion`, `ContentHash` (frozen, slotted; D3)
- [x] 1.2 `context.py`: `ExecutionContext`, `AllocationContract`, `ResolvedModelRef` (only constructible from `ctx.dependencies`)
- [x] 1.3 `channel.py`: `ExecutionChannel` (write-only `emit`), `CancellationToken` Protocol (D5)
- [x] 1.4 `events.py`: `ExecutionEvent` PEP 695 tagged union (D7)
- [x] 1.5 `report.py`: `ExecutionReport`, `ExecutionPulse`, `ExecutionPhase`
- [x] 1.6 `tests/unit/execution/`: immutability + `ResolvedModelRef` proof-carrying construction — done 2026-08-06, 47/47 tests passing, ruff+pyright clean (see `sdd/ray-worker-runtime/apply-progress`)

## Phase 2: backends/ contract (PR 2)

- [x] 2.1 `adapter.py`: `BackendAdapter` Protocol (backend_id, supports, acquire, release), `BackendId`, `BackendSession` (D4) — done 2026-08-06
- [x] 2.2 `text.py`/`embedding.py`/`rerank.py`/`speech.py`: per-modality execution Protocols — done 2026-08-06
- [x] 2.3 `tests/unit/backends/` + `assert_type` conformance: no llama.cpp/TensorRT-LLM/vLLM/ONNX/Faster-Whisper imports — done 2026-08-06, 39/39 new tests passing (86/86 total), ruff+pyright clean (see `sdd/ray-worker-runtime/apply-progress`)

## Phase 3: selection/ policy (PR 3) — COMPLETE 2026-08-06

- [x] 3.1 `policy.py`: `ModelSelectionPolicy.plan(model: ResolvedModelRef, constraints) -> ServingPlan`, `ServingConstraints`, `Quantization` — done, `ServingPlan.backend: BackendId` satisfies `backends/adapter.py`'s `ServingPlanLike` structurally
- [x] 3.2 pyright fixture: `policy.plan("deepseek")  # type: ignore[arg-type]` + `reportUnnecessaryTypeIgnoreComment = true` (correct pyright rule name; `reportUnnecessaryTypeIgnore` is not a recognized pyright setting) — done, `tests/unit/selection/pyright_fixtures/rejects_bare_family_string.py`, guard verified to actually fire (see `sdd/ray-worker-runtime/apply-progress`)
- [x] 3.3 `tests/unit/selection/`: decision has only backend+quantization, no discovery step — done 2026-08-06, 13/13 new tests passing (99/99 total), ruff+pyright clean (see `sdd/ray-worker-runtime/apply-progress`)

## Phase 4: capabilities/ provider surface (PR 4) — COMPLETE 2026-08-06

- [x] 4.1 `names.py`: `CapabilityName` + shape validation — generic dot-separated lowercase snake_case shape, not a hardcoded enum (Phase 2's concrete Providers don't exist yet) — done
- [x] 4.2 `descriptor.py`: `CapabilityDescriptor`, `CapabilityFlags`, `CapabilityCatalog` — plus `ModelFamily` (gap resolution, see below) — done
- [x] 4.3 `provider.py`: `CapabilityProvider` Protocol (descriptor property, async execute) — `execute()` returns `ExecutionReport`, not `ExecutionMetrics` (gap resolution, see below) — done
- [x] 4.4 `tests/unit/capabilities/`: conforming provider descriptor shape is stable, `CapabilityName` shape validation edge cases, `ModelFamily`/`CapabilityDescriptor` construction — done 2026-08-06, 36/36 new tests passing (135/135 total), ruff+pyright clean (see `sdd/ray-worker-runtime/apply-progress`)

**Two undefined-type gaps resolved during apply (not resolved by design.md/tasks.md as written):**
- **`ExecutionMetrics`** (referenced in `design.md`'s Key Contracts but never defined anywhere): resolved as the already-existing `ExecutionReport` — see `capabilities/provider.py`'s module docstring for full reasoning. No new type added to `execution/`; Phase 1 was not reopened.
- **`ModelFamily`** (referenced in `design.md`'s `CapabilityDescriptor.families: frozenset[ModelFamily]` but never defined anywhere): defined as a small frozen, slotted dataclass in `capabilities/descriptor.py`, shaped like `backends/adapter.py`'s `BackendId` (single opaque `value: str`) — outward catalog metadata only, per `design.md`'s own boundary rule that family strings never enter the inward execution path.

## Phase 5: runtime/ lifecycle host (PR 5) — COMPLETE 2026-08-06

- [x] 5.1 `registry.py`: `CapabilityRegistry` (immutable, ctor-built, duplicate capability -> error, empty-catalog provider -> error, `resolve()`, `catalog()`) — done
- [x] 5.2 `worker_runtime.py`: `WorkerRuntime.execute(ctx) -> ExecutionReport`, dispatch only via registry — done, cooperative cancellation (D5), never lets a Provider exception escape, always emits terminal `EndOfStream`
- [x] 5.3 `errors.py`: Worker Contract-conformant error types (`DispatchError`/`UnknownCapabilityError`, `RegistrationError`/`DuplicateCapabilityError`/`EmptyCatalogError`) — done
- [x] 5.4 `tests/unit/runtime/`: success lifecycle, unknown capability -> Failed report (no exception), malformed capability string -> Failed report (no exception), cancellation -> ack+cleanup+final events+report, duplicate-capability rejection, empty-catalog rejection, aggregated catalog — done 2026-08-06, 17/17 new tests passing (152/152 total), ruff+pyright clean
- [x] 5.5 Naming audit test (`tests/unit/runtime/test_naming_audit.py`, AST-identifier based, permanent): `capabilities/`, `selection/`, `backends/` zero "Worker" identifiers; `runtime/` exempt only for `WorkerRuntime` — done, mutation-verified (temporarily injected a `Worker`-named identifier, confirmed the test fails, reverted, confirmed green again)

## Phase 6: testing/ shared fakes (PR 6) — COMPLETE 2026-08-06

- [x] 6.1 `InMemoryExecutionChannel`, `FakeExecutionContext`, `ManualCancellation`, `StubProvider`, `RecordingBackend` — done, RED-first (`tests/unit/testing/`: 22 new tests, all failed with `ModuleNotFoundError` before `src/tibios_ray/testing/` existed), then GREEN (174/174 total), ruff+pyright clean. Naming audit (Phase 5) extended to also scan `testing/` (zero exemptions), mutation-verified.
- [x] 6.2 Retrofit Phase 1-5 ad-hoc test doubles to import from `testing/` (dedupe) — done, 6 files retrofitted one at a time (`tests/unit/execution/test_channel.py`, `tests/unit/execution/test_context.py`, `tests/unit/capabilities/test_provider.py`, `tests/unit/runtime/test_registry.py`, `tests/unit/runtime/test_worker_runtime.py`, `tests/unit/backends/test_adapter.py`), full suite re-run green after each swap, no assertions changed (174/174 total throughout), ruff+pyright clean.

## Phase 7: wiring + docs (PR 7) — COMPLETE 2026-08-06

- [x] 7.1 `worker.py` docstring: composition root builds registry, owns one `WorkerRuntime` — done, updated to reference the now-real `CapabilityRegistry`/`WorkerRuntime` types (Phases 4-5), still zero business logic, notes gRPC wiring is blocked on the not-yet-existing `.proto` contract (sibling `proto-worker-contract` change in progress in `tibios-core`)
- [x] 7.2 `docs/architecture/01-worker-runtime.md`: cites `18-worker-model.md`, no duplication — done, summary-level flow/terminology/module-layout doc pointing to `design.md` and `openspec/changes/ray-worker-runtime/` for detail
- [x] 7.3 Repo-wide grep: zero `local-infer` routing rule, zero stray "Worker" identifiers — confirms proposal Success Criteria — done, manual `rg` sweep of `src/`, `tests/`, `docs/`, `README.md`, `pyproject.toml`: zero `local-infer`/size-routing patterns anywhere; every "Worker" occurrence outside `WorkerRuntime` is a docstring/prose citation of the Worker Contract concept, none are code identifiers (Phase 5's AST-based `test_naming_audit.py` already enforces this for `capabilities/selection/backends/runtime/testing/` at the unit level)

## Post-verify addendum: permanent no-local-infer-routing guard (closes sdd-verify WARNING #2)

All 7 phases above were already 100% complete when `sdd-verify` ran (`sdd/ray-worker-runtime/verify-report`, PASS WITH WARNINGS). WARNING #2 noted that task 7.3's repo-wide sweep was a one-time manual `rg` check, not a permanent regression guard — unlike the naming rule (`test_naming_audit.py`), which has a mutation-verified AST-based pytest test. This addendum closes that gap without reopening or renumbering Phase 0-7.

- [x] A.1 Added `tests/unit/runtime/test_no_local_infer_routing.py`: two permanent, AST-based, mutation-verified pytest tests enforcing `proposal.md`'s Boundary Rules / `25-ai-runtime.md`'s Anti-Patterns ("no size/cost routing rule between `local-infer` and tibios-ray may exist anywhere"). Scans `execution/`, `backends/`, `selection/`, `capabilities/`, `runtime/`, `testing/`, `worker.py`, `server.py` for (1) literal `local-infer`/`local_infer` string constants outside docstrings, and (2) size/cost-threshold-shaped `Compare` nodes (e.g. `model_size < 4_000_000_000`). Docstring's "What this deliberately does NOT catch" section documents the heuristic's honest limits. Mutation-tested live: injected both violation shapes into `selection/policy.py`, confirmed both new tests failed with a clear message naming the exact file and violation, reverted, confirmed 176/176 green again. `uv run pytest`, `uv run ruff check`, `uv run pyright` all clean (176 tests, up from 174).
