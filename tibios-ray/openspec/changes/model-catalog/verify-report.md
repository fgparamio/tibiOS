# Verification Report: model-catalog

**Change**: model-catalog
**Version**: N/A (spec has no version header)
**Mode**: Strict TDD (verified against apply-progress's per-slice RED/GREEN commit evidence)

---

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 61 |
| Tasks complete `[x]` | 61 |
| Tasks incomplete `[ ]` | 0 |

All 8 phases (names+FLC, types+query surface [2a/2b], chat A, chat B, embedding+rerank, vision, speech+OCR, assembly+consistency) are checked off. `apply-progress` and `tasks.md` agree.

---

## Build & Tests Execution

**Build/Lint/Type-check** (from `tibios-ray/`):
```
uv run pytest      -> 722 passed
uv run ruff check  -> All checks passed!
uv run pyright     -> 0 errors, 0 warnings, 0 informations
```
All Passed - independently re-run, not trusted from apply-progress alone.

**Catalog-scoped tests**: 438 passed across 15 test files under `tests/unit/catalog/`.

**Coverage**: no coverage tool configured for this project (per cached testing capabilities) - not available, not blocking.

---

## TDD Compliance (spot-checked, not merely trusted)

Two of the eight RED/GREEN commit pairs were independently checked out into isolated detached-HEAD sandboxes and executed:

| Slice | RED commit | GREEN commit | RED behavior confirmed | GREEN behavior confirmed |
|---|---|---|---|---|
| Phase 1 (names+FLC) | `95aac97` (+`b6a9505` fixup, both test-only) | `53eb421` | `ModuleNotFoundError: No module named 'tibios_ray.catalog'` on collection - genuine failure, not a weak assertion | 63/63 catalog tests pass |
| Phase 6 (vision) | `e6d251c` | `681d75f` | `ModuleNotFoundError: No module named 'tibios_ray.catalog.entries.vision'` on collection | 17/17 vision tests pass |

Both RED commits' diffs were confirmed test-file-only before execution. Sandboxes were removed afterward; the change's home worktree status is clean and back on `4813e12`.

The remaining 6 slices were checked structurally via the commit log (test commit -> feat commit -> docs/checkbox commit pattern holds for every phase, 27 commits total across the change) but not individually re-executed in isolation - spot-check, not exhaustive, per the audit scope requested.

**TDD Compliance**: 2/2 spot-checked pairs confirmed genuine RED->GREEN. No evidence of squashed or fabricated TDD evidence anywhere in the log (in contrast to the `capability-providers` WARNING that motivated this change's two-commit discipline).

---

## Independent Verification of the Nine Flagged Items

### 1. FLC family_of - hand-derivation

Re-derived by hand, independently of the code, using design.md's four-phase algorithm (strip org prefix -> tokenize with MC4's alpha->digit >=2-letter-prefix guard -> unconditional drop -> MC3 head rule + tail-version-mark drop) for: `Qwen/Qwen3-8B-Instruct` -> `qwen`, `intfloat/multilingual-e5-large` -> `e5` (head, kept), `BAAI/bge-m3` -> `bge` (`m3` dropped as a tail version mark). All three match `catalog/names.py`'s actual output and design.md's table exactly, including the e5-keep-vs-m3-drop distinction the algorithm is built to resolve.

Correction to the audit's premise: the two "known non-derivable" names do NOT raise FamilyDerivationError. Hand-derivation of both, cross-checked against `test_names.py`'s `TestFamilyOfDocumentedNonDerivableExclusions` class, confirms:
- `meta-llama/Meta-Llama-3.1-8B-Instruct` derives cleanly to `meta_llama` (no exception)
- `deepseek-ai/DeepSeek-R1-Distill-Qwen-32B` derives cleanly to `deepseek_qwen` (no exception)

Both are excluded from the catalog's entry data by curatorial choice (vendor-echoed org token; cross-lineage distill has no single truthful family), not because family_of rejects them. This is explicitly documented in design.md's Open Questions, tasks.md task 1.6, and pinned by a dedicated test whose docstring literally warns against the exact misreading in the audit brief. Not a defect - the implementation and its own regression test correctly work as designed. Flagged as a SUGGESTION only, to correct the record.

### 2. MC5 - multi-tier BackendSupport

Confirmed in catalog/entries/chat.py: Qwen/Qwen3-8B (the deliberate "five-row flagship") carries two BackendSupport rows for llama_cpp (q4_k_m->5, q8_0->10) and two for vllm (fp16->20, awq/gptq->5) - four distinct rows across two BackendIds, proving ModelDescriptor.serving genuinely supports multiple footprint tiers per backend, not one row per backend. ModelCatalog.__init__'s _footprints index keys on (name, backend, quantization), not (name, backend), which is what makes this representable and query-safe.

### 3. MC7 - get() raises, spec text says "returns None"

Confirmed directly in catalog/catalog.py: get() calls self._require(name), which raises UnknownModelError on a KeyError. This matches design.md's Key Contracts (MC7's asymmetric error contract) exactly, and is a deliberate, recorded decision - tasks.md task 2.7 states it explicitly, and apply-progress carries the same note forward. Not a defect in the implementation. However, spec.md's Scenario "get returns None for an unknown name" was never corrected to match - see WARNING below.

### 4. MC8/MC12 - gemma shared between chat and vision

`rg -n "gemma" src/tibios_ray/catalog/entries/vision.py` returns only prose-comment mentions (explaining the omission), zero BackendSupport/ModelDescriptor entries for gemma in that file - confirmed directly. entries/chat.py holds all three gemma entries. The assembled DEFAULT_CATALOG (Phase 8) is proven, not merely assumed, to resolve gemma correctly for both capabilities: test_catalog_consistency.py's TestAllEntriesAssembly.test_all_entries_has_exactly_one_gemma_entry_set_not_a_duplicate asserts exactly 3 (not 6) gemma entries in ALL_ENTRIES, and _advertised_backends()'s union rule is exercised end-to-end by TestCatalogToDescriptor over every entry including gemma's three.

### 5. MC9 - structural guard, mutation-tested

Read tests/unit/catalog/test_no_resolution_types.py in full. Mutation test performed: temporarily added `mutation_probe: ResolvedModelRef | None = None` to BackendSupport in catalog/model.py (importing ResolvedModelRef from execution/context.py). Result: TestNoResolutionTypesInDataclassFields::test_no_public_catalog_dataclass_field_is_execution_typed failed exactly as expected, reporting the offending field precisely. Reverted via a pre-mutation backup; the guard tests all pass again post-revert and there is no residual diff. The guard is real, not decorative.

### 6. MC13 - derivation formula consistency

Hand-recomputed footprint figures using the convention apply-progress documents as reverse-engineered in Phase 5 - decimal GB via ceil(parameter_count x bits/8 x 1.2 / 1e9) (not binary GiB, despite design.md's worked table labeling values "GiB" and the field being named min_vram_bytes). Spot-checked and matched exactly: all embedding.py entries (bge, bge-large, nomic_embed, both e5 entries, jina_embeddings - 8 rows), all vision.py entries (qwen_vl x2, llama_vision - 7 rows), all speech.py entries (whisper x2, kokoro - 5 rows), ocr.py's paddleocr (1 row), and most of chat.py (Qwen3-32B, Kimi-K2, Mistral-Small-24B all matched exactly).

One inconsistency found: DeepSeek-V3 and DeepSeek-R1's fp8 tier stores min_vram_bytes=805, but ceil(671_000_000_000 x 1.2 / 1e9) = ceil(805.2) = 806 - an off-by-one against the documented ceiling convention. This originates in design.md's own worked Reference Data table, not in a later phase's derivation - Phase 3 copied it verbatim per its task description, so this is a design-authoring arithmetic slip faithfully reproduced, not an apply-phase bug. See WARNING below.

### 7. Zero production callers - independently re-run

`rg -n "tibios_ray\.catalog" src/tibios_ray --glob '!src/tibios_ray/catalog/**'` - zero matches (exit code 1), confirmed independently, not trusted from Phase 8's report.

### 8. Descriptor-to-catalog consistency harness - mutation-tested

Read tests/unit/catalog/test_catalog_consistency.py in full. Mutation test performed: temporarily removed OCR_ENTRIES from the ALL_ENTRIES union in catalog/entries/__init__.py (simulating an advertised family - paddleocr - with zero catalog entries). Result: TestDescriptorToCatalog::test_every_advertised_family_has_at_least_one_catalog_entry[paddleocr] failed exactly as expected, with 231/232 other parametrized cases still passing (proving the harness pinpoints the exact broken family, not a blanket failure). Reverted; full 722-test suite green again with no residual diff.

### 9. PaddleOCR's flagged uncertain estimates

parameter_count=15_000_000 and context_window=25 - both plausible: 15M is roughly an order of magnitude below every transformer-based entry in the catalog, consistent with the documented rationale. context_window=25 is sourced from a real published config value (max_text_length), not invented. Confirmed the consistency harness only asserts > 0 for both fields - no specific-value assertion exists, matching the claim exactly.

---

## Spec Compliance Matrix

| Requirement | Scenario | Test | Result |
|---|---|---|---|
| Catalog Value Types | PublishedModelName carries no resolution proof | test_names.py::TestPublishedModelNameShape | COMPLIANT |
| Catalog Value Types | Footprint varies independently per backend | test_model.py (two-row, different-tier cases) | COMPLIANT |
| family_of Derivation Function | derives the label from the published lineage name | test_names.py::TestFamilyOfDerivesTheArchivedLabels (20 cases) | COMPLIANT |
| family_of Derivation Function | family_of is pure | test_names.py::TestFamilyOfIsPure | COMPLIANT |
| ModelCatalog Query Surface | families lists every family with at least one entry | test_catalog.py | COMPLIANT |
| ModelCatalog Query Surface | get returns None for an unknown name | test_catalog.py asserts UnknownModelError raised instead | DOCUMENTED DEVIATION (design supersedes spec text deliberately; spec.md text itself stale) |
| ModelCatalog Query Surface | requirements answers footprint for one backend+quantization pair | test_catalog.py::TestRequirements | COMPLIANT |
| No ResolvedModelRef, No Object Identity Leakage | No catalog dataclass field is Object-Store-identity-typed | test_no_resolution_types.py (mutation-tested) | COMPLIANT |
| No ResolvedModelRef, No Object Identity Leakage | No query signature accepts or returns ResolvedModelRef | test_no_resolution_types.py + pyright_fixtures | COMPLIANT |
| Catalog-Descriptor Consistency | Every advertised family resolves to a catalog entry | test_catalog_consistency.py::TestDescriptorToCatalog (mutation-tested) | COMPLIANT |
| Catalog-Descriptor Consistency | Entry backends never exceed the family's advertised backends | test_catalog_consistency.py::TestCatalogToDescriptor | COMPLIANT |
| No Production Wiring | No module outside catalog/ and its tests imports catalog/ | test_layering.py + independent re-run this session | COMPLIANT |

Compliance summary: 11/12 scenarios fully compliant; 1/12 (get on unknown name) is a documented, deliberate design-supersedes-spec-text deviation, not a code defect.

---

## Coherence (Design)

| Decision | Followed? | Notes |
|---|---|---|
| MC1 (PublishedModelName positional, not kw-only) | Yes | confirmed in names.py |
| MC2 (family_of as module function, not method) | Yes | |
| MC3/MC4 (head rule, fused-version split) | Yes | hand-verified |
| MC5 (multi-tier BackendSupport) | Yes | independently confirmed |
| MC6 (ctor-validated class, MappingProxyType indices) | Yes | |
| MC7 (asymmetric error contract) | Yes | independently confirmed |
| MC8 (union-of-backends rule for multi-descriptor families) | Yes | independently confirmed |
| MC9 (generic type introspection guard) | Yes | mutation-tested |
| MC10 (module-introspection descriptor discovery) | Yes | matches design.md verbatim |
| MC11 (FLC constants re-declared, not imported from test) | Yes | |
| MC12 (entries filed by capability group, keyed by family) | Yes | independently confirmed |
| MC13 (stated-data footprint, documented formula) | Mostly | one off-by-one (DeepSeek-V3/R1 fp8: 805 vs 806), see WARNING |
| MC14 (DEFAULT_CATALOG assembled last) | Yes | entries/__init__.py is Phase 8-only, confirmed by commit log |

---

## Issues Found

**CRITICAL** (must fix before archive):
None.

**WARNING** (should fix):

1. min_vram_bytes naming/unit mismatch. The field is named min_vram_bytes (implying a raw byte count) but every stored value across all 31 entries - and the formula apply-progress documents as reverse-engineered in Phase 5 - is actually a decimal-GB count (ceil(bytes / 1e9)), not raw bytes and not true binary GiB either (despite design.md's human-readable tables labeling the same numbers "GiB"). The data is internally self-consistent (verified by hand across every capability group), so nothing is functionally broken today - zero production callers, and the consistency harness only checks > 0. But the field name is actively misleading for any future consumer who reads min_vram_bytes literally as bytes (a 20x under-provisioning risk once this catalog is wired to a real admission decision). Recommend renaming to min_vram_gb (or converting stored values to true bytes) before this catalog gains its first production caller - not necessarily before this archive, since the change's own stated scope is "inert, zero production callers."

2. DeepSeek-V3/DeepSeek-R1's fp8-tier min_vram_bytes=805 is off by one against the documented ceiling formula (ceil(671e9 x 1.2 / 1e9) = 806, not 805). Traced to design.md's own worked Reference Data table, faithfully copied into chat.py by Phase 3 rather than independently recomputed - an authoring-time arithmetic slip, not an apply-phase bug. ~0.02% relative error on advisory-only data with zero consumers; does not affect any test. Trivial one-line fix in chat.py (and design.md's table, for consistency) whenever convenient.

3. spec.md's "get returns None for an unknown name" scenario is stale relative to the actual (and design-intended, and task-documented) UnknownModelError-raising behavior. Not a code defect - a well-recorded, deliberate decision (design.md MC7, tasks.md task 2.7, apply-progress) - but spec.md itself was never edited to match, so a reader of spec.md alone would be misled. Recommend updating spec.md's scenario text at or before archive; pure documentation fix, zero code risk.

**SUGGESTION** (nice to have):

1. The verification brief's premise that meta-llama/Meta-Llama-3.1-8B-Instruct and deepseek-ai/DeepSeek-R1-Distill-Qwen-32B "raise" was independently checked and found incorrect against the actual, deliberately-tested behavior: both derive cleanly (no exception) to meta_llama/deepseek_qwen respectively and are excluded from catalog entries by curatorial choice, not by family_of rejection. The implementation, design.md, tasks.md, and a dedicated test class (whose docstring explicitly anticipates this exact misreading) are all internally consistent and correct on this point. No action needed - noted only to correct the record for future readers of this audit.

---

## Verdict

**PASS WITH WARNINGS**

61/61 tasks complete, 722/722 tests passing, ruff clean, pyright clean. All 8 slices' RED/GREEN discipline holds where spot-checked (2/8, both genuinely red-then-green, isolated via detached-HEAD sandboxes). All nine independently-audited claims about FLC derivation, multi-tier BackendSupport, the get() error contract, gemma's shared-family handling, the MC9 structural guard (mutation-tested), the MC13 footprint formula, zero production callers, the consistency harness (mutation-tested), and PaddleOCR's estimates check out - with three WARNING-level findings (a unit-naming mismatch in min_vram_bytes, a one-entry-pair off-by-one in the footprint formula, and stale spec.md wording for the documented MC7 divergence) and zero CRITICAL findings. None of the three WARNINGs block correctness of the delivered code against its own design and tests; they are pre-existing-data-quality and documentation-freshness items, safe to fix now or immediately after archive at the team's discretion.

Ready for sdd-archive.
