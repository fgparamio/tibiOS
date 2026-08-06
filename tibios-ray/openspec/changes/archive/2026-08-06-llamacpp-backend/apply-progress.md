# Apply Progress: llamacpp-backend

## Mode: Strict TDD (test runner: `uv run pytest`)

## Phase 1 (Slice 1): Package, Seam, Residency — COMPLETE (14/14)

| Task | Status | Notes |
|------|--------|-------|
| 1.1 | [x] | RED `tests/unit/engines/test_llamacpp_conformance.py` — typed binding to `TextGenerationBackend` |
| 1.2 | [x] | GREEN `src/tibios_ray/engines/llamacpp.py` skeleton: `LlamaLike`, `LlamaFactory`, `default_llama_factory`, `LLAMA_CPP_BACKEND_ID`, `LlamaCppTextBackend` (all methods raising `NotImplementedError`) |
| 1.3 | [x] | RED/GREEN `test_llamacpp_sdk_free.py` — passed immediately given the lazy-import design (LC11) |
| 1.4 | [x] | RED `test_llamacpp_supports.py` |
| 1.5 | [x] | GREEN `supports()` = `plan.backend == LLAMA_CPP_BACKEND_ID` (LC12) |
| 1.6 | [x] | RED `test_llamacpp_residency.py` + `tests/unit/engines/stub_llama.py` (`StubLlama` double) |
| 1.7 | [x] | GREEN `_Residency` side table (LC2), `acquire`/`release` via `asyncio.to_thread` (LC3/LC9), `UnknownSessionError` |
| 1.8 | [x] | RED `test_llamacpp_layering.py` — passed immediately (implementation only ever imported `tibios_ray.backends`) |
| 1.9 | [x] | No stray imports found — no-op |
| 1.10 | [x] | `src/tibios_ray/engines/__init__.py` re-exports + `test_engines_exports.py` |
| 1.11 | [x] | `test_no_engine_imports.py`: `glob`→`rglob`, extracted `_scan_for_forbidden_engine_imports`, added `tmp_path` recursion test + clean-tree companion test |
| 1.12 | [x] | Same scanner extended to flag `importlib.import_module("<literal>")` string imports |
| 1.13 | [x] | `pyproject.toml`: `[project.optional-dependencies] llamacpp = ["llama-cpp-python>=0.3.34,<0.4"]` — version re-verified against PyPI (latest is 0.3.34, matches design range exactly) |
| 1.14 | [x] | Full verify green, extra absent (confirmed `import llama_cpp` fails in the venv) |

### TDD Cycle Evidence — Slice 1

| Task | RED (failed for right reason) | GREEN | REFACTOR |
|------|-------------------------------|-------|----------|
| 1.1 conformance | `ModuleNotFoundError: tibios_ray.engines.llamacpp` | skeleton class created, pyright 0 errors | — |
| 1.4/1.5 supports | `NotImplementedError` from stub | real `plan.backend ==` check | — |
| 1.6/1.7 residency | `NotImplementedError` from stub `acquire`/`release` | `_Residency` side table + `to_thread` implementation | — |
| 1.8/1.9 layering | test written directly against finished, already-clean imports (passed on first run — no stray imports existed to fix) | n/a | — |
| 1.11/1.12 guard hardening | new tests referenced `_scan_for_forbidden_engine_imports`, a function that did not exist in the pre-edit file (would `NameError`) | rewrote file: `glob`→`rglob`, extracted scanner, added `importlib.import_module` string detection | ran `ruff check --fix` once for import ordering |

Note: a genuine "wrong-reason RED" was caught and fixed during 1.6 — the first draft of `test_llamacpp_residency.py` imported the stub helper as `from tests.unit.engines.stub_llama import StubLlama`, which failed with `ModuleNotFoundError: No module named 'tests'` (an import-path mistake, not a TDD-meaningful failure, since `tests/unit/engines/` has no `__init__.py` — pytest's "prepend" import mode makes that directory itself the sys.path insertion point, so sibling helper modules are imported bare). Fixed to `from stub_llama import StubLlama` before treating the subsequent `NotImplementedError` failure as the real RED.

### Files Changed — Slice 1

| File | Action | What Was Done |
|------|--------|----------------|
| `src/tibios_ray/engines/llamacpp.py` | Created | `LlamaLike` Protocol, `LlamaFactory` type alias, `default_llama_factory` (lazy `importlib.import_module`), `LLAMA_CPP_BACKEND_ID`, `UnknownSessionError`, `_Residency` dataclass, `LlamaCppTextBackend` (`backend_id`, `supports`, `acquire`, `release` implemented; `generate()` stub raising `NotImplementedError`, deferred to Slice 2) |
| `src/tibios_ray/engines/__init__.py` | Created | Re-exports `LLAMA_CPP_BACKEND_ID`, `LlamaCppTextBackend`, `LlamaLike` + `__all__` |
| `tests/unit/engines/test_llamacpp_conformance.py` | Created | Typed-binding Protocol conformance + no-base-class assertion |
| `tests/unit/engines/test_llamacpp_sdk_free.py` | Created | Asserts `llama_cpp` absent from `sys.modules` after import |
| `tests/unit/engines/test_llamacpp_supports.py` | Created | `supports()` true only for `llama_cpp`, false for 3 other backend ids |
| `tests/unit/engines/test_llamacpp_residency.py` | Created | Acquire distinctness, release-closes-once, unusable-after-release, unknown-session-raises |
| `tests/unit/engines/stub_llama.py` | Created (Slice 1) / Modified (Slice 2) | `StubLlama` — hand-written `LlamaLike` double, non-collected support module (no `test_` prefix) |
| `tests/unit/engines/test_llamacpp_layering.py` | Created | AST scan: `engines/*.py` imports only `tibios_ray.backends` (+ self-package re-export exemption) |
| `tests/unit/engines/test_engines_exports.py` | Created | Package-level re-export test, mirrors `test_backends_exports.py` |
| `tests/unit/backends/test_no_engine_imports.py` | Modified | `glob`→`rglob`; extracted `_scan_for_forbidden_engine_imports`; added synthetic nested-package recursion test + clean-tree companion; added `importlib.import_module` string-import detection + test |
| `pyproject.toml` | Modified | Added `[project.optional-dependencies] llamacpp = ["llama-cpp-python>=0.3.34,<0.4"]` |

### Deviations from Design — Slice 1

1. **`generate()` stub required in Slice 1, contrary to task 1.2's literal wording.** Task 1.2 lists only `backend_id`/`supports`/`acquire`/`release` for the "skeleton," and the orchestrator's batch instructions said "no `generate()` yet." However, task 1.1's conformance test requires a typed binding to `TextGenerationBackend`, whose Protocol declares `generate(...) -> AsyncIterator[TextChunk]`. Without *some* `generate` method present, pyright would reject the binding (`reportAttributeAccessIssue`) and the Slice 1 conformance test could never pass. Resolved by adding a minimal `generate()` method whose body was exactly `raise NotImplementedError(...)` — satisfying the Protocol's structural signature without implementing any thread-bridge/concurrency logic. Superseded by Slice 2's real implementation (see below).
2. **`_Residency` is a plain (non-frozen) `@dataclass(slots=True)`, not `frozen=True`**, per LC2's explicit rationale ("avoids stuffing mutable state (Lock, live thread) into a `frozen=True, slots=True` dataclass") — intentional, not a deviation.
3. **Layering test's allowed-imports set includes `tibios_ray.engines` (self-package) in addition to `tibios_ray.backends`.** Intra-package re-export, not a cross-layer dependency — documented in the test file's comments. No production code imports anything outside `tibios_ray.backends`.
4. **Version re-verification confirmed, not changed.** `llama-cpp-python` latest release is `0.3.34`, matching the design's `>=0.3.34,<0.4` range exactly.

### Issues Found — Slice 1

None beyond the wrong-reason-RED import-path mistake documented above (self-corrected before treating it as a TDD failure).

---

## Phase 2 (Slice 2): Streaming — COMPLETE (12/12)

| Task | Status | Notes |
|------|--------|-------|
| 2.1 | [x] | RED `tests/unit/engines/test_llamacpp_streaming.py::test_streams_not_buffers` |
| 2.2 | [x] | GREEN `_Token`/`_Failure`/`_Done` frozen slotted dataclasses (LC10), `_pump` thread fn, `_put` backpressure helper (bounded `asyncio.Queue(maxsize=8)`, `run_coroutine_threadsafe`, poll loop) |
| 2.3 | [x] | GREEN `generate()`: `async with residency.lock` for the whole generator lifetime, starts pump, consumes queue, LC8 one-token lookahead, `finally: stop_event.set()` (no await) |
| 2.4 | [x] | RED `::test_loop_stays_alive` — passed immediately (implementation from 2.2/2.3 already covers it) |
| 2.5 | [x] | Confirmed: thread bridge unblocks the loop, no fix needed |
| 2.6 | [x] | RED `::test_terminal_semantics` (+ two triangulation tests: empty completion, empty-text raw chunk dropping) — passed immediately |
| 2.7 | [x] | Confirmed: lookahead buffering/empty-chunk drop already correct from 2.3, no fix needed |
| 2.8 | [x] | RED `::test_parameter_mapping` — passed immediately |
| 2.9 | [x] | Confirmed: `TextRequest` fields already wired into `create_completion` verbatim from 2.3, no fix needed |
| 2.10 | [x] | RED `::test_exception_propagation` — passed immediately |
| 2.11 | [x] | Confirmed: `_Failure` re-raise path already correct from 2.3, no fix needed |
| 2.12 | [x] | Verify: `uv run pytest tests/unit/engines` (22 passed), `uv run ruff check` (clean), `uv run pyright` (0/0/0) |

### TDD Cycle Evidence — Slice 2

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 2.1-2.3 | `test_llamacpp_streaming.py::test_streams_not_buffers` | Unit | ✅ 15/15 (`tests/unit/engines` pre-batch) | ✅ Written — failed with `NotImplementedError('generate() lands in Slice 2')` (wrong-value assertion on the exception, confirming the right reason) | ✅ Passed after implementing `_Token`/`_Failure`/`_Done`/`_pump`/`_put`/`generate()` together | ✅ 7 cases (all 7 streaming tests written before the GREEN implementation pass, since the thread-bridge mechanism is inherently monolithic — see Deviations) | ✅ Docstring/comment cleanup on `_Residency`/`release()` referencing Slice 2 as "future"; re-ran full suite after |
| 2.4 | `::test_loop_stays_alive` | Unit | N/A (new scenario in same file) | ✅ Written first, ran RED against `NotImplementedError` before GREEN | ✅ Passed immediately once 2.2/2.3 landed | ➖ Single scenario per design's Testing Strategy table | ➖ None needed |
| 2.6 | `::test_terminal_semantics` + 2 triangulation tests | Unit | N/A | ✅ Written first (all 3 RED against `NotImplementedError`) | ✅ Passed immediately | ✅ 3 cases: multi-token, empty completion, empty-text-chunk dropping | ➖ None needed |
| 2.8 | `::test_parameter_mapping` | Unit | N/A | ✅ Written first, RED against `NotImplementedError` | ✅ Passed immediately | ➖ Single scenario (kwargs mapping has one code path) | ➖ None needed |
| 2.10 | `::test_exception_propagation` | Unit | N/A | ✅ Written first, RED against `NotImplementedError` | ✅ Passed immediately | ➖ Single scenario, but the test itself triangulates via the "lock released" follow-up call | ➖ None needed |

### Test Summary — Slice 2

- **Total tests written**: 7 (in `test_llamacpp_streaming.py`)
- **Total tests passing**: 7/7, stable across 20 repeated runs (checked for flakiness given the threading/concurrency nature — zero flakes, all synchronization is via `threading.Event`/`asyncio.gather`, no sleeps)
- **Layers used**: Unit (7)
- **Approval tests**: None — no refactoring of pre-existing behavior
- **Pure functions created**: `_put` (pump-thread side, deterministic given its inputs modulo real thread/loop timing)

### Files Changed — Slice 2

| File | Action | What Was Done |
|------|--------|----------------|
| `src/tibios_ray/engines/llamacpp.py` | Modified | Added `_Token`/`_Failure`/`_Done` (LC10), `_QUEUE_MAXSIZE`/`_PUT_POLL_SECONDS` constants, `_put` (LC6/LC7 backpressure + abandonment polling), `_pump` (LC9 off-loop SDK interaction, LC8 empty-text drop), `_residency_for` helper, and replaced the `NotImplementedError` `generate()` stub with the real async-generator thread-bridge implementation (LC4/LC5/LC8). Updated module docstring and `_Residency`/`release()` comments from "Slice 2 not yet landed" to present tense. |
| `tests/unit/engines/stub_llama.py` | Modified | Extended `StubLlama` with `block_before_index`/`block_event`/`parked` (deterministic pause + signal, no sleeps) and `error`/`error_before_index` (mid-stream exception injection); fields made public so tests can mutate them between calls (e.g. clearing `error` to prove lock release) |
| `tests/unit/engines/test_llamacpp_streaming.py` | Created | 7 tests: `test_streams_not_buffers`, `test_loop_stays_alive`, `test_terminal_semantics`, `test_terminal_semantics_empty_completion_yields_one_finished_chunk`, `test_terminal_semantics_drops_empty_text_raw_chunks`, `test_parameter_mapping`, `test_exception_propagation` |
| `openspec/changes/llamacpp-backend/tasks.md` | Modified | Checked off tasks 2.1–2.12 |

### Deviations from Design — Slice 2

1. **All 7 streaming tests were written before any GREEN implementation, and the GREEN step implemented the full thread bridge (`_Token`/`_Failure`/`_Done`/`_pump`/`_put`/`generate()`) in one pass, rather than incrementally per task 2.1→2.2→2.3→2.4→2.5…** The design's mechanism is monolithic by construction: `test_streams_not_buffers` alone requires a working pump thread, bounded queue, backpressure `_put`, and the full LC8 lookahead loop to pass at all — there is no meaningful intermediate implementation that makes *only* task 2.1's test green without also implementing the rest. This mirrors task list's own structure (2.2/2.3 are both GREEN tasks for the single RED in 2.1). Tasks 2.4, 2.6, 2.8, 2.10 are each documented above as "RED — passed immediately," matching the same honest pattern already established in Slice 1 for tasks like 1.3/1.8 where a written test happened to already be satisfied by prior implementation work.
2. **LC8's one-token lookahead necessarily delays the *first* emitted `TextChunk` until a second raw item (real token or exhaustion) has arrived** — this is a structural, unavoidable consequence of "terminal chunk by exhaustion, not `finish_reason`" (rejecting the "extra trailing empty chunk" alternative requires knowing in advance whether the current token is last). `test_streams_not_buffers` was therefore designed with **two** fast tokens followed by a block on the *third* `next()` call (the "is there more?" check) rather than blocking literally after the very first token — proving the response is streamed incrementally (not fully buffered) without contradicting the lookahead's one-item skew. This is a refinement of the task's literal wording ("stub blocks... after yielding its first token"), documented here because the literal reading is not implementable under the design's own LC8 semantics — any one-token-lookahead implementation would need evidence of a second item before it can emit anything.
3. **`_pump` catches `Exception`, not `BaseException`, when routing errors into `_Failure`**, matching the referenced precedent (`WorkerRuntime._dispatch` handling `Exception`, CP2) rather than the broader class of interrupts/`SystemExit`. Not called out as risky in design.md's LC10 rationale, but worth flagging as an explicit, deliberate scope choice.
4. **`StubLlama`'s new fields (`block_before_index`, `block_event`, `error`, `error_before_index`, `parked`) are public, not underscore-prefixed**, so tests can mutate them directly between two `generate()` calls on the same stub (e.g. `stub.error = None` in `test_exception_propagation` to prove the lock was released without re-triggering the same failure). This differs from the private-attribute style of the original Slice-1-only fields but is scoped to the test double, not production code.

### Issues Found — Slice 2

None. All 7 tests passed on the first GREEN implementation attempt; no wrong-reason REDs.

### Verification Results — Slice 2

- `uv run pytest tests/unit/engines/test_llamacpp_streaming.py`: **7 passed**, stable across 20 repeated runs (no flakiness)
- `uv run pytest tests/unit/engines`: **22 passed**
- `uv run pytest` (full repo suite): **747 passed**
- `uv run ruff check` (full repo): **All checks passed**
- `uv run pyright` (full repo): **0 errors, 0 warnings, 0 informations**
- Confirmed `llama_cpp` extra still NOT installed in the venv (`importlib.util.find_spec("llama_cpp")` → `None`), and `import tibios_ray.engines.llamacpp` still leaves `"llama_cpp" not in sys.modules` — all green under that condition.

---

## Phase 3 (Slice 3): Concurrency + Reality Check — COMPLETE (8/8)

| Task | Status | Notes |
|------|--------|-------|
| 3.1 | [x] | RED `tests/unit/engines/test_llamacpp_concurrency.py::test_serializes_within_session` |
| 3.2 | [x] | GREEN confirmed: per-session lock (already implemented in Slice 2) serializes correctly — no production fix needed |
| 3.3 | [x] | RED `::test_independence_across_sessions` |
| 3.4 | [x] | GREEN confirmed: lock is per-session, not global (LC2/LC4, already implemented) — no production fix needed |
| 3.5 | [x] | RED `tests/unit/engines/test_llamacpp_abandonment.py::test_abandon_releases_lock` |
| 3.6 | [x] | GREEN confirmed: `aclose()` triggers `stop_event`, pump self-terminates via LC7 polling, lock releases (LC5, already implemented) — no production fix needed |
| 3.7 | [x] | Created `tests/integration/__init__.py` and `tests/integration/test_llamacpp_smoke.py` — opt-in, `skipif(TIBIOS_RAY_LLAMACPP_GGUF unset)` |
| 3.8 | [x] | Verify: full suite 750 passed / 4 skipped, `ruff check` clean, `pyright` 0/0/0 |

### TDD Cycle Evidence — Slice 3

| Task | Test File | RED (failed for right reason) | GREEN | Flakiness check |
|------|-----------|-------------------------------|-------|------------------|
| 3.1/3.3 | `test_llamacpp_concurrency.py` | Confirmed genuine: `stub_llama.py` was reverted to its pre-Slice-3 state and the tests re-run, producing `TypeError: StubLlama.__init__() got an unexpected keyword argument 'barrier'` — a missing-test-infrastructure RED, not a production bug | Extended `StubLlama` with `marker`/`activity_log`/`max_active_count` (enter/exit logging + reentrancy counter under a `threading.Lock`) and `barrier` (shared `threading.Barrier` wait before first token); both tests then passed immediately against the existing `generate()` implementation — production code from Slice 2 already correctly serializes per-session and never per-process | 20 repeated runs, 0 flakes |
| 3.5 | `test_llamacpp_abandonment.py` | Same class of RED as 3.1 (stub lacked `closed`/the new `finally`-based exit marker) — not separately re-verified in isolation since the same stub revert covered it, but the test could not have passed before the `closed` event and `try/finally` wrapping existed in `create_completion()` | Added `closed: threading.Event`, set inside `create_completion()`'s `finally` (now wrapping the whole body so it fires on exhaustion *and* `GeneratorExit`); test passed immediately — `generate()`'s `finally: stop_event.set()` (LC5) and `_put`'s polling abandonment check (LC7) were already correctly implemented in Slice 2 | 20 repeated runs, 0 flakes |
| 3.7 | `tests/integration/test_llamacpp_smoke.py` | N/A — opt-in test, no RED/GREEN cycle applicable (skipped by construction without the env var); verified it collects and is reported `SKIPPED`, not silently ignored or erroring | 4 test functions written directly against the public API | N/A |

### Files Changed — Slice 3

| File | Action | What Was Done |
|------|--------|----------------|
| `tests/unit/engines/stub_llama.py` | Modified | Added `marker`/`activity_log`/`max_active_count`/`_activity_lock` (enter/exit logging with a live reentrancy counter, LC4 serialization proof), `barrier` (shared `threading.Barrier` wait before first token, LC4 independence proof), `closed: threading.Event` (set in `create_completion()`'s `finally`, now wrapping the whole generator body so it fires on exhaustion *and* `GeneratorExit`/`aclose()`) |
| `tests/unit/engines/test_llamacpp_concurrency.py` | Created | `test_serializes_within_session` (one session, two concurrent `generate()` calls via `asyncio.gather`, asserts `[enter,exit,enter,exit]` log order and `max_active_count <= 1`); `test_independence_across_sessions` (two sessions, two `StubLlama` instances sharing one `threading.Barrier(2, timeout=5.0)`, proves the lock is per-session not global — a global lock would starve the barrier and time it out) |
| `tests/unit/engines/test_llamacpp_abandonment.py` | Created | `test_abandon_releases_lock`: 30-token stub (deliberately larger than `_QUEUE_MAXSIZE=8` so the pump is structurally guaranteed to still be mid-stream, parked in `_put`'s backpressure poll, when abandonment happens — not coincidentally already exhausted); consumes one chunk, `aclose()`s, confirms (a) `stub.closed.wait(1.0)` is set — the stub's own generator `finally` ran — and (b) a fresh `generate()` call on the same session completes, proving the lock was released |
| `tests/integration/__init__.py` | Created | Package marker + docstring explaining the opt-in integration-test convention |
| `tests/integration/test_llamacpp_smoke.py` | Created | Module-level `pytestmark = pytest.mark.skipif(os.environ.get("TIBIOS_RAY_LLAMACPP_GGUF") is None, ...)`; 4 tests against the real `default_llama_factory` (no override): multi-chunk + single-terminal-chunk semantics, `max_tokens` honored, `stop` string honored (`stop=(" ",)`, asserts no space in the emitted text and early truncation), `release()` completes cleanly. Imports only the public API (`LlamaCppTextBackend`, `LLAMA_CPP_BACKEND_ID`, `BackendId`, `TextRequest`) — no `llama_cpp` import, so the module type-checks with the SDK absent (LC11) |
| `openspec/changes/llamacpp-backend/tasks.md` | Modified | Checked off tasks 3.1–3.8 — all 34 tasks in the change now `[x]` |

### Deviations from Design — Slice 3

1. **`StubLlama.create_completion()` gained a `try/finally` wrapper it did not have before** (Slices 1–2 only guarded individual `_maybe_raise`/`_maybe_block` calls inline, with no generator-level `finally`). This was necessary, not optional: the abandonment test's requirement to observe "the stub's underlying generator's `finally` actually ran" is meaningless without one existing. The wrapper preserves all prior behavior exactly (block/error injection points at the same indices) and only adds the enter/exit marker + `closed.set()` around it — verified by the full pre-existing 22-test `tests/unit/engines` suite (now 25, +3) staying green throughout.
2. **`test_independence_across_sessions`'s outer `asyncio.wait_for(..., timeout=10.0)`** is a deliberate, generous bound around a mechanism that is otherwise "deterministic by structure" per design.md's own framing (the `threading.Barrier(2, timeout=5.0)` is the actual determinism — either both sides reach it, or the barrier itself times out and raises `BrokenBarrierError` inside `generate()`, propagating as a clean test failure rather than a hang). The outer `wait_for` exists only as a last-resort safety net against a genuine deadlock hanging the whole test run; it does not introduce timing-dependent pass/fail behavior — the barrier's own 5s bound does that job, and 5s only matters in the failure path.
3. **`asyncio.gather(...)`'s runtime return type is `list`, not the `tuple[...]` its typeshed overloads declare for a fixed number of positional awaitables.** Both concurrency tests wrap the `gather()` result in `list(...)` before returning from their `scenario()` coroutines — reconciling pyright's static tuple type with the actual runtime list without a `# type: ignore` comment (same LC11-pincer-avoidance reasoning already established for `default_llama_factory`). Caught by `uv run pyright` during this batch (`reportReturnType`), not by a test failure — worth flagging since it is the only new pyright-vs-runtime mismatch encountered in the whole change.
4. **The integration test's `stop` scenario (`test_generate_honors_stop_string`) asserts a probabilistic-but-near-certain property** ("a space appears early in any coherent multi-word completion") rather than a byte-exact one, since the real model's output is not deterministic across GGUF files/quantizations. This is consistent with the test being opt-in and never run in CI (gated on `TIBIOS_RAY_LLAMACPP_GGUF`, which the default test run leaves unset) — it is exploratory/confirmatory for whoever runs it manually with a real model file, not a hermetic assertion.
5. **RED verification for 3.1/3.3 and 3.5 was done via one shared before/after stub revert** (temporarily restoring `stub_llama.py` to its pre-Slice-3 content via the scratchpad, confirming `TypeError` on the new keyword arguments, then restoring the Slice-3 version) rather than three separate incremental reverts. This mirrors the Slice 1/2 precedent of documenting "RED — passed immediately" once the underlying mechanism is monolithic (here: `StubLlama`'s new fields are added together since the three new tests share the same constructor surface) — the RED was genuine (a real `TypeError`, not a production-logic gap) and its cause is fully attributable to test-infrastructure absence, not a design flaw.

### Issues Found — Slice 3

None. Both concurrency tests and the abandonment test passed on the very first run once `StubLlama` was extended — no production code in `src/tibios_ray/engines/llamacpp.py` needed any change for tasks 3.1–3.6; the per-session lock (LC4), no-await `finally` release discipline (LC5), and abandonment polling protocol (LC7) built in Slice 2 were already correct. This is the intended outcome of "Slice 3: Concurrency + Reality Check" per design.md's Slice Plan — it proves prior work, it does not add new production logic.

### Verification Results — Slice 3

- `uv run pytest tests/unit/engines/test_llamacpp_concurrency.py tests/unit/engines/test_llamacpp_abandonment.py`: **3 passed**, stable across 20 repeated runs (0 flakes)
- `uv run pytest tests/integration`: **4 skipped** (confirmed `SKIPPED`, not `FAILED` or silently excluded — `TIBIOS_RAY_LLAMACPP_GGUF` unset in this environment)
- `uv run pytest tests/unit/engines`: **25 passed** (22 from Slices 1–2 + 3 new)
- `uv run pytest` (full repo suite): **750 passed, 4 skipped**
- `uv run ruff check` (full repo): **All checks passed**
- `uv run pyright` (full repo): **0 errors, 0 warnings, 0 informations**
- Confirmed `llama_cpp` extra still NOT installed in the venv (`importlib.util.find_spec("llama_cpp")` → `None`), and `import tibios_ray.engines.llamacpp` still leaves `"llama_cpp" not in sys.modules` — all green under that condition, unchanged since Slice 1.

---

## Workload / PR Boundary — Slice 3

- Mode: chained PR slice (`auto-chain`, `stacked-to-main` per tasks.md Review Workload Forecast)
- Current work unit: Unit 3 — "Concurrency + reality check" (PR 3, base = PR 2's branch)
- Boundary: starts from Slice 2's completed streaming implementation (`generate()` already correct); ends with the concurrency-serialization tests, the cross-session-independence test, the abandonment/`aclose()` test, and the opt-in integration smoke test — all proving existing production behavior rather than adding new production code. Clean rollback boundary via `git revert` of this slice's commits; this is also the **final** slice of the change.
- Estimated review budget impact: `tests/unit/engines/stub_llama.py` grew by ~50 lines (marker/barrier/closed support); `tests/unit/engines/test_llamacpp_concurrency.py` is ~115 lines new; `tests/unit/engines/test_llamacpp_abandonment.py` is ~90 lines new; `tests/integration/{__init__,test_llamacpp_smoke}.py` are ~110 lines new combined. Total new/modified ≈ 360-370 lines — within tasks.md's Slice 3 estimate (~180, exceeded due to the integration test's four separate scenarios and generous docstrings) but still under the 400-line single-PR budget.

## Status

**34/34 total change tasks complete** (Slice 1: 14/14, Slice 2: 12/12, Slice 3: 8/8). The `llamacpp-backend` change is fully implemented — `LlamaCppTextBackend` satisfies `TextGenerationBackend` structurally, with residency (`acquire`/`release`), non-blocking thread-bridge streaming (`generate()`), and per-session concurrency control (`asyncio.Lock`, LC4) all built and verified. Ready for `sdd-verify`.
