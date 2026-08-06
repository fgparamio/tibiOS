# Proposal: Model Catalog

## Intent

`ModelFamily` is an opaque label (`"qwen"`, `"whisper"`). The seven Providers advertise families truthfully, but nothing in tibios-ray records **which concrete models exist inside a family**, their context window, footprint, or which backends/quantizations actually run them. Roadmap Phase 3 adds that layer down — as real, queryable reference data, still no complex logic.

## Scope

### In Scope

| Type | Shape |
|---|---|
| `PublishedModelName` | `value: str` — published identity (`"Qwen/Qwen3-8B"`). Deliberately **not** named `ModelId`: it carries no resolution proof, unlike `execution/ids.py`'s `ObjectId`. |
| `ModelDescriptor` | `name`, `family: ModelFamily`, `parameter_count`, `context_window`, `serving: frozenset[BackendSupport]` |
| `BackendSupport` | `backend: BackendId`, `quantizations: frozenset[Quantization]`, `min_vram_bytes` — footprint is a function of quantization, so it lives here, not on the model |
| `ModelCatalog` | immutable, in-memory, built from a static entry table |
| `family_of(name) -> ModelFamily` | the archived Family Label Convention promoted from test regex to a real function (its purity rule 5 named this change as the caller) |

**Queries**: `families()` · `models(family)` · `get(name)` · `supports(name, backend)` · `quantizations(name, backend)` · `requirements(name, backend, quantization)`. Reused `Quantization`/`BackendId`/`ModelFamily` — no parallel vocabulary.

Entries for all seven advertised capability families.

### Explicitly NOT Done (the boundary)

- **No `ResolvedModelRef`.** No catalog type carries `ObjectId`/`ObjectVersion`/`ContentHash`; no query accepts or returns one. Resolution needs a metadata/tag query on tibios-core's Object Store — verified still absent (`23-object-store.md` §Object Queries lists only identity operations; `tibios-core/openspec/changes/proto-worker-contract/` has landed nothing here).
- **No Object Store integration**, no `ModelSelectionPolicy` implementation, no `worker.py` wiring, no `choose`/`best` query (that is selection, not catalog).
- **Does not replace `CapabilityDescriptor.families`** — descriptors stay the sole outward advertisement; the catalog is inward reference data. No Provider gains a catalog reference.

### Honest consumer statement

**Zero production callers.** The only consumer in this change is a test-level consistency check between catalog and descriptors. The catalog is inert, verified data until resolution unblocks.

## Non-Goals

All `ray-worker-runtime` non-goals carry forward (dynamic plugins, marketplace, hot-reload, auto-discovery, benchmark policies, multi-model routing, agent frameworks). Also: benchmark/quality metrics, pricing, download/caching, unifying Phase 2's conformance harness onto `family_of`.

## Capabilities

### New Capabilities

- `model-catalog`: catalog data model, query surface, FLC derivation, and the catalog↔descriptor consistency invariants.

### Modified Capabilities

- None. Foundation specs stay frozen; no descriptor changes.

## Approach

New leaf package `src/tibios_ray/catalog/`, one-way dependency `catalog -> capabilities -> selection -> backends`; nothing imports `catalog/` (AST guard, same pattern as the existing `capabilities/`↛`runtime/` guard). Frozen, slotted, kw-only dataclasses. Strict TDD.

**Delivery (`auto-chain`)** — one slice per seam, each ≤400 lines: (1) types + `family_of` + query surface; (2) chat families; (3) embedding + rerank; (4) vision; (5) speech + OCR; (6) consistency harness.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `src/tibios_ray/catalog/{model,names,catalog}.py` | New | Value types, FLC, query surface |
| `src/tibios_ray/catalog/entries/*.py` | New | Static entry tables per capability group |
| `tests/unit/catalog/**` | New | Per-group data + shared invariant harness |
| `src/tibios_ray/capabilities/`, `selection/`, `worker.py` | Untouched | Deliberately no wiring |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Object Store metadata query still absent cross-repo | High | Catalog keyed by published name, never `ObjectId`; asserted by test — this change does not depend on it |
| Catalog data drifts from upstream reality | High | Tests assert shape and internal consistency, never external truth or exhaustiveness (Phase 2 precedent) |
| `min_vram_bytes` figures are estimates | Med | Documented as advisory with derivation noted; nothing makes an admission decision from it here |
| Scope creep into selection | Med | No `choose`/`best` query; no policy implementation; verify phase checks |
| Catalog contradicts advertised descriptors | Med | Two-way consistency test: every advertised family has ≥1 entry; every entry's backends ⊆ that family's advertised backends |
| Import cycle via `ModelFamily` | Low | One-way edge, AST-guarded |

## Rollback Plan

Purely additive: new package, new tests, no edit to existing modules. `git revert` of the slice commits restores the archived `capability-providers` state exactly. No data, schema, or contract migration exists.

## Dependencies

- `ray-worker-runtime`, `capability-providers` (archived) — **satisfied**.
- `proto-worker-contract` (tibios-core) — **not blocking**; nothing here is transport-facing.
- Object Store metadata/tag query — **open, and explicitly not depended upon**.

## Success Criteria

- [ ] `ModelDescriptor` exists per concrete model, carrying family, context window, per-backend quantizations and min VRAM
- [ ] All six queries answer from catalog data with no hardcoded branch per family
- [ ] No catalog type has an `ObjectId`/`ObjectVersion`/`ContentHash` field; no query accepts or returns a `ResolvedModelRef` — asserted by test
- [ ] `entry.family == family_of(entry.name)` holds for every entry
- [ ] Every family advertised by the seven Providers has ≥1 entry; every entry's backends ⊆ that family's advertised backends
- [ ] No module outside `catalog/` and its tests imports `catalog/`
- [ ] No `ModelSelectionPolicy` implementation and no Object Store call introduced
- [ ] Delivered as chained slices, each ≤400 changed lines
