# Tasks: The ONNX Runtime Embedding and Rerank Backend

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~550-650 (proposal "Delivery" / design "Slice Plan") |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (Seams + residency) -> PR 2 (Execution) |
| Delivery strategy | auto-chain (design.md "Slice Plan" — the Slice Plan IS the chaining decision) |
| Chain strategy | stacked-to-main (repo precedent: vllm-backend, llamacpp-backend) |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Both Protocols, both default factories, `_OnnxResidency`, `_OnnxBackendBase` (`backend_id`/`supports`/`acquire`/`release`), OR2/OR6/OR10; both public classes present, execution methods raise `NotImplementedError`; `onnx` extra; `backend-adapter` spec delta | PR 1 | Independently shippable; no `embed()`/`rerank()` execution yet |
| 2 | `_infer`, `embed()`, `rerank()`, OR3/OR7/OR8/OR9/OR11; opt-in integration smoke | PR 2 | Depends on PR 1 merged |

Strict TDD active (`uv run pytest -q`). Each numbered task is RED (failing test) then GREEN (code) unless marked test-only, doc-only, or verification.

## PR 1 — Seams + Residency

- [x] 1.1 `pyproject.toml`: add `onnx` optional extra (`onnxruntime`, `transformers`); comment noting the two-artifact debt (OR10).
- [x] 1.2 RED: typed-binding conformance test (`_e: EmbeddingBackend = OnnxEmbeddingBackend(...)`, `_r: RerankBackend = OnnxRerankBackend(...)`) plus negative — `OnnxEmbeddingBackend` has no `rerank` attribute (OR5). GREEN: create `engines/onnxrt.py` with `InferenceSessionLike`/`NodeArgLike`/`TokenizerLike` Protocols, `ONNXRUNTIME_BACKEND_ID`, `UnknownSessionError`, private `_OnnxBackendBase` skeleton, both public classes with their execution method raising `NotImplementedError`, no base-class edge.
- [x] 1.3 Create `tests/unit/engines/stub_onnx.py`: `StubInferenceSession`, `StubNodeArg`, `StubTokenizer` with call-recording factories (`stub_llama.py`/`stub_async_llm.py` precedent).
- [x] 1.4 RED: SDK-free import test — `onnxruntime`, `transformers`, `numpy` absent from `sys.modules` after import. GREEN: `default_session_factory`/`default_tokenizer_factory`, lazy `importlib.import_module` (LC11/VL8).
- [ ] 1.5 RED: `supports()` True for `BackendId("onnxruntime")` on both classes, False for `llama_cpp`/`vllm`; explicit both-classes-identical assertion (OR5's discriminator). GREEN: implement `backend_id`/`supports()` on `_OnnxBackendBase` (LC12/VL4).
- [ ] 1.6 RED: three `acquire()`s -> three distinct `session_id`s, session-factory counter exactly 1, tokenizer-factory counter exactly 1 (OR2). GREEN: `_OnnxResidency` dataclass (session/tokenizer/input_names/refcount), `acquire()` construct-or-reuse + refcount under `self._lock`.
- [ ] 1.7 RED: single-flight under concurrency — `asyncio.gather` of two `acquire()`s with factory parked on a `threading.Event`, factory counter exactly 1 (OR2/VL6). GREEN: single-flight lock + double-check in `acquire()`.
- [ ] 1.8 RED: teardown at zero / double-release / rebuild-after-teardown (OR2/VL13). GREEN: `release()` pop-under-lock, decrement, teardown at zero; second `release()` raises `UnknownSessionError`.
- [ ] 1.9 RED: providers reach the session factory, not `supports()` — default `("CPUExecutionProvider",)`, custom tuple when supplied (OR10). GREEN: wire `providers` construction argument through to the session factory call.
- [ ] 1.10 Modify `tests/unit/engines/test_engines_layering.py`: bump vacuity guard `>=3` -> `>=4` (scanner already recursive, covers `onnxrt.py`).
- [ ] 1.11 RED/GREEN `src/tibios_ray/engines/__init__.py`: re-export both Backends, both Protocols, `ONNXRUNTIME_BACKEND_ID`; extend `__all__`; update `tests/unit/engines/test_engines_exports.py`.
- [ ] 1.12 No code task: `backend-adapter` spec delta (`specs/backend-adapter/spec.md`, modality-agnostic Backend Contract phrasing) is doc-only — already authored, no corresponding code change.
- [ ] 1.13 Local verification: `uv run pytest && uv run ruff check && uv run pyright` green for slice 1 (extra absent).

## PR 2 — Execution

- [ ] 2.1 RED: concurrent `run()` on one shared session — two sessions from one Backend, stub `run()` blocks on `threading.Barrier(2)`, `asyncio.gather(embed(s1,...), embed(s2,...))`, both enter before either exits; a lock anywhere times it out (OR3). GREEN: implement `_infer()` calling `residency.session.run(...)` inside `asyncio.to_thread`, no lock held.
- [ ] 2.2 RED: provably off the event loop — stub `run()` blocks on a `threading.Event`, a concurrent coroutine advances a counter before the event is set (OR7). GREEN: confirm the single `asyncio.to_thread` hop spans tokenize->run->extract; fix if any blocking work leaks onto the loop.
- [ ] 2.3 RED: input filtering — stub tokenizer emits `token_type_ids`, stub session declares only `input_ids`/`attention_mask` -> recorded feed has exactly two keys; reverse case, a declared-but-unemitted input is absent, not synthesized (OR8). GREEN: cache `session.get_inputs()`-derived `input_names` at `acquire()`, filter the feed by intersection.
- [ ] 2.4 RED: shape and order — 2-D stub output -> one `Vector` per input in order, equal length, values match; 3-D output -> `OnnxOutputShapeError`; empty input -> empty result, `run` never called (OR9). GREEN: implement `_rows()`, `OnnxOutputShapeError`, `embed()` mapping rows to `Vector`.
- [ ] 2.5 RED: `output_name` selection — constructed with `output_name="sentence_embedding"` -> stub records that name in `output_names`; default `None` passed through, `outputs[0]` read (OR9/OR10). GREEN: wire `output_name` construction argument into `_infer()`'s `session.run(self._output_names, feed)` call.
- [ ] 2.6 RED: rerank pairs the query — stub tokenizer records `text == [query] * len(documents)`, `text_pair == documents` (OR6). GREEN: implement `rerank()` calling `_infer(session, [query]*len(documents), list(documents))`, mapping `row[0]` to `RerankResult(index=i, score=...)`.
- [ ] 2.7 RED: rerank result shape — one `RerankResult` per document, `index` values are `0..n-1` in order (OR9). GREEN: confirm/adjust `rerank()` mapping (falls out of 2.4/2.6 if already correct).
- [ ] 2.8 RED: cancellation is inert — cancel the awaiting task mid-`run()`, `CancelledError` propagates, session untouched, a subsequent `embed()` on the same session still succeeds (OR11). GREEN: confirm no `finally` performs async work on the cancellation path; fix if present.
- [ ] 2.9 Create `tests/integration/test_onnxrt_smoke.py`: opt-in, `pytestmark = skipif(TIBIOS_RAY_ONNX_MODEL/…_TOKENIZER unset)`; real factories, public API only — `embed()` over 3 texts, `rerank()` over 3 ordered documents, two `asyncio.gather`-ed `embed()` calls on one shared session match their serial results (OR3/OR4 empirical discharge), clean `release()`.
- [ ] 2.10 `engines/onnxrt.py` module docstring: document OR3/OR4's thread-safety claim citing microsoft/onnxruntime discussions #10107 and #14073, plus accepted limitations (per-Backend-instance residency, artifact-pair debt, no pooling/normalization, no batching, stub cannot prove the real SDK signature, CUDA EP untested).
- [ ] 2.11 Local verification: `uv run pytest` (unit green, integration skipped), `uv run ruff check`, `uv run pyright` green for slice 2.
