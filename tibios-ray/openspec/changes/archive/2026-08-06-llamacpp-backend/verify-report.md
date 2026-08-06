## Verification Report

**Change**: llamacpp-backend
**Version**: N/A (single-version spec)
**Mode**: Strict TDD

---

### Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 34 |
| Tasks complete | 34 |
| Tasks incomplete | 0 |

All 3 slices (Phase 1: 14/14, Phase 2: 12/12, Phase 3: 8/8) checked complete in `tasks.md`.

---

### Build & Tests Execution

**Build**: N/A (no build step for this Python package; ruff + pyright serve as the quality gate)

**Ruff**: All checks passed.

**Pyright**: 0 errors, 0 warnings, 0 informations.

**Tests**: 750 passed, 4 skipped (0 failed), exit code 0 — independently re-run, matches apply-progress's self-report exactly.

- 4 skipped = the 4 opt-in integration tests in `tests/integration/test_llamacpp_smoke.py` (gated by `TIBIOS_RAY_LLAMACPP_GGUF` env var, unset in this environment — expected, by design).

**`llama_cpp` absence verified independently**:
```
llama_cpp installed: False
llama_cpp in sys.modules after import: False
```
Full 750-test suite passes with the SDK genuinely absent — core install stays SDK-free per proposal's explicit success criterion.

**Coverage**: Not available (no coverage tool configured in project — consistent with prior archived changes' verify-reports).

---

### Independent Verification (beyond trusting apply-progress)

1. **LC12 — "An Engine Never Performs Model Selection" (user-mandated non-negotiable), verified rigorously**:
   - `grep`'d `src/tibios_ray/engines/llamacpp.py` for any `model`/`family`/`ResolvedModelRef` reference outside `supports()`. Only hits: docstrings, `model_path` (constructor param — GGUF file path, not model identity), and the `supports()` line itself. **Zero model-identity branching anywhere in the module.**
   - `supports(plan)` is exactly `return plan.backend == LLAMA_CPP_BACKEND_ID` — one line, no conditionals.
   - Confirmed this is not just convention but **structurally enforced**: `ServingPlanLike` (in `backends/adapter.py`) exposes only a `.backend` property — `plan.model` is not even accessible under pyright's structural typing, so a model-identity branch would fail type-checking before it could exist.
   - Gap noted: unlike `capability-providers`' AST no-branching guard, there is no dedicated automated regression test scanning `llamacpp.py` for model-identity conditionals — verification here is manual grep + structural typing, not a standing test. See SUGGESTION below.

2. **Zero gRPC dependency**: `rg "import grpc|grpc\."` across the entire `src/tibios_ray/` tree returns nothing — no gRPC type exists anywhere in this codebase yet, let alone in `engines/llamacpp.py`. `generate()`'s only yield type is `TextChunk` (plain frozen dataclass from `backends/text.py`), confirmed by direct code read of the full `generate()` body and by every streaming test's assertions (`TextChunk(text=..., finished=...)`).

3. **Per-session lock, genuinely per-session, not adapter-level**: `rg "self\._lock|self\.lock|Lock\(\)"` in `llamacpp.py` finds only `_Residency.lock: asyncio.Lock = field(default_factory=asyncio.Lock)` — no adapter-level or module-level lock exists. Each `acquire()` call creates a fresh `_Residency(llama=llama)` (fresh `Lock()` via `default_factory`) and stores it in `self._sessions[session_id]`, a `dict` — one lock per session, confirmed by direct code read (`acquire()`, lines 242–250) and further proven behaviorally by `test_independence_across_sessions` (two sessions run concurrently without blocking each other — would time out on a `threading.Barrier` if the lock were global).

4. **LC5 — `finally: stop_event.set()` performs no `await`**: direct read of `generate()`'s `finally` block (lines 314–322) confirms it contains exactly one statement, `stop_event.set()` (synchronous, infallible), plus comments — no `await` anywhere in that block, on any exit path (exhaustion, `aclose()`, `break`, `CancelledError`, GC). This is the exact mechanism the proposal's risk table required to avoid "lock leak on cancellation." The pump thread is deliberately *not* joined here (joined off-loop, inside `release()`'s single `to_thread` call instead, per LC9).

5. **`default_llama_factory` lazy import, confirmed empirically**:
```
llama_cpp installed: False
llama_cpp in sys.modules after import: False   (after `import tibios_ray.engines.llamacpp`)
```
   Source: `default_llama_factory` calls `importlib.import_module("llama_cpp")` inside its own body, never at module level — confirmed both by static read and by the runtime check above.

6. **`ChatProvider` genuinely untouched**: read `src/tibios_ray/capabilities/chat.py` in full — `@dataclass(frozen=True, slots=True)` with zero declared fields, `execute()` unconditionally raises `NoBackendAvailableError`, no import of or reference to `LlamaCppTextBackend` or `tibios_ray.engines` anywhere in the file. Also confirmed `src/tibios_ray/worker.py` has no reference to `LlamaCpp*` or `engines` — nothing in production code constructs the new adapter yet, matching the proposal's explicit "Out of Scope" boundary.

7. **`test_no_engine_imports.py` `glob`→`rglob` fix is real, not cosmetic**: read the file in full. The recursive-violation test (`test_scanner_recurses_into_nested_packages`) genuinely builds a synthetic nested package at `tmp_path/sub/pkg/bad.py` containing `import llama_cpp`, plus the necessary `__init__.py` files, and asserts the scanner's offender dict correctly reports `sub/pkg/bad.py`. A companion test (`test_scanner_finds_no_offenders_in_a_clean_nested_package`) proves the scanner doesn't false-positive on a clean nested tree, making the first test's non-empty result meaningful rather than a scanner-always-fires bug. A third test (`test_scanner_flags_importlib_string_based_forbidden_imports`) proves the design-recommended hardening for `importlib.import_module("<literal>")` string-based imports (which a plain AST-import scan would miss, and which LC11 itself introduces into the codebase) is real and working. The scanner itself uses `package.rglob("*.py")`, not `glob`.

8. **Spot-checked 2–3 tests for tautology — none found**:
   - `test_independence_across_sessions` (concurrency): uses a `threading.Barrier(2, timeout=5.0)` shared across two distinct `StubLlama` instances — a global/adapter-level lock would starve the second session's stub from ever reaching the barrier, timing it out and failing the test. This is a real structural proof, not an assertion of `True == True`.
   - `test_streams_not_buffers`: proves non-buffering via a genuine one-token-lookahead race — the stub is parked (`threading.Event`) on the *third* `next()` call before the first `TextChunk` is delivered to the consumer, and the test asserts `stub.parked.is_set()` while `block_event` is still unset at that point — a real concurrency proof, not a mocked no-op.
   - `test_abandon_releases_lock`: uses 30 tokens (`_MANY_TOKENS`, deliberately > `_QUEUE_MAXSIZE=8`) so the pump thread is *structurally guaranteed* still mid-stream (not coincidentally finished) when `aclose()` fires; asserts both that the stub's own generator `finally` ran (`stub.closed.wait(1.0)` — proves the *producer* unwound, not just the consumer) and that a fresh `generate()` call on the same session subsequently completes (proves the lock was actually released, not merely that no exception was raised).

---

### Spec Compliance Matrix

**`llamacpp-text-backend` spec**

| Requirement | Scenario | Test | Result |
|---|---|---|---|
| Structural Conformance to TextGenerationBackend | pyright accepts LlamaCppTextBackend as TextGenerationBackend | `test_llamacpp_conformance.py::test_llamacpp_text_backend_satisfies_text_generation_backend` + `uv run pyright` (0 errors) | ✅ COMPLIANT |
| An Engine Never Performs Model Selection | supports() checks backend family only | `test_llamacpp_supports.py` (3 params: llama_cpp True, vllm/tensorrt_llm/onnxruntime False) | ✅ COMPLIANT |
| An Engine Never Performs Model Selection | Model-specific branch inside engine fails boundary check | No dedicated AST/regression test (unlike `capability-providers`' no-branching guard); verified by manual grep + `ServingPlanLike`'s structural typing (only exposes `.backend`) | ⚠️ PARTIAL (true, not standing-guarded) |
| Residency Lifecycle Constructs and Frees One Model Per Session | acquire creates one Llama, one session, one lock | `test_llamacpp_residency.py::test_two_acquires_give_distinct_session_ids_and_distinct_stub_instances` + code read (`_Residency` per `acquire()` call) | ✅ COMPLIANT |
| Residency Lifecycle Constructs and Frees One Model Per Session | release frees the underlying model | `test_llamacpp_residency.py::test_release_calls_close_exactly_once_and_the_session_becomes_unusable` | ✅ COMPLIANT |
| Streaming Output Is Transport-Agnostic | generate() yields only TextChunk, no gRPC dependency | Code read (no grpc import anywhere in repo) + all streaming tests' `TextChunk(...)` assertions | ✅ COMPLIANT |
| Non-Blocking Thread-Bridge Streaming | Event loop stays responsive during generation | `test_llamacpp_streaming.py::test_loop_stays_alive` | ✅ COMPLIANT |
| Non-Blocking Thread-Bridge Streaming | Chunks in order, exactly one finished=True terminal chunk | `test_llamacpp_streaming.py::test_terminal_semantics` (+2 triangulation tests) | ✅ COMPLIANT |
| Non-Blocking Thread-Bridge Streaming | Abandoning the stream mid-flight releases resources | `test_llamacpp_abandonment.py::test_abandon_releases_lock` | ✅ COMPLIANT |
| Per-Session Lock Serializes Only Calls Sharing That Session | Two sessions of the same model run concurrently | `test_llamacpp_concurrency.py::test_independence_across_sessions` | ✅ COMPLIANT |
| Per-Session Lock Serializes Only Calls Sharing That Session | Two calls on the same session are provably serialized | `test_llamacpp_concurrency.py::test_serializes_within_session` | ✅ COMPLIANT |
| Injectable Llama Factory for SDK-Free Unit Testing | Unit tests run without llama_cpp installed | Full suite: 750 passed / 4 skipped with `llama_cpp` absent (verified independently) | ✅ COMPLIANT |
| Injectable Llama Factory for SDK-Free Unit Testing | Default factory imports the SDK only when invoked | `test_llamacpp_sdk_free.py::test_importing_the_module_does_not_import_llama_cpp` + independent `sys.modules` check | ✅ COMPLIANT |
| llama-cpp-python Is an Optional Extra | Core install excludes llama-cpp-python | `pyproject.toml` `[project.optional-dependencies] llamacpp = [...]` + full suite green without it | ✅ COMPLIANT |
| ChatProvider Composition Stays Out of Scope | ChatProvider is unchanged and still raises | Direct read of `capabilities/chat.py`: zero fields, `execute()` raises `NoBackendAvailableError`, no reference to `LlamaCppTextBackend`/`engines` | ✅ COMPLIANT |

**`backend-adapter` spec (delta)**

| Requirement | Scenario | Test | Result |
|---|---|---|---|
| Backend Adapter Contract Is Engine-Agnostic | Backend Adapter contract has no concrete backend implementation | `test_no_engine_imports.py::test_backends_source_imports_no_concrete_engine_sdk` (rglob) | ✅ COMPLIANT |
| Backend Adapter Contract Is Engine-Agnostic | A Capability Provider executes only against the contract type | Carried forward from `capability-providers` (unmodified this change); `chat.py` still holds no backend reference | ✅ COMPLIANT |
| Backend Adapter Contract Is Engine-Agnostic | Import guard inspects backends/ recursively, not just top-level | `test_no_engine_imports.py::test_scanner_recurses_into_nested_packages` + `::test_scanner_finds_no_offenders_in_a_clean_nested_package` (real synthetic nested package, not a re-assertion of the flat case) | ✅ COMPLIANT |

**Compliance summary**: 17/18 scenarios fully compliant, 1/18 partial (true and structurally enforced by typing, but not guarded by a dedicated standing regression test — same category of gap as `capability-providers`' one PARTIAL, "Binding Invariants... Source read only... PARTIAL").

---

### Correctness (Static — Structural Evidence)

| Requirement | Status | Notes |
|---|---|---|
| Structural Conformance (no base class) | ✅ Implemented | `LlamaCppTextBackend.__bases__ == (object,)`, pyright-verified |
| LC12 (Engine never performs model selection) | ✅ Implemented | One-line `supports()`, structurally enforced by `ServingPlanLike` |
| LC2/LC3 (per-session residency side table) | ✅ Implemented | `_Residency` dict keyed by `session_id`, one `Llama` per `acquire()` |
| LC4/LC5 (per-session lock, await-free finally) | ✅ Implemented | Verified by direct code read, lines 284–322 |
| LC6/LC7 (bounded queue thread bridge, backpressure/abandonment polling) | ✅ Implemented | `_QUEUE_MAXSIZE=8`, `_put`'s polling loop |
| LC8 (one-token lookahead terminal semantics) | ✅ Implemented | `pending` variable in `generate()`'s consume loop |
| LC9 (all SDK interaction off event loop) | ✅ Implemented | `acquire`/`release` via `asyncio.to_thread`, `generate()`'s pump on dedicated `Thread` |
| LC10 (`_Token`/`_Failure`/`_Done` queue union) | ✅ Implemented | Frozen slotted dataclasses, `isinstance`-narrowed |
| LC11 (lazy SDK import via `importlib.import_module`) | ✅ Implemented | Confirmed empirically, `sys.modules` check |
| Zero gRPC dependency | ✅ Implemented | No `grpc` import anywhere in `src/tibios_ray/` |
| `backends/` engine-agnostic (recursive) | ✅ Implemented | `rglob`, mutation-style synthetic nested-package test |
| `ChatProvider` untouched | ✅ Implemented | Zero fields, unconditional raise, no new imports |

---

### Coherence (Design Match)

All design decisions LC1–LC12 traced against the actual implementation; no deviations found beyond those the apply-progress record itself already disclosed and justified (e.g. `_pump` catching `Exception` not `BaseException`, matching `WorkerRuntime._dispatch` precedent; `_Residency` as a non-frozen `slots=True` dataclass per LC2's own stated rationale). File Changes table matches actual files touched (`engines/__init__.py`, `engines/llamacpp.py`, `pyproject.toml`, `tests/unit/backends/test_no_engine_imports.py`, `tests/unit/engines/**`, `tests/integration/**`; `capabilities/chat.py` untouched).

---

### TDD Compliance (Strict TDD Mode)

Per apply-progress's own detailed RED/GREEN/TRIANGULATE/REFACTOR tables (Slices 1–3): every test file has a documented RED phase confirmed failing for the *right* reason (`NotImplementedError`, `ModuleNotFoundError`, or genuine `TypeError` from missing test infrastructure — explicitly distinguished from "wrong-reason RED" import-path mistakes that were caught and fixed before being treated as meaningful, e.g. the Slice 1 `stub_llama` import-path bug). No evidence of tests written after implementation to backfill coverage. Two legitimate deviations are disclosed and justified in apply-progress: (1) Slice 1's `generate()` stub had to exist as a one-line `raise NotImplementedError` to satisfy the Protocol's structural signature for the Slice 1 conformance test — this is not a violation, it's how a Protocol-conformance RED test is even expressible before the real method exists; (2) several Slice 2/3 tests report "RED — passed immediately" once shared test infrastructure (e.g. `StubLlama`'s new fields) landed together, since the underlying mechanism (thread bridge) is inherently monolithic — documented, not silently glossed over.

No stub-satisfying-tautological-test pattern found in the spot-checked tests (see Independent Verification item 8 above).

---

### Success Criteria (from `proposal.md`, all 8, independently verified)

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | `LlamaCppTextBackend` satisfies `TextGenerationBackend` (pyright-verified, no base class) | ✅ PASS | `uv run pyright`: 0 errors; `LlamaCppTextBackend.__bases__ == (object,)` |
| 2 | Unit suite passes with `llama_cpp` not installed — no weights, no network | ✅ PASS | 750 passed / 4 skipped, `llama_cpp` confirmed absent from venv and `sys.modules` |
| 3 | `generate()` yields more than one chunk for a multi-token stub completion (proves no buffering) and exactly one `finished=True` terminal chunk | ✅ PASS | `test_terminal_semantics`: `len(chunks) > 1`, `finished` flags `[False, False, True]` |
| 4 | Two concurrent `generate()` calls on one session are provably serialized, never interleaved | ✅ PASS | `test_serializes_within_session`: `activity_log == [enter,exit,enter,exit]`, `max_active_count <= 1` |
| 5 | Abandoning a stream mid-flight releases the lock and stops the underlying generator | ✅ PASS | `test_abandon_releases_lock`: `stub.closed.wait(1.0)` True, follow-up `generate()` on same session completes |
| 6 | `backends/` tree imports no engine SDK under recursive inspection | ✅ PASS | `test_backends_source_imports_no_concrete_engine_sdk` (rglob) + synthetic nested-package recursion proof |
| 7 | `ChatProvider` still raises `NoBackendAvailableError`; no field added | ✅ PASS | Direct code read: zero fields, unconditional raise, no new imports |
| 8 | Opt-in integration test passes against a real tiny GGUF when a path is supplied | ⚠️ NOT EXECUTED (by design) | Test exists (`tests/integration/test_llamacpp_smoke.py`, 4 scenarios), correctly `skipif`-gated, structurally sound on read — but no real GGUF file or `llama_cpp` install is available in this verification environment, so it could not actually be run against real weights. This is expected per the proposal's own "opt-in, zero CI cost" design, not a defect — but it means criterion 8 remains **unproven in practice**, only proven-by-construction. |

**Result: 7/8 fully pass with direct execution evidence; 1/8 (integration smoke test) passes structurally but is unexecuted against a real model in this environment — inherent to its opt-in design, not a regression.**

**On checkbox convention**: I checked prior archived changes for precedent. `capability-providers`' `proposal.md` had its Success Criteria checked `[x]` in the *final apply commit* (`eb56460`, "feat(capabilities): add OCR Provider"), not in the verify-report commit (`6ad52bce`, which only added the report file, zero changes to `proposal.md`). `model-catalog`'s `proposal.md` Success Criteria remained **unchecked `[ ]`** even after archiving (confirmed by reading the archived copy at `openspec/changes/archive/2026-08-06-model-catalog/proposal.md`). There is no consistent repo convention of verify checking these boxes — it is inconsistent even between the two precedent changes. Given that inconsistency, I did **not** edit `proposal.md`'s checkboxes myself; the pass/fail table above stands as the verification record. (SUGGESTION below: recommend the apply phase check these consistently, matching `capability-providers`' pattern, since it is the more complete precedent — but this is a process nit, not a code defect.)

---

### Issues Found

**CRITICAL (must fix before archive): None.**

**WARNING (should fix, does not block archive):**

1. LC12 ("An Engine Never Performs Model Selection" — the user-mandated non-negotiable requirement) is true today and structurally reinforced by `ServingPlanLike`'s narrow `.backend`-only surface, but has no dedicated automated regression test (an AST no-branching scan, mirroring `capability-providers`' precedent for its own Binding Invariants) standing guard against a future engine adding model-identity logic. Currently enforced only by code review + the type system's absence of a `.model` attribute on `ServingPlanLike`. Recommend a follow-up test (e.g. `test_llamacpp_no_model_identity_logic.py`, AST-scanning `engines/llamacpp.py` for `model`/`family`-referencing conditionals) to close this the same way `test_llamacpp_layering.py` closes the import-boundary gap.

**SUGGESTION (nice to have):**

1. Success-criterion 8 (opt-in integration test) is structurally sound but has never actually been run against a real GGUF file in any environment this verify pass had access to — the "stubbed seam diverges from the real SDK signature" risk (proposal's own risk table) technically remains open until someone runs it once with `TIBIOS_RAY_LLAMACPP_GGUF` set. Not a blocker (this is exactly the intended zero-CI-cost tradeoff), but worth a manual one-time run before relying on this adapter in anger.
2. The repo's checkbox-on-`proposal.md`-Success-Criteria convention is inconsistent between the two available archived precedents (`capability-providers` checked at final-apply-commit time; `model-catalog` never checked even post-archive). Recommend picking one convention going forward (e.g. always check at apply's final commit, per `capability-providers`) to avoid this ambiguity recurring at the next verify.

---

### Overall Verdict

**PASS WITH WARNINGS.** 0 CRITICAL, 1 WARNING, 2 SUGGESTIONS. All 34/34 tasks complete and independently re-verified against the actual implementation (not just apply-progress's self-report). Test suite (750 passed / 4 skipped), ruff, and pyright are all clean and independently reproduced with the exact counts apply-progress reported. All 4 rigorously-flagged non-negotiable claims from the orchestrator's brief hold: (1) `supports()` genuinely checks only `plan.backend`, no model-identity branching found anywhere; (2) `generate()` yields only `TextChunk`, zero gRPC imports anywhere in the module or its transitive imports; (3) the lock is genuinely per-session (`_Residency.lock`, fresh instance per `acquire()` call in the `_sessions` dict, no adapter-level lock exists); (4) the `finally: stop_event.set()` performs no `await` on any exit path; (5) `default_llama_factory` imports `llama_cpp` lazily, confirmed empirically via `sys.modules`. `ChatProvider` is confirmed genuinely untouched. 7/8 proposal Success Criteria pass with direct execution evidence; the 8th (opt-in integration smoke test) is structurally sound but unexecuted in this environment by design. No issue found rises to CRITICAL severity — safe to proceed to `sdd-archive`.
