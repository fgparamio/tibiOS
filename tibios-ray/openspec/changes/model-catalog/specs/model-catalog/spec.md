# Model Catalog Specification

## Purpose

Records which concrete models exist inside each advertised `ModelFamily` — parameter count, context window, and which backends/quantizations actually serve them — as static, in-memory, queryable reference data. Inert: verified for internal and catalog↔descriptor consistency, with zero production callers until Object Store metadata resolution unblocks selection.

## Requirements

### Requirement: Catalog Value Types

The system MUST define `PublishedModelName`, `ModelDescriptor`, and `BackendSupport` as frozen, slotted, kw-only dataclasses:

| Type | Fields |
|---|---|
| `PublishedModelName` | `value: str` — published identity, e.g. `"Qwen/Qwen3-8B"`; not named `ModelId`, carries no resolution proof |
| `ModelDescriptor` | `name: PublishedModelName`, `family: ModelFamily`, `parameter_count`, `context_window`, `serving: frozenset[BackendSupport]` |
| `BackendSupport` | `backend: BackendId`, `quantizations: frozenset[Quantization]`, `min_vram_bytes` |

#### Scenario: PublishedModelName carries no resolution proof
- GIVEN `PublishedModelName("Qwen/Qwen3-8B")`
- WHEN inspected
- THEN it declares a single `value: str` field and no other field

#### Scenario: Footprint varies independently per backend
- GIVEN a `ModelDescriptor` whose `serving` has two `BackendSupport` entries
- WHEN each entry is read
- THEN `min_vram_bytes` and `quantizations` differ per `backend` without affecting the other entry

### Requirement: family_of Derivation Function

The system MUST expose `family_of(name: PublishedModelName) -> ModelFamily`, a pure function implementing the archived Family Label Convention (drop org/version/size/quantization/tuning-stage tokens; keep remaining published tokens joined by `_`), promoted from test-only regex to production code.

#### Scenario: family_of derives the label from the published lineage name
- GIVEN `PublishedModelName("Qwen/Qwen3-8B-Instruct")`
- WHEN `family_of` is called
- THEN it returns `ModelFamily("qwen")`

#### Scenario: family_of is pure
- GIVEN two separate calls to `family_of` with the same `PublishedModelName`
- WHEN both are called, regardless of catalog contents
- THEN both return an equal `ModelFamily`

### Requirement: ModelCatalog Query Surface

`ModelCatalog` MUST be immutable and built once from a static entry table. It MUST expose exactly six queries — `families()`, `models(family)`, `get(name)`, `supports(name, backend)`, `quantizations(name, backend)`, `requirements(name, backend, quantization)` — each answering from entry data with no hardcoded per-family branch.

#### Scenario: families lists every family with at least one entry
- GIVEN a populated `ModelCatalog`
- WHEN `families()` is called
- THEN it returns every distinct `ModelFamily` present across catalog entries, none absent

#### Scenario: get returns None for an unknown name
- GIVEN a `ModelCatalog`
- WHEN `get(PublishedModelName("unknown/model"))` is called
- THEN it returns `None`, not an exception

#### Scenario: requirements answers footprint for one backend+quantization pair
- GIVEN an entry with a `BackendSupport` for a given backend and quantization
- WHEN `requirements(name, backend, quantization)` is called with that exact pair
- THEN it returns that pair's `min_vram_bytes`

### Requirement: No ResolvedModelRef, No Object Identity Leakage

No catalog type MUST declare an `ObjectId`, `ObjectVersion`, or `ContentHash` field; no catalog query MUST accept or return a `ResolvedModelRef`. This MUST be structurally impossible — no field or parameter slot exists to carry one — the same enforcement style as `selection/policy.py`'s `ModelSelectionPolicy.plan()` guard against a bare family string.

#### Scenario: No catalog dataclass field is Object-Store-identity-typed
- GIVEN `PublishedModelName`, `ModelDescriptor`, `BackendSupport`
- WHEN their field type annotations are inspected
- THEN none is `ObjectId`, `ObjectVersion`, or `ContentHash`

#### Scenario: No query signature accepts or returns ResolvedModelRef
- GIVEN `ModelCatalog`'s six query methods
- WHEN their parameter and return type annotations are inspected
- THEN none references `ResolvedModelRef`

### Requirement: Catalog-Descriptor Consistency

Every `ModelFamily` advertised in `CapabilityDescriptor.families` by the six capability modules (`chat`, `embedding`, `rerank`, `vision`, `speech`, `ocr`) MUST have at least one catalog entry. Every catalog entry's `BackendSupport.backend` set MUST be a subset of the advertised `CapabilityDescriptor.backends` for that entry's family.

#### Scenario: Every advertised family resolves to a catalog entry
- GIVEN the union of families advertised across the six capability modules' descriptors
- WHEN each family is looked up via `models(family)`
- THEN each call returns at least one `ModelDescriptor`

#### Scenario: Entry backends never exceed the family's advertised backends
- GIVEN a `ModelDescriptor` and the `CapabilityDescriptor` of the module advertising its family
- WHEN the descriptor's `serving` backends are compared to the module's `backends`
- THEN every serving backend is a member of the module's advertised backends

### Requirement: No Production Wiring

The catalog MUST NOT be imported by `capabilities/`, `selection/`, or `worker.py` in this change; its only consumer MUST be the consistency checks above.

#### Scenario: No module outside catalog/ and its tests imports catalog/
- GIVEN the source tree after this change
- WHEN imports are traced from `capabilities/`, `selection/`, and `worker.py`
- THEN none resolves to `tibios_ray.catalog`
