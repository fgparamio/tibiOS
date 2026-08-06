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

## Phase 5: runtime/ lifecycle host (PR 5)

- [ ] 5.1 `registry.py`: `CapabilityRegistry` (immutable, ctor-built, duplicate capability -> error, `resolve()`, `catalog()`)
- [ ] 5.2 `worker_runtime.py`: `WorkerRuntime.execute(ctx) -> ExecutionReport`, dispatch only via registry
- [ ] 5.3 `errors.py`: Worker Contract-conformant error types
- [ ] 5.4 `tests/unit/runtime/`: success lifecycle, unknown capability -> Failed report (no exception), cancellation -> ack+cleanup+final events+report, duplicate-capability rejection, aggregated catalog
- [ ] 5.5 Naming audit test: grep `runtime/`, `selection/`, `backends/`, `capabilities/` for "Worker" -> zero matches

## Phase 6: testing/ shared fakes (PR 6)

- [ ] 6.1 `InMemoryExecutionChannel`, `FakeExecutionContext`, `ManualCancellation`, `StubProvider`, `RecordingBackend`
- [ ] 6.2 Retrofit Phase 1-5 ad-hoc test doubles to import from `testing/` (dedupe)

## Phase 7: wiring + docs (PR 7)

- [ ] 7.1 `worker.py` docstring: composition root builds registry, owns one `WorkerRuntime`
- [ ] 7.2 `docs/architecture/01-worker-runtime.md`: cites `18-worker-model.md`, no duplication
- [ ] 7.3 Repo-wide grep: zero `local-infer` routing rule, zero stray "Worker" identifiers — confirms proposal Success Criteria
