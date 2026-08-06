# Tasks: The vLLM Text Generation Backend

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~450-550 (proposal "Delivery") |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (Model Runtime/residency) -> PR 2 (streaming/cancellation) |
| Delivery strategy | auto-chain (design.md "Slice Plan") |
| Chain strategy | stacked-to-main (confirmed by user 2026-08-06) |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main (confirmed)
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Model Runtime, refcounted acquire/release, `AsyncLLMLike` seam, `vllm` extra, `backend-adapter` spec delta (doc-only) | PR 1 | Independently shippable; no `generate()` yet |
| 2 | Native-async `generate()`, uniform cancellation, opt-in GPU smoke | PR 2 | Depends on PR 1 merged |

Strict TDD active (`uv run pytest`). Each numbered task is RED (failing test) then GREEN (code) unless marked test-only or code-only.

## PR 1 — Model Runtime + Residency

- [x] 1.1 `pyproject.toml`: add `vllm` optional extra (mirrors `llamacpp` extra); comment noting torch/CUDA coupling.
- [x] 1.2 RED: typed-binding conformance test (`_b: TextGenerationBackend = VllmTextBackend(...)`). GREEN: create `engines/vllm.py` with `AsyncLLMLike`/`RequestOutputLike`/`CompletionOutputLike` Protocols, `VLLM_BACKEND_ID`, `UnknownSessionError`, empty `VllmTextBackend` skeleton.
- [x] 1.3 Create `tests/unit/engines/stub_async_llm.py`: `StubAsyncLLM`, `StubRequestOutput`, recording params factory (`stub_llama.py` precedent).
- [x] 1.4 RED: import-SDK-free test (`"vllm"`/`"torch"` absent from `sys.modules` after import). GREEN: `default_engine_factory` with lazy `importlib` import (LC11).
- [x] 1.5 RED: `supports()` True/False across BackendIds incl. plan exposing only `.backend` (VL4). GREEN: implement `supports()`.
- [ ] 1.6 RED: first/second `acquire()` reuse one engine; two models get two engines (VL2/VL3). GREEN: `_ModelRuntime` dataclass, `acquire()` construct-or-reuse + refcount increment under `self._lock` (VL5).
- [ ] 1.7 RED: concurrent-first-acquire barrier test asserting exactly one construction (VL6, highest-severity risk). GREEN: single-flight lock+double-check, no `await` between factory return and slot assignment.
- [ ] 1.8 RED: release-last shuts down engine; release-non-last keeps it running (VL13). GREEN: `release()` pop-under-lock, decrement, teardown at zero via `asyncio.to_thread(engine.shutdown)`.
- [ ] 1.9 RED: double-release / foreign-session raises `UnknownSessionError`, refcount unaffected (LC2 idempotent-by-rejection). GREEN: pop-then-raise ordering in `release()`.
- [ ] 1.10 RED: teardown-vs-acquire race test — concurrent `release(last)`/`acquire()`, assert ordering invariant (VL13). No new code (falls out of 1.6-1.8's shared lock).
- [ ] 1.11 `engines/__init__.py`: re-export `VLLM_BACKEND_ID`, `VllmTextBackend`, `AsyncLLMLike`; extend `__all__`. RED/GREEN: update `test_engines_exports.py`.
- [ ] 1.12 Rename `test_llamacpp_layering.py` -> `test_engines_layering.py`; bump vacuity guard `>=2` -> `>=3` (scanner already covers `vllm.py`).
- [ ] 1.13 No code task: `backend-adapter` delta (`BackendSession` residency invariant, `specs/backend-adapter/spec.md`) is spec-only — `BackendSession` already complies. Do not schedule a corresponding code change.
- [ ] 1.14 Local verification: `uv run pytest && uv run ruff check && uv run pyright` green for slice 1 (no CI configured — local gate only).

## PR 2 — Streaming + Cancellation

- [ ] 2.1 RED: `generate()` streams stub outputs in production order, no `Thread`/`asyncio.Queue`/polling in call path. GREEN: implement `generate()` async-for over `entry.runtime.engine.generate(...)`, no lock (VL5 inversion).
- [ ] 2.2 RED: terminal semantics — multi-output exactly one trailing `finished=True`; single-finished-output case; exhaustion-without-finished synthesizes `TextChunk("", finished=True)`; empty non-terminal delta dropped (VL10). GREEN: implement terminal-chunk logic.
- [ ] 2.3 RED: default sampling-params factory sets `output_kind=RequestOutputKind.DELTA`, `n=1` via faked `sys.modules["vllm.sampling_params"]` (VL9). GREEN: implement `default_sampling_params_factory`; the `output_kind=RequestOutputKind.DELTA` line MUST carry the permanent comment `# DELTA, not CUMULATIVE — see VL9`.
- [ ] 2.4 RED: consumer-side delta-not-cumulative concatenation-equality test; parameter-mapping test (`max_tokens`/`temperature`/`stop` reach factory verbatim, prompt unmodified) (VL8/VL9). GREEN: wire `sampling_params_factory` seam into `generate()`.
- [ ] 2.5 RED: streaming-not-buffering test — stub parks on `asyncio.Event` after first output, consumer already has chunk 1, loop liveness proven. No new code (regression against 2.1/2.2).
- [ ] 2.6 RED: abandonment via `aclose()` triggers stub `abort()` exactly once with correct request id; abort survives `task.cancel()` mid-stream (VL11). GREEN: `_finalize`/`_schedule_finalize` — await-free `finally`, scheduled background task registered in `runtime.pending`.
- [ ] 2.7 RED: no abort on clean completion; both `abort()` and `stream.aclose()` always issued and exception-suppressed, regardless of simulated v0/v1 GC behavior (VL12). GREEN: dual-call `_finalize`.
- [ ] 2.8 RED: `release()` is the deterministic join — abort completes before `shutdown()` (VL13/VL14). GREEN: drain `runtime.pending` in `release()` teardown path.
- [ ] 2.9 RED: two `generate()` calls yield two distinct `session_id`-prefixed request ids; `generate()` on released/foreign session raises `UnknownSessionError` before touching the engine (VL14). GREEN: `request_id = f"{session_id}:{uuid4().hex}"`, `entry.live` tracking.
- [ ] 2.10 Create `tests/integration/test_vllm_smoke.py`: opt-in, `pytestmark = pytest.mark.skipif(os.environ.get("TIBIOS_RAY_VLLM_MODEL") is None, ...)`; public-API-only: >=2 chunks, one terminal, `max_tokens` honored, two sessions share one engine, mid-stream abandonment doesn't wedge, clean release.
- [ ] 2.11 `engines/vllm.py` module docstring: document accepted limitations (per-Backend-instance residency, coupled sessions, out-of-band quantization, stub cannot prove real SDK signature).
- [ ] 2.12 Local verification: `uv run pytest && uv run ruff check && uv run pyright` green for slice 2 (no CI configured — local gate only).
