# Tasks: The llama.cpp Text Generation Backend

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~700-800 total (Slice 1 ~300, Slice 2 ~280, Slice 3 ~180) |
| 400-line budget risk | Medium per slice, High if delivered as one PR |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (Slice 1) -> PR 2 (Slice 2) -> PR 3 (Slice 3) |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Package/seam/residency | PR 1 | Base=main. `engines/` skeleton, `acquire`/`release`, guard fix, extra |
| 2 | Streaming | PR 2 | Base=PR 1 branch. `generate()`, thread bridge, LC8 terminal chunk |
| 3 | Concurrency + reality check | PR 3 | Base=PR 2 branch. Lock scoping, abandonment, opt-in integration |

## Phase 1 (Slice 1): Package, Seam, Residency

- [x] 1.1 RED `tests/unit/engines/test_llamacpp_conformance.py`: typed binding `_b: TextGenerationBackend = LlamaCppTextBackend(...)`
- [x] 1.2 GREEN `src/tibios_ray/engines/llamacpp.py`: `LlamaLike` Protocol, `LlamaFactory`, `default_llama_factory` (lazy `importlib.import_module("llama_cpp")`), `LLAMA_CPP_BACKEND_ID`, `LlamaCppTextBackend` skeleton (`backend_id`, `supports`, `acquire`, `release` stubs), no base class
- [x] 1.3 RED/GREEN `tests/unit/engines/test_llamacpp_sdk_free.py`: after import, `"llama_cpp" not in sys.modules`
- [x] 1.4 RED `tests/unit/engines/test_llamacpp_supports.py`: `True` for `llama_cpp`, `False` for `vllm`/`tensorrt_llm`/`onnxruntime`
- [x] 1.5 GREEN implement `supports(plan)` as `plan.backend == LLAMA_CPP_BACKEND_ID` (LC12, no model check)
- [x] 1.6 RED `tests/unit/engines/test_llamacpp_residency.py`: two `acquire()`s give distinct `session_id`/stub instances; `release()` calls `close()` once, session unusable after; releasing unknown session raises
- [x] 1.7 GREEN implement `_Residency` side table (LC2), `acquire` via `asyncio.to_thread(factory, model_path)` (LC3), `release` (stop->join->close in one `to_thread`)
- [x] 1.8 RED `tests/unit/engines/test_llamacpp_layering.py`: AST scan — `engines/*.py` imports only `tibios_ray.backends`
- [x] 1.9 GREEN fix any stray imports so layering test passes
- [x] 1.10 RED/GREEN `src/tibios_ray/engines/__init__.py`: re-export `LlamaCppTextBackend`/`LlamaLike`/`LLAMA_CPP_BACKEND_ID` + `__all__`; `tests/unit/engines/test_engines_exports.py`
- [x] 1.11 Modify `tests/unit/backends/test_no_engine_imports.py`: `glob`->`rglob`, extract scanner, add synthetic `tmp_path` nested-package test proving recursion
- [x] 1.12 Harden scanner to flag `importlib.import_module("<forbidden literal>")` string imports inside `backends/`
- [x] 1.13 Modify `pyproject.toml`: `[project.optional-dependencies] llamacpp = ["llama-cpp-python>=0.3.34,<0.4"]` (re-verify version)
- [x] 1.14 Verify: `uv run pytest tests/unit/engines tests/unit/backends/test_no_engine_imports.py`, `uv run ruff check`, `uv run pyright` all green with extra absent

## Phase 2 (Slice 2): Streaming

- [x] 2.1 RED `tests/unit/engines/test_llamacpp_streaming.py::test_streams_not_buffers`: stub blocks on `threading.Event` after first token; consumer already has chunk 1 while producer parked
- [x] 2.2 GREEN add `_Token`/`_Failure`/`_Done` frozen slotted dataclasses (LC10), `_pump` thread fn, `_put` backpressure helper (bounded `asyncio.Queue(maxsize=8)`, `run_coroutine_threadsafe`, poll loop)
- [x] 2.3 GREEN implement `generate()`: `async with residency.lock`, start pump, consume queue, LC8 one-token lookahead, `finally: stop_event.set()` (no await)
- [x] 2.4 RED `::test_loop_stays_alive`: stub parks until a concurrent asyncio task sets its event; deadlocks if loop blocked
- [x] 2.5 GREEN confirm thread bridge unblocks loop; fix if deadlock
- [x] 2.6 RED `::test_terminal_semantics`: multi-token stub yields >1 chunk, exactly one trailing `finished=True`; empty completion yields exactly one `TextChunk(text="", finished=True)`
- [x] 2.7 GREEN implement lookahead buffering/empty-chunk drop for LC8
- [x] 2.8 RED `::test_parameter_mapping`: stub records `max_tokens`, `temperature`, `stop=list(request.stop)`, `stream=True`, prompt verbatim
- [x] 2.9 GREEN wire `TextRequest` fields into `create_completion` call
- [x] 2.10 RED `::test_exception_propagation`: stub raises mid-stream -> identical exception surfaces from `async for`, lock released after
- [x] 2.11 GREEN implement `_Failure` re-raise path
- [x] 2.12 Verify: `uv run pytest tests/unit/engines`, `uv run ruff check`, `uv run pyright` green

## Phase 3 (Slice 3): Concurrency + Reality Check

- [x] 3.1 RED `tests/unit/engines/test_llamacpp_concurrency.py::test_serializes_within_session`: stub logs `(marker, enter/exit)` under `threading.Lock`, reentrancy counter never >1; two `generate()` on one session via `asyncio.gather` -> `[enter,exit,enter,exit]`
- [x] 3.2 GREEN confirm per-session lock serializes; fix if interleaved
- [x] 3.3 RED `::test_independence_across_sessions`: two `acquire()`s, each stub waits on shared `threading.Barrier(2, timeout=...)` before first token; both enter before either exits
- [x] 3.4 GREEN confirm lock is per-session not global (LC2/LC4); fix if barrier times out
- [x] 3.5 RED `tests/unit/engines/test_llamacpp_abandonment.py::test_abandon_releases_lock`: consume one chunk, `await agen.aclose()`; fresh `generate()` on same session completes; stub's generator `finally` ran (`asyncio.to_thread(stub.closed.wait, 1.0)`)
- [x] 3.6 GREEN confirm `aclose()` triggers `stop_event` via generator `finally` (LC5/LC7); fix pump self-termination if needed
- [x] 3.7 Create `tests/integration/__init__.py` and `tests/integration/test_llamacpp_smoke.py`: `pytestmark = skipif(TIBIOS_RAY_LLAMACPP_GGUF unset)`; real factory, >=2 chunks, one terminal chunk, `max_tokens` honored, `stop` honored, `release()` clean
- [x] 3.8 Verify: `uv run pytest` (unit green, integration skipped), `uv run ruff check`, `uv run pyright` green
