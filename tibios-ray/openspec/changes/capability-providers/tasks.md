# Tasks: The Six Official Capability Providers

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1035 total across 7 slices (~90-250/slice) |
| 400-line budget risk | Low (per-slice) |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 → PR 4 → PR 5 → PR 6 → PR 7 (stacked to main) |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | `errors.py` alone | PR 1 | Base = main. Root of dependency order. |
| 2 | Per-Provider harness + Chat | PR 2 | Base = main (after PR 1 merges). Largest slice (~250 lines) — harness pays for itself here. |
| 3 | Embedding + whole-catalog harness | PR 3 | Base = main. First slice with 2+ Providers — co-registration/union/round-trip stop being vacuous. |
| 4 | Rerank | PR 4 | Base = main. |
| 5 | Vision | PR 5 | Base = main. |
| 6 | Speech (2 classes) | PR 6 | Base = main. |
| 7 | OCR | PR 7 | Base = main. |

Each PR: `uv run pytest && uv run ruff check && uv run pyright`, run from inside `tibios-ray/`. Each `__init__.py` edit is a rebase-clean one-line addition, not a conflict surface.

## Slice 1 — `capabilities/errors.py` (PR 1)

- [x] 1.1 RED: `tests/unit/capabilities/test_errors.py` — assert `NoBackendAvailableError(capability=..., provider=...)` sets `.capability`/`.provider`, has non-empty `str()`, `isinstance(e, Exception)`, `not isinstance(e, DispatchError)` (spec: Binding Invariants)
- [x] 1.2 GREEN: create `src/tibios_ray/capabilities/errors.py` with `NoBackendAvailableError` per design's Key Contracts block (CP2, CP3, CP4)
- [x] 1.3 Update `src/tibios_ray/capabilities/__init__.py` to export `NoBackendAvailableError`; verify `test_capabilities_exports.py` stays green
- [x] 1.4 Verify: `uv run pytest && uv run ruff check && uv run pyright` from `tibios-ray/`

## Slice 2 — Conformance harness + Chat Provider (PR 2) — COMPLETE

- [x] 2.1 RED: `tests/unit/capabilities/test_provider_conformance.py` with `_PROVIDERS: tuple[CapabilityProvider, ...] = (ChatProvider(),)` and all per-Provider parametrized checks from design's Testing Strategy table (stable descriptor identity, constant naming, non-empty catalog, element typing, FLC regex, backend-id shape, `execute()` always raises for 3 context variants, error payload, no report, end-to-end through `WorkerRuntime`)
- [x] 2.2 RED: `tests/unit/capabilities/test_chat.py` — full `descriptor == CapabilityDescriptor(...)` equality + flag values (spec: Descriptor Catalog Correctness, "Chat advertises realistic flags")
- [x] 2.3 GREEN: create `src/tibios_ray/capabilities/chat.py` with `CHAT_GENERATE_DESCRIPTOR` (families: qwen, llama, deepseek, gemma, mistral, kimi; backends: llama_cpp, tensorrt_llm, vllm; flags: streaming/tools/json/reasoning all True) and `ChatProvider` per design's reference shape
- [x] 2.4 Update `capabilities/__init__.py` to export `ChatProvider`
- [x] 2.5 Verify: `uv run pytest && uv run ruff check && uv run pyright`

## Slice 3 — Embedding Provider + whole-catalog harness (PR 3) — COMPLETE

- [x] 3.1 RED: `tests/unit/capabilities/test_catalog_conformance.py` — co-registration (no `DuplicateCapabilityError`/`EmptyCatalogError`), aggregated catalog union, round-trip `resolve()`, exact capability-string set, AST no-branching scan, AST layering scan (`capabilities/` imports nothing from `runtime/`) (spec: Joint Registration Without Rejection, Binding Invariants)
- [x] 3.2 RED: `tests/unit/capabilities/test_embedding.py` — descriptor equality with families `bge`, `nomic_embed`, `e5`, `jina_embeddings`; backend `onnxruntime`; all flags `False`
- [x] 3.3 GREEN: create `src/tibios_ray/capabilities/embedding.py` with `EMBEDDING_GENERATE_DESCRIPTOR` and `EmbeddingProvider` (no `flags` arg — default `CapabilityFlags()`)
- [x] 3.4 Append `EmbeddingProvider()` to `_PROVIDERS` tuple in `test_provider_conformance.py`
- [x] 3.5 Update `capabilities/__init__.py` to export `EmbeddingProvider`
- [x] 3.6 Verify: `uv run pytest && uv run ruff check && uv run pyright`

## Slice 4 — Rerank Provider (PR 4) — COMPLETE

- [x] 4.1 RED: `tests/unit/capabilities/test_rerank.py` — descriptor equality with families `bge_reranker`, `jina_reranker`; backend `onnxruntime`; all flags `False`
- [x] 4.2 GREEN: create `src/tibios_ray/capabilities/rerank.py` with `RERANK_DOCUMENTS_DESCRIPTOR` and `RerankProvider`
- [x] 4.3 Append `RerankProvider()` to `_PROVIDERS` tuple
- [x] 4.4 Update `capabilities/__init__.py` to export `RerankProvider`
- [x] 4.5 Verify: `uv run pytest && uv run ruff check && uv run pyright`

## Slice 5 — Vision Provider (PR 5) — COMPLETE

- [x] 5.1 RED: `tests/unit/capabilities/test_vision.py` — descriptor equality with families `qwen_vl`, `llama_vision`, `gemma` (NOT `gemma_vision` — FLC deviation CP5); backends `vllm`, `tensorrt_llm`; flags streaming+json only
- [x] 5.2 GREEN: create `src/tibios_ray/capabilities/vision.py` with `VISION_UNDERSTAND_DESCRIPTOR` and `VisionProvider`
- [x] 5.3 Append `VisionProvider()` to `_PROVIDERS` tuple
- [x] 5.4 Update `capabilities/__init__.py` to export `VisionProvider`
- [x] 5.5 Verify: `uv run pytest && uv run ruff check && uv run pyright`

## Slice 6 — Speech Providers (transcribe + synthesize) (PR 6)

- [ ] 6.1 RED: `tests/unit/capabilities/test_speech.py` — `SPEECH_TRANSCRIBE_DESCRIPTOR` (family `whisper`, backend `faster_whisper`, flag streaming only) and `SPEECH_SYNTHESIZE_DESCRIPTOR` (family `kokoro`, backend `onnxruntime`, flag streaming only), both class equality + naming per design (`SpeechTranscriptionProvider`, `SpeechSynthesisProvider`)
- [ ] 6.2 GREEN: create `src/tibios_ray/capabilities/speech.py` with both descriptors and both Provider classes
- [ ] 6.3 Append `SpeechTranscriptionProvider()` and `SpeechSynthesisProvider()` to `_PROVIDERS` tuple
- [ ] 6.4 Update `capabilities/__init__.py` to export both classes
- [ ] 6.5 Verify: `uv run pytest && uv run ruff check && uv run pyright`

## Slice 7 — OCR Provider (PR 7)

- [ ] 7.1 RED: `tests/unit/capabilities/test_ocr.py` — descriptor equality with family `paddleocr`; backend `onnxruntime`; flag json only; class name `OcrProvider` (no acronym special-casing)
- [ ] 7.2 GREEN: create `src/tibios_ray/capabilities/ocr.py` with `OCR_EXTRACT_DESCRIPTOR` and `OcrProvider`
- [ ] 7.3 Append `OcrProvider()` to `_PROVIDERS` tuple — now all seven Providers present, satisfying proposal's Success Criteria (7 Providers, union catalog, capability-string set)
- [ ] 7.4 Update `capabilities/__init__.py` to export `OcrProvider`
- [ ] 7.5 Verify full suite: `uv run pytest && uv run ruff check && uv run pyright`; confirm `test_naming_audit.py` still passes (no "Worker" in any new identifier)
