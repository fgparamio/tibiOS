# Tasks: Model Catalog

## TDD Commit Convention (applies to every task below)

Every unit of work in this change lands as **two separate commits**: one committing only the failing test(s) (RED), a second committing the implementation that turns it GREEN. This is `sdd-apply`'s responsibility to enforce per unit of work — it is not repeated as a checklist item under each task below.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~2190 total (per design's Module/Slice Plan), ~170-390 per slice |
| 400-line budget risk | Low per slice / High if delivered as one PR |
| Chained PRs recommended | Yes |
| Suggested split | PR1 names+FLC -> PR2 types+query surface -> PR3 chat A -> PR4 chat B -> PR5 embedding+rerank -> PR6 vision -> PR7 speech+ocr -> PR8 assembly+consistency |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Low (slice 2 estimated ~390, near the ceiling; documented 2a/2b fallback split below if it exceeds 400 in practice)

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | `names` + FLC | PR 1 | base=main; no deps; must land first — `ModelCatalog.__init__` (unit 2) calls `family_of` to enforce `FamilyMismatchError` |
| 2 | types + query surface | PR 2 | base=PR1; split into 2a (`model.py` + `_by_name`/`_by_family` indices: `__init__`/`families`/`models`/`get`)/2b (`_footprints` index: `supports`/`quantizations`/`requirements` + both resolution-type guards + pyright fixture) if the diff exceeds ~400 lines |
| 3 | chat A: qwen, llama, deepseek | PR 3 | base=PR2 |
| 4 | chat B: gemma, mistral, kimi | PR 4 | base=PR3; appends to the same `entries/chat.py` — sequential in a stacked chain, so a rebase-clean append, not a conflict surface |
| 5 | embedding + rerank | PR 5 | base=PR4 |
| 6 | vision | PR 6 | base=PR5 |
| 7 | speech + OCR | PR 7 | base=PR6 |
| 8 | assembly + consistency | PR 8 | base=PR7; final slice — unions all entries into `DEFAULT_CATALOG`, adds the catalog↔descriptor consistency harness |

### Traceability — spec Requirement to slice

| Spec Requirement | Landed in |
|---|---|
| Catalog Value Types (`PublishedModelName`) | Slice 1 |
| `family_of` Derivation Function | Slice 1 |
| Catalog Value Types (`ModelDescriptor`, `BackendSupport`) | Slice 2 |
| `ModelCatalog` Query Surface | Slice 2 |
| No `ResolvedModelRef`, No Object Identity Leakage | Slice 1 (layering) + Slice 2 (type-surface + pyright guards) |
| No Production Wiring | Slice 1 (layering-in/out AST guards) + Slice 8 (full-suite confirmation) |
| Catalog-Descriptor Consistency | Slice 8 (data prerequisites land slices 3-7) |

## Phase 1: `names` + FLC (PR 1)

- [x] 1.1 `catalog/errors.py`: `CatalogError` base + six concrete subclasses — `FamilyDerivationError`, `UnknownModelError`, `UnsupportedServingError` (query-time); `DuplicateModelError`, `FamilyMismatchError`, `AmbiguousFootprintError` (construction-time) — each carries typed payload (offending `PublishedModelName`, and for serving errors the `BackendId`/`Quantization`), never a bare message (MC6/MC9's error contract, used by both slice 1 and slice 2)
- [x] 1.2 `catalog/names.py`: `PublishedModelName` — frozen, slotted, single-field, **positional** (not kw-only, per MC1) dataclass — satisfies spec Requirement "Catalog Value Types" for `PublishedModelName` and Scenario "PublishedModelName carries no resolution proof"
- [x] 1.3 `catalog/names.py`: `family_of(name: PublishedModelName) -> ModelFamily` — token tables (`_SEPARATORS`, `_FUSED_VERSION`, `_VERSION_TOKEN`, `_SIZE_TOKEN`, `_QUANT_TOKEN`, `_TAIL_VERSION_MARK`, `_FLC_SHAPE`, `_DROPPED_TOKENS`), `_tokenize`, `_is_dropped`, and the four-phase algorithm (strip org prefix, tokenise with MC4's alpha->digit split guard, unconditional drop, MC3's head rule + tail version marks) exactly as specified in `design.md`'s "The FLC in production" section — satisfies spec Requirement "family_of Derivation Function"
- [x] 1.4 `tests/unit/catalog/test_names.py`: parametrized table covering all 14 archived FLC derivations plus the 6 generalisation cases design.md verified (`Qwen3-30B-A3B`, `Kimi-K2-Instruct`, `Mistral-Small-3.2-24B-Instruct-2506`, `whisper-large-v3-turbo`, `e5-large-v2`, `Mixtral-8x7B-Instruct-v0.1`), each case with an `id` naming the model — satisfies Scenario "family_of derives the label from the published lineage name"
- [x] 1.5 `tests/unit/catalog/test_names.py`: negative cases — `family_of` raises `FamilyDerivationError` for `""`, `"openai/"`, `"large-v3"` (every token dropped), `"7B"`; plus a property-style assertion that every produced label satisfies both `_FLC_SHAPE` and the banned-token check — proves `family_of` never silently guesses on a name it cannot cleanly derive, and satisfies Scenario "family_of is pure"
- [x] 1.6 `tests/unit/catalog/test_names.py`: documentation-in-test note (comment, not a runtime assertion) recording that `meta-llama/Meta-Llama-3.1-8B-Instruct` (-> `meta_llama`) and `deepseek-ai/DeepSeek-R1-Distill-Qwen-32B` (-> `deepseek_qwen`) **do** derive cleanly via `family_of` — they are not `FamilyDerivationError` cases — but are deliberately excluded from the catalog entries built in slices 3-4 for reasons unrelated to derivability (vendor-echoed org token; cross-lineage distill has no single truthful family), per `design.md`'s Open Questions. Prevents a future contributor from "fixing" this by adding either as an entry.
- [x] 1.7 `tests/unit/catalog/test_errors.py`: each of the six `CatalogError` subclasses carries its typed payload, not a bare message
- [x] 1.8 `catalog/__init__.py`: re-export `PublishedModelName`, `family_of`, `CatalogError` + the six subclasses — explicitly **not** `entries` (architecture note: `__init__.py` re-exports types, `family_of`, `ModelCatalog`, errors — never entry data)
- [x] 1.9 `tests/unit/catalog/test_layering.py`: layering-out AST guard — no `Import`/`ImportFrom` under `src/tibios_ray/catalog/**/*.py` names `tibios_ray.execution` or `tibios_ray.runtime` — satisfies spec Requirement "No ResolvedModelRef, No Object Identity Leakage" at the module-graph level
- [x] 1.10 `tests/unit/catalog/test_layering.py`: layering-in AST guard — no module under `src/tibios_ray/**/*.py` **outside** `catalog/` imports `tibios_ray.catalog` — satisfies spec Requirement "No Production Wiring" Scenario "No module outside catalog/ and its tests imports catalog/"; meaningful from this slice onward even though `catalog/` has almost no public surface yet
- [x] 1.11 `tests/unit/catalog/test_layering.py`: package-root import guard — no module under `catalog/` imports `tibios_ray.catalog` itself (CP8's circular-init hazard rule, reused verbatim)
- [x] 1.12 `uv run pytest && uv run ruff check && uv run pyright` from `tibios-ray/` — confirm slice green before opening PR 1

## Phase 2: types + query surface (PR 2) — COMPLETE

Delivered as the documented 2a/2b fallback split (diff exceeded ~400
lines as a single PR): **2a** (`model.py` + `_by_name`/`_by_family`
indices + `families`/`models`/`get` + duplicate/family-mismatch
invariants, ~393 changed lines) and **2b** (`_footprints` index +
`AmbiguousFootprintError` + `supports`/`quantizations`/`requirements` +
both resolution-type guards + pyright fixture, ~359 changed lines).

- [x] 2.1 `catalog/model.py`: `BackendSupport` — frozen, slotted, kw-only — `backend: BackendId`, `quantizations: frozenset[Quantization]`, `min_vram_bytes: int`. Reflects design decision MC5: `BackendSupport` is keyed by **(backend, footprint tier)**, not by backend alone — `ModelDescriptor.serving` may hold several `BackendSupport` rows for the same `BackendId` (e.g. one row for `q4_k_m`, another for `q8_0` on `llama_cpp`) — satisfies spec Requirement "Catalog Value Types" for `BackendSupport`
- [x] 2.2 `catalog/model.py`: `ModelDescriptor` — frozen, slotted, kw-only — `name`, `family`, `parameter_count`, `context_window`, `serving: frozenset[BackendSupport]` — satisfies spec Requirement "Catalog Value Types" for `ModelDescriptor`
- [x] 2.3 `tests/unit/catalog/test_model.py`: RED-first construction tests for `BackendSupport`/`ModelDescriptor` — frozen+slotted, and explicitly the MC5 shape: two `BackendSupport` rows sharing one `BackendId` with different `quantizations`/`min_vram_bytes` and no crosstalk between them — satisfies Scenario "Footprint varies independently per backend"
- [x] 2.4 `catalog/catalog.py`: `ModelCatalog.__init__(entries)` — builds `_by_name`, `_by_family`, `_footprints` indices, each wrapped in `MappingProxyType`; enforces the three construction-time invariants: no duplicate `PublishedModelName` -> `DuplicateModelError`; `entry.family == family_of(entry.name)` -> `FamilyMismatchError`; no `(backend, quantization)` pair repeated across two `BackendSupport` rows of one entry -> `AmbiguousFootprintError`
- [x] 2.5 `catalog/catalog.py`: `families() -> frozenset[ModelFamily]` — satisfies Scenario "families lists every family with at least one entry"
- [x] 2.6 `catalog/catalog.py`: `models(family) -> tuple[ModelDescriptor, ...]`, ordered by `name.value`, empty tuple for an unknown family (MC7's asymmetric error contract — "which models are in X" has an honest empty answer)
- [x] 2.7 `catalog/catalog.py`: `get(name) -> ModelDescriptor`, raises `UnknownModelError` for an unknown name (MC7: an identity lookup's absence is a caller error, mirroring `CapabilityRegistry.resolve`). Note: design.md's contract deliberately supersedes the spec text's "returns `None`" phrasing for this one query (see Key Contracts / MC7) — implemented per design; this spec-text/design divergence is recorded here explicitly so `sdd-verify` treats it as a documented decision, not a silent contradiction.
- [x] 2.8 `catalog/catalog.py`: `supports(name, backend) -> bool` — `False` for a known model on an unadvertised backend, `UnknownModelError` for an unknown model
- [x] 2.9 `catalog/catalog.py`: `quantizations(name, backend) -> frozenset[Quantization]` — union across every `BackendSupport` row for that backend; empty when `supports()` is `False`; `UnknownModelError` for an unknown model
- [x] 2.10 `catalog/catalog.py`: `requirements(name, backend, quantization) -> int` — pure lookup against `_footprints`, no arithmetic (MC5); raises `UnsupportedServingError` when the exact triple is not in the model's serving table — satisfies Scenario "requirements answers footprint for one backend+quantization pair"
- [x] 2.11 `tests/unit/catalog/test_catalog.py`: fabricated three-entry fixture catalog (not real data — query semantics and catalog data must fail independently) with one model carrying two tiers on one backend and one model absent from a backend, covering all six queries; plus one test per construction invariant — duplicate name -> `DuplicateModelError`; `ModelDescriptor(name=PublishedModelName("Qwen/Qwen3-8B"), family=ModelFamily("llama"), ...)` -> `FamilyMismatchError`; two `BackendSupport` rows sharing `(vllm, fp16)` -> `AmbiguousFootprintError`. The `FamilyMismatchError` case is the catalog-construction-level counterpart to slice 1's `family_of`-level `FamilyDerivationError` coverage — together they prove the catalog never silently accepts an unresolvable or mismatched name.
- [x] 2.12 `tests/unit/catalog/test_no_resolution_types.py`: generic introspection guard (MC9 — never a hardcoded `"ObjectId"` string check) — for every public class in `catalog/`, every `dataclasses.fields()` annotation resolved via `typing.get_type_hints`, unwrapped through `frozenset`/`tuple`/`Mapping` args, asserts none has `__module__.startswith("tibios_ray.execution")` — satisfies Scenario "No catalog dataclass field is Object-Store-identity-typed"
- [x] 2.13 `tests/unit/catalog/test_no_resolution_types.py`: same guard applied via `inspect.signature` to every public `ModelCatalog` method's parameters and return annotation — satisfies Scenario "No query signature accepts or returns ResolvedModelRef"
- [x] 2.14 `tests/unit/catalog/test_no_resolution_types.py`: no callable in `catalog/` named `choose`/`best`/`select`/`plan`; no class in `catalog/` structurally satisfying `ModelSelectionPolicy` (name-set comparison, since the protocol is not `runtime_checkable`) — reinforces the proposal's "no choose/best query" boundary
- [x] 2.15 `tests/unit/catalog/pyright_fixtures/rejects_resolved_model_ref.py`: `catalog.get(resolved_ref)  # type: ignore[arg-type]` plus a no-ignore control `catalog.get(PublishedModelName(...))`, mirroring `tests/unit/selection/pyright_fixtures/rejects_bare_family_string.py`'s pattern; relies on `pyproject.toml`'s existing `reportUnnecessaryTypeIgnoreComment = true` — closes the static half of MC9
- [x] 2.16 `catalog/__init__.py`: update re-exports to add `ModelDescriptor`, `BackendSupport`, `ModelCatalog` (still not `entries`)
- [x] 2.17 `uv run pytest && uv run ruff check && uv run pyright` — confirm slice green. Diff exceeded ~400 changed lines as a single PR, so split per the documented fallback: **2a** = `model.py` + `ModelCatalog.__init__`/`families`/`models`/`get` (the `_by_name`/`_by_family` indices) + tasks 2.1-2.3, 2.4 (partial: duplicate+family-mismatch invariants only), 2.5-2.7, and their tests (~393 lines, commits 232af1c/f811453/f9fd2ea); **2b** = `supports`/`quantizations`/`requirements` (the `_footprints` index, including the `AmbiguousFootprintError` invariant) + both resolution-type guards + the pyright fixture (tasks 2.8-2.15) (~359 lines, commits 07649c9/144e844). 378/378 tests passing, ruff clean, pyright clean.

## Phase 3: chat A — qwen, llama, deepseek (PR 3) — COMPLETE

- [x] 3.1 `catalog/entries/chat.py`: `qwen` family — 5 entries (`Qwen/Qwen3-8B` as the deliberate five-row flagship exercising every `BackendSupport` shape the type permits; `Qwen3-14B`, `Qwen3-32B`, `Qwen3-30B-A3B`, `Qwen2.5-7B-Instruct`) with the exact params/context/serving-row data from `design.md`'s Reference Data table
- [x] 3.2 `catalog/entries/chat.py`: `llama` family — 3 entries (`meta-llama/Llama-3.1-8B-Instruct` — the **canonical** form, not `Meta-Llama-3.1-8B-Instruct`; `Llama-3.3-70B-Instruct`; `Llama-3.2-3B-Instruct`)
- [x] 3.3 `catalog/entries/chat.py`: `deepseek` family — 2 entries (`DeepSeek-V3`, `DeepSeek-R1`), no `llama_cpp` row (a 671B model is multi-node; claiming single-GPU GGUF support would be catalog fiction). Deliberately excludes `deepseek-ai/DeepSeek-R1-Distill-Qwen-32B` — see task 1.6.
- [x] 3.4 `tests/unit/catalog/test_chat_entries.py`: RED-first — local `ModelCatalog(CHAT_ENTRIES)` fixture scoped to this slice's own data (MC14 — shared `entries/__init__.py` assembly is deferred to slice 8); family coverage for `qwen`/`llama`/`deepseek`; one full `ModelDescriptor` equality per family as the stability assertion; derivation round-trip `entry.family == family_of(entry.name)` for every name in this slice
- [x] 3.5 `uv run pytest && uv run ruff check && uv run pyright` — confirm slice green

## Phase 4: chat B — gemma, mistral, kimi (PR 4) — COMPLETE

- [x] 4.1 `catalog/entries/chat.py` (append): `gemma` family — 3 entries (`gemma-3-4b-it`, `gemma-3-12b-it`, `gemma-3-27b-it`). These three rows are also the *entire* `gemma` answer for `vision.understand` (MC8/MC12) — `entries/vision.py` (slice 6) must not restate them.
- [x] 4.2 `catalog/entries/chat.py` (append): `mistral` family — 2 entries (`Mistral-7B-Instruct-v0.3`, `Mistral-Small-3.2-24B-Instruct-2506`)
- [x] 4.3 `catalog/entries/chat.py` (append): `kimi` family — 1 entry (`Kimi-K2-Instruct`), satisfying "≥1 entry per advertised family". `moonshotai/Kimi-VL-A3B-Instruct` (-> `kimi_vl`) is intentionally out of scope — no Provider advertises `kimi_vl`.
- [x] 4.4 `tests/unit/catalog/test_chat_entries.py`: extend with `gemma`/`mistral`/`kimi` coverage, same pattern as 3.4 (family coverage, one full-equality stability assertion per family, derivation round-trip)
- [x] 4.5 `uv run pytest && uv run ruff check && uv run pyright` — confirm slice green

## Phase 5: embedding + rerank (PR 5)

- [x] 5.1 `catalog/entries/embedding.py`: `bge` (`BAAI/bge-m3`, `BAAI/bge-large-en-v1.5`), `nomic_embed` (`nomic-ai/nomic-embed-text-v1.5`), `e5` (`intfloat/multilingual-e5-large`, `intfloat/e5-large-v2`), `jina_embeddings` (`jinaai/jina-embeddings-v3`) — footprint figures per MC13's formula (`ceil_gib(parameter_count × bits/8 × 1.2)`)
- [x] 5.2 `catalog/entries/rerank.py`: `bge_reranker` (`BAAI/bge-reranker-v2-m3`), `jina_reranker` (`jinaai/jina-reranker-v2-base-multilingual`)
- [x] 5.3 `tests/unit/catalog/test_embedding_entries.py`: RED-first — local `ModelCatalog(EMBEDDING_ENTRIES)` fixture, family coverage for `bge`/`nomic_embed`/`e5`/`jina_embeddings`, one full-equality stability assertion per family, derivation round-trip
- [x] 5.4 `tests/unit/catalog/test_rerank_entries.py`: same pattern for `bge_reranker`/`jina_reranker`
- [x] 5.5 `uv run pytest && uv run ruff check && uv run pyright` — confirm slice green

## Phase 6: vision (PR 6) — COMPLETE

- [x] 6.1 `catalog/entries/vision.py`: `qwen_vl` (`Qwen/Qwen2.5-VL-7B-Instruct`, `Qwen/Qwen2.5-VL-72B-Instruct`), `llama_vision` (`meta-llama/Llama-3.2-11B-Vision-Instruct`) — this module holds **only** these two families (MC12); `gemma`'s vision answer already exists in `entries/chat.py` (slice 4) and is not duplicated here. Note: `design.md`'s worked Reference data table does **not** cover `qwen_vl`/`llama_vision` (only names, line 400) — figures were derived from MC13's formula using the decimal-GB interpretation established in slice 5, not copied verbatim.
- [x] 6.2 `tests/unit/catalog/test_vision_entries.py`: RED-first — local `ModelCatalog(VISION_ENTRIES)` fixture, family coverage for `qwen_vl`/`llama_vision`, one full-equality stability assertion per family, derivation round-trip
- [x] 6.3 `uv run pytest && uv run ruff check && uv run pyright` — confirm slice green

## Phase 7: speech + OCR (PR 7) — COMPLETE

- [x] 7.1 `catalog/entries/speech.py`: `whisper` (`openai/whisper-large-v3`, `openai/whisper-large-v3-turbo`), `kokoro` (`hexgrad/Kokoro-82M`). Note: `design.md`'s worked Reference data table does **not** cover `whisper`/`kokoro` (only names, line 400) — figures were derived from MC13's formula using the decimal-GB interpretation established in slice 5, not copied verbatim (verified directly against design.md before writing any code, not assumed from slice 6's situation).
- [x] 7.2 `catalog/entries/ocr.py`: `paddleocr` (`PaddlePaddle/PaddleOCR`) — same derive situation as 7.1.
- [x] 7.3 `tests/unit/catalog/test_speech_entries.py` + `tests/unit/catalog/test_ocr_entries.py`: RED-first — local `ModelCatalog` fixtures, family coverage, one full-equality stability assertion per family, derivation round-trip
- [x] 7.4 `uv run pytest && uv run ruff check && uv run pyright` — confirm slice green

## Phase 8: assembly + consistency (PR 8) — COMPLETE

- [x] 8.1 `catalog/entries/__init__.py`: `ALL_ENTRIES` — the union of every group's `*_ENTRIES` tuple (`CHAT_ENTRIES`, `EMBEDDING_ENTRIES`, `RERANK_ENTRIES`, `VISION_ENTRIES`, `SPEECH_ENTRIES`, `OCR_ENTRIES`), per MC14 — assembled last so slices 3-7 touched no shared file
- [x] 8.2 `catalog/entries/__init__.py`: `DEFAULT_CATALOG = ModelCatalog(ALL_ENTRIES)` — the union's construction validates all three invariants (no duplicate name, `family_of` match, no ambiguous footprint) across the full dataset at import time
- [x] 8.3 `catalog/__init__.py`: confirm final re-export surface still does **not** include anything from `entries/` — `entries/` stays unreachable from the package root's public surface
- [x] 8.4 `tests/unit/catalog/test_catalog_consistency.py`: `_advertised()` — discover `CapabilityDescriptor` instances via `pkgutil.iter_modules(tibios_ray.capabilities.__path__)` + `importlib`, never a hand-maintained tuple (MC10)
- [x] 8.5 `tests/unit/catalog/test_catalog_consistency.py`: `_advertised_backends(family)` — union over every descriptor advertising that family (MC8)
- [x] 8.6 `tests/unit/catalog/test_catalog_consistency.py`: descriptor -> catalog direction — parametrized over all 17 distinct advertised `ModelFamily` values (`id=family.value`): `DEFAULT_CATALOG.models(family)` is non-empty — satisfies spec Requirement "Catalog-Descriptor Consistency" Scenario "Every advertised family resolves to a catalog entry"
- [x] 8.7 `tests/unit/catalog/test_catalog_consistency.py`: catalog -> descriptor direction — parametrized over every entry in `ALL_ENTRIES` (`id=entry.name.value`): `{row.backend for row in entry.serving} <= _advertised_backends(entry.family)`; `entry.family in advertised_families`; `entry.family == family_of(entry.name)`; `entry.serving` non-empty; `parameter_count > 0`; `context_window > 0`; every `min_vram_bytes > 0` — satisfies Scenario "Entry backends never exceed the family's advertised backends", and is stricter than the proposal's bare minimum by also requiring `entry.family in advertised_families` (dead data with no reachable query path is caught for free)
- [x] 8.8 `tests/unit/catalog/test_catalog_consistency.py`: harness sanity check — `len(_advertised()) == 7` and the seven capability strings match the archived set exactly, so a Provider deleted or renamed upstream fails here rather than silently shrinking the parametrization to nothing
- [x] 8.9 `uv run pytest && uv run ruff check && uv run pyright` from `tibios-ray/` — full suite green, confirming spec Requirement "No Production Wiring" end-to-end (slice 1's layering guards plus this slice's consistency harness together)
- [x] 8.10 Cross-check the delivered slices against `proposal.md`'s Success Criteria checklist (lines 85-92) one item at a time before recommending `sdd-verify`

## Post-verify addendum: closed all 3 WARNINGs (closes sdd-verify WARNING #1, #2, #3)

All 8 phases above were already 100% complete when `sdd-verify` ran (`sdd/model-catalog/verify-report`, PASS WITH WARNINGS, zero CRITICAL findings). Three WARNING-level findings were closed here without reopening or renumbering Phase 1-8.

- [x] A.1 (closes WARNING #1 — misleading field name) Renamed `BackendSupport.min_vram_bytes` to `min_vram_gb` across `catalog/model.py`, all six entry files (`catalog/entries/{chat,embedding,rerank,vision,speech,ocr}.py`), `catalog/catalog.py`'s `requirements()` lookup, and every referencing test (`test_model.py`, `test_catalog.py`, `test_chat_entries.py`, `test_embedding_entries.py`, `test_rerank_entries.py`, `test_vision_entries.py`, `test_speech_entries.py`, `test_ocr_entries.py`, `test_catalog_consistency.py`). The field always stored a ceiling decimal-GB count (MC13's formula), never raw bytes. Mechanical rename, no behavior change — confirmed zero `min_vram_bytes` occurrences remain in `src/` or `tests/` via `rg`; `proposal.md`/`design.md`/`spec.md`'s own historical mentions of the old name were deliberately left untouched, same as an already-archived change's docs would be. `uv run pytest && uv run ruff check && uv run pyright` all green before and after. Commit `462291d`.
- [x] A.2 (closes WARNING #2 — DeepSeek fp8 off-by-one) Recomputed DeepSeek-V3/R1's fp8 footprint directly: `ceil(671_000_000_000 * 8/8 * 1.2 / 1e9) = ceil(805.2) = 806`, confirming `805` was an off-by-one against MC13's own formula (an authoring-time slip in `design.md`'s worked reference table, faithfully copied into `chat.py`). Two-commit RED/GREEN discipline: RED (`30ca654`) updated `test_chat_entries.py::TestStabilityAssertions::test_deepseek_v3_full_equality`'s expected value to `806` and confirmed it failed against the still-`805` data; GREEN (`6ec3cd5`) corrected all four fp8 rows in `catalog/entries/chat.py` (DeepSeek-V3 vllm+tensorrt_llm, DeepSeek-R1 vllm+tensorrt_llm) to `806`. `design.md`'s archived worked table was intentionally left untouched, per the same already-archived-docs convention as A.1. `uv run pytest && uv run ruff check && uv run pyright` all green after GREEN — 722/722.
- [x] A.3 (closes WARNING #3 — stale spec.md scenario) Updated `specs/model-catalog/spec.md`'s "get returns None for an unknown name" scenario to "get raises UnknownModelError for an unknown name", matching the real, already-implemented, deliberate behavior (design decision MC7's asymmetric error contract, task 2.7). Documentation-only — `catalog.py`'s `get()`/`_require()` were already correct; nothing in `src/` changed. Commit `d97ec52`. `uv run pytest && uv run ruff check && uv run pyright` all green — 722/722.

`model-catalog` is ready for `sdd-archive` — zero CRITICAL, zero WARNING, zero open items remain.
