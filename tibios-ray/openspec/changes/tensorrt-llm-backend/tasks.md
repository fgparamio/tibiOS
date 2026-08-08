# Tasks: TensorRT-LLM Text Backend

Source of truth for slice boundaries: `design.md`'s `File Changes` +
`Testing Strategy` tables. `design.md`'s `Migration / Rollout` proposes a
2-PR split (config+residency+stub / generate+cancellation+wiring+extra);
`sdd-tasks` **adjusts this to 4 PRs** — see Review Workload Forecast. The
File Changes' PR1/PR2 boundary is preserved as an internal seam (PR1→PR2
here = old PR1's first half; PR3→PR4 here = old PR1's second half + old
PR2), not discarded.

Strict TDD (`uv run pytest`): within each PR, the test task for a unit
precedes its implementation task. `uv run pytest && uv run ruff check &&
uv run pyright` MUST be green at the end of every PR before opening the
next.

D30-D39 are referenced by number; see `design.md` for rationale. Spec
requirements are cited by name; see `specs/tensorrt-llm-text-backend/spec.md`.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~900-1300 (proposal's 700-950 revised up: D39's pre-flight predicate + the dedicated no-compilation-entry-point guard were not itemized in `proposal.md`'s estimate) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 → PR 4 (adjusted from design.md's 2-PR proposal) |
| Delivery strategy | ask-on-risk |
| Chain strategy | **size:exception approved by user (2026-08-07) for PR 2 and PR 4** — no further splitting; both land as planned above the 400-line budget |

Decision needed before apply: Resolved
Chained PRs recommended: Declined — size:exception approved instead
Chain strategy: size:exception (PR 2, PR 4)
400-line budget risk: High, accepted

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | `TensorrtLlmConfig` + parser | PR 1 | ~70-100 lines. No dependency on Unit 2-4 — may land first or in parallel with Unit 2 |
| 2 | SDK seam: Protocols, D35 factory, D39 pre-flight, sampling-params factory, `UnknownSessionError`, `stub_trtllm.py` | PR 2 | ~415-505 lines — at or above budget alone (heaviest stub + 4 guard test files). No dependency on Unit 1 |
| 3 | Residency: `_ModelRuntime`, `backend_id`/`supports`/`acquire`/`release`, conformance | PR 3 | ~325-415 lines. Depends on Unit 2 only |
| 4 | `generate()` (D37), cancellation (D36), Composition Root wiring, `_BACKEND_PREFERENCE` (D33), the extra (D30/D32), exports/layering/forbidden-import guards, integration smoke | PR 4 | ~525-680 lines — largest unit, above budget alone. Depends on Unit 1 (needs `TensorrtLlmConfig` for `worker.py`) and Unit 3 |

Units 2 and 4 individually risk exceeding the 400-line budget even after
this 4-way split — flagged, not silently accepted. Orchestrator must stop
and ask the user (ask-on-risk): accept these two as `size:exception`
within their own PR, or split further (e.g. Unit 2 into "Protocols+factory"
vs. "stub+guard tests"; Unit 4 into "generate+cancellation" vs.
"composition+extra+guards+smoke").

## Dependency Graph

```
PR 1 (config)      ────────────────────────────────────────┐
PR 2 (SDK seam) ─► PR 3 (residency) ──────────────────────► PR 4 (generate/cancellation/wiring/extra/guards/smoke)
```

- PR 1 and PR 2 have no dependency on each other — both may start
  immediately, in parallel.
- PR 3 depends on PR 2 only (needs the Protocols, `default_engine_factory`,
  `default_sampling_params_factory`, `UnknownSessionError`, `stub_trtllm.py`).
- PR 4 depends on PR 1 (needs `TensorrtLlmConfig` for `worker.py`'s
  composition branch) and PR 3 (needs the full residency-capable class to
  add `generate()`/cancellation onto).

## PR 1 — Config surface

No dependencies. May run in parallel with PR 2.

- [ ] 1.1 Test: extend `tests/unit/config/test_config.py` — `TIBIOS_RAY_TENSORRT_ENGINE_PATH` absent → `WorkerConfig.tensorrt_llm is None`; present → `TensorrtLlmConfig(engine_path=...)` with the path returned byte-identical (D38; spec: "Unset artifact path leaves the capability unwired, not crashed")
- [ ] 1.2 Implement: `src/tibios_ray/config.py` — `TensorrtLlmConfig(engine_path: str)` frozen/slots/kw-only dataclass (D38), `_TENSORRT_ENGINE_PATH = "TIBIOS_RAY_TENSORRT_ENGINE_PATH"` constant, `_tensorrt_config(env)` parser, one `WorkerConfig.tensorrt_llm` field, one `from_env()` line
- [ ] 1.3 Verify PR 1 green: `uv run pytest tests/unit/config/ && uv run ruff check src/tibios_ray/config.py && uv run pyright src/tibios_ray/config.py`

## PR 2 — SDK seam (Protocols, D35 factory, D39 pre-flight, stub)

No dependencies. May run in parallel with PR 1.

- [ ] 2.1 Test: `tests/unit/engines/test_tensorrt_sdk_free.py` — importing `tibios_ray.engines.tensorrt` never imports `tensorrt_llm`; `sys.modules` unaffected before and after (spec: "Unit tests run without tensorrt_llm or CUDA installed")
- [ ] 2.2 Test: `tests/unit/engines/test_tensorrt_artifact_preflight.py` — `tmp_path` fixtures: missing path, an existing file (not a directory), a directory with no `*.engine` file each raise an actionable `ConfigError`-shaped failure naming `TIBIOS_RAY_TENSORRT_ENGINE_PATH`; `sys.modules` sabotage proves the SDK is never reached (D39; spec: "A configured but nonexistent or incompatible artifact fails construction explicitly")
- [ ] 2.3 Test: `tests/unit/engines/test_tensorrt_construction_blocking.py` — `default_engine_factory`'s SDK constructor call runs off the event loop (monkeypatched `asyncio.to_thread` / thread-identity assertion in an injected factory) (D35)
- [ ] 2.4 Test: `tests/unit/engines/test_tensorrt_no_compilation.py` — AST/source scan of `engines/tensorrt.py` finds no reference to `trtllm-build`, `build_config`, `BuildConfig`, `quantize`, or `subprocess` (spec: "No compilation call exists in the Backend's call path")
- [ ] 2.5 Implement: `src/tibios_ray/engines/tensorrt.py` (create) — module docstring, `TENSORRT_LLM_BACKEND_ID`, `LLMLike`/`RequestOutputLike`/`CompletionOutputLike` Protocols, `LLMFactory`/`SamplingParamsFactory` type aliases, `default_engine_factory` (D39 pre-flight predicate before any SDK call + D35 `asyncio.to_thread` body + lazy `importlib` import with the actionable `ModuleNotFoundError` naming the extra and D32's index/container instruction), `default_sampling_params_factory`, `UnknownSessionError` (D38 module-local precedent)
- [ ] 2.6 Implement: `tests/unit/engines/stub_trtllm.py` (create) — `StubLLM` (records `generate_async`/`abort`/`shutdown` calls + construction count) + `StubRequestOutput` (self-yielding-in-place per the design's gotcha, `text_diff`-bearing), mirroring `stub_async_llm.py`
- [ ] 2.7 Verify PR 2 green: `uv run pytest tests/unit/engines/test_tensorrt_sdk_free.py tests/unit/engines/test_tensorrt_artifact_preflight.py tests/unit/engines/test_tensorrt_construction_blocking.py tests/unit/engines/test_tensorrt_no_compilation.py && uv run ruff check src/tibios_ray/engines/tensorrt.py && uv run pyright src/tibios_ray/engines/tensorrt.py`

## PR 3 — Residency (shared refcounted Model Runtime)

Depends on PR 2 (needs the Protocols, `default_engine_factory`, and `stub_trtllm.py`).

- [ ] 3.1 Test: `tests/unit/engines/test_tensorrt_conformance.py` — typed binding `backend: TextGenerationBackend = TensorrtLlmTextBackend(...)`; `TensorrtLlmTextBackend.__bases__ == (object,)` (spec: "pyright accepts TensorrtLlmTextBackend as a TextGenerationBackend")
- [ ] 3.2 Test: `tests/unit/engines/test_tensorrt_supports.py` — `supports(plan)` checks only `plan.backend == BackendId("tensorrt_llm")`, true regardless of `plan.model` (spec: "supports() checks backend family only")
- [ ] 3.3 Test: `tests/unit/engines/test_tensorrt_residency.py` — first `acquire()` constructs via `StubLLM`, second `acquire()` for the same model reuses it exactly once; releasing the last session shuts the engine down (D34; spec: "First acquire constructs the engine, second acquire reuses it", "Releasing the last session shuts the engine down")
- [ ] 3.4 Test: `tests/unit/engines/test_tensorrt_concurrency.py` — N concurrent first-`acquire()`s construct exactly one engine (single-flight under the lock; `StubLLM` construction counter + barrier) (D34; spec: "Shared Refcounted Model Runtime")
- [ ] 3.5 Test: `tests/unit/engines/test_tensorrt_teardown.py` — `UnknownSessionError` on double release and on a foreign/never-acquired `session_id`; releasing a non-last session leaves the engine running
- [ ] 3.6 Implement: `src/tibios_ray/engines/tensorrt.py` (extend) — `_ModelRuntime`/`_SessionEntry` dataclasses, `TensorrtLlmTextBackend.__init__` (`engine_path`, `engine_factory`, `sampling_params_factory`), `backend_id`, `supports`, `acquire` (single-flight under lock, D34), `release` (refcount teardown, D34) — no `generate()`/cancellation yet
- [ ] 3.7 Verify PR 3 green: `uv run pytest tests/unit/engines/test_tensorrt_conformance.py tests/unit/engines/test_tensorrt_supports.py tests/unit/engines/test_tensorrt_residency.py tests/unit/engines/test_tensorrt_concurrency.py tests/unit/engines/test_tensorrt_teardown.py && uv run ruff check src/tibios_ray/engines/tensorrt.py && uv run pyright src/tibios_ray/engines/tensorrt.py`

## PR 4 — Streaming, cancellation, Composition Root wiring, extra, guards, smoke

Depends on PR 1 and PR 3.

- [ ] 4.1 Test: `tests/unit/engines/test_tensorrt_streaming.py` — chunks yielded in production order from a cumulative-`.text` stub whose `text_diff` carries only the increment (assert emitted chunks concatenate to `.text` exactly once); `TextChunk.finished` sourced from `output.finished`, never lookahead; empty non-terminal deltas dropped; only `TextChunk` values produced; no `Thread`/`asyncio.Queue`/polling-loop/gRPC import in the call path (D37; spec: "generate() streams via native async iteration with no gRPC dependency")
- [ ] 4.2 Test: `tests/unit/engines/test_tensorrt_cancellation.py` — `abort()` issued exactly once on exhaustion-free exit, `aclose()`, `break`, and `CancelledError` alike; `release()` strands nothing (`runtime.pending` drained); single-owner claim never double-finalizes; `finally` performs no `await` (D36; spec: "Abandoning a stream mid-flight issues an explicit abort")
- [ ] 4.3 Implement: `src/tibios_ray/engines/tensorrt.py` (extend) — `generate()` reading `output.outputs[0].text_diff` with the mandated `# text_diff, not text — see D37` comment at the read site (D37); `_finalize`/`_schedule_finalize` issuing handle-scoped `await handle.abort()` under `suppress(Exception)`, keyed by a locally-minted `stream_key = f"{session_id}:{uuid4().hex}"` (D36)
- [ ] 4.4 Test: extend `tests/unit/engines/test_engines_exports.py` — `TENSORRT_LLM_BACKEND_ID`, `TensorrtLlmTextBackend`, `LLMLike` added to the expected export set
- [ ] 4.5 Implement: `src/tibios_ray/engines/__init__.py` (modify) — re-export the three new names, extend `__all__` (D29 aliasing precedent)
- [ ] 4.6 Test: extend `tests/unit/engines/test_engines_layering.py` — bump the vacuity guard `>= 3` → `>= 4`
- [ ] 4.7 Test: extend `tests/unit/backends/test_no_engine_imports.py` — add `"tensorrt_llm"` to `FORBIDDEN_ENGINE_MODULES`
- [ ] 4.8 Gate task: dry-run `uv lock`/`uv sync --extra tensorrt` to resolve the exact version pin (Verification Gate 1 — inconclusive per design.md, must be re-checked at implementation time since PyPI listings shift); confirm the unit tier still passes with the extra **absent** (spec: "Core install excludes tensorrt_llm")
- [ ] 4.9 Implement: `pyproject.toml` (modify) — `tensorrt = ["tensorrt-llm>=X,<Y; python_version < '3.14'"]` (D30) with the comment carrying D31/D32's install-channel/index-flag message; `X`/`Y` from 4.8's dry run
- [ ] 4.10 Test: extend `tests/unit/test_worker.py` — `TIBIOS_RAY_TENSORRT_ENGINE_PATH` absent → `tensorrt_llm` absent from `ChatProvider`'s injected mapping, Worker still starts (spec: "Unset artifact path leaves the capability unwired, not crashed"); present → wired; `_BACKEND_PREFERENCE == (vllm, tensorrt_llm, llama_cpp, onnxruntime)` (D33); `worker.py` remains the sole constructor (existing construction-scan guard extended)
- [ ] 4.11 Implement: `src/tibios_ray/worker.py` (modify) — one `if config.tensorrt_llm is not None:` branch constructing `TensorrtLlmTextBackend(engine_path=...)`; **insert** `TENSORRT_LLM_BACKEND_ID` into `_BACKEND_PREFERENCE` at index 1 with a comment citing D33's rationale
- [ ] 4.12 Test: `tests/unit/capabilities/test_no_backend_specific_branching.py` or extend an existing scan — `capabilities/chat.py` has zero diff; neither it nor `selection/preference.py` contains a conditional referencing `tensorrt_llm`/`TensorrtLlmTextBackend` by name (spec: "capabilities/chat.py has zero diff for this change", "No backend-specific branching exists in ChatProvider or PreferenceOrderPolicy")
- [ ] 4.13 Implement: `tests/integration/test_tensorrt_smoke.py` (create) — opt-in, skipped unless `TIBIOS_RAY_TENSORRT_ENGINE_PATH` is set; real `LLM` against a real engine artifact, mirroring `test_vllm_smoke.py`'s shape (carries Verification Gates 2-6)
- [ ] 4.14 Verify PR 4 green + full success criteria: `uv run pytest && uv run ruff check && uv run pyright` — zero violations across layering/naming/`no_engine_imports` guards

## Cross-PR Guards (re-run at the end of every PR)

- [ ] G.1 `test_tensorrt_no_compilation.py` (2.4) stays green as `generate()`/cancellation/composition code lands in PR 4 — Invariant 2 must hold end-to-end, not just at PR 2
- [ ] G.2 `tests/unit/engines/test_engines_layering.py` (`engines -> backends` only) stays at zero violations after every PR
- [ ] G.3 `engines/tensorrt.py` never imports `capabilities/`, `selection/`, or `runtime/` — manual AST-import-scan re-verification alongside G.2, mirroring the archived `provider-backend-composition` tasks.md's `G.3`
