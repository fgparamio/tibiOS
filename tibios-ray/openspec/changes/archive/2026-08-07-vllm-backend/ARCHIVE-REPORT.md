# Archive Report: vLLM Backend

**Change**: vllm-backend
**Archived**: 2026-08-07
**Status**: COMPLETE — fully implemented, verified, and closed

## Executive Summary

`VllmTextBackend` is tibios-ray's second concrete Backend Adapter, executing `chat.generate` against vLLM's `AsyncLLM` with native-async streaming and a shared, refcounted Model Runtime (one engine instance per distinct model, reused across sessions). All 27 tasks completed; verification passed with 0 CRITICAL, 0 WARNING, and 2 informational SUGGESTIONs (neither blocking). Merged to main via PR #14.

This change had an unusual history worth recording: it was implemented and locally gated on 2026-08-06 but never pushed, sitting 60 commits behind `main` — missing the entire `worker-context-wiring` gRPC transport epic — until this session rebased it, corrected a same-day regression (an incorrect project-wide Python 3.14→3.13 downgrade introduced while working around vLLM's `torch==2.7.0` lacking a cp314 wheel), and landed it for real.

## Scope Summary

### What Was Built

`src/tibios_ray/engines/vllm.py` — `VllmTextBackend`, structurally satisfying `TextGenerationBackend` (Protocol conformance, no base class). Key mechanisms:

- **Model Runtime**: lazy, single-flight, refcounted engine construction — one `AsyncLLMLike` instance per distinct model, shared across all sessions of that model, torn down only on last release.
- **Native-async streaming**: `generate()` consumes the engine's `AsyncGenerator` directly — no thread, queue, or polling bridge (contrast with `llamacpp-text-backend`'s thread+queue bridge, since vLLM's engine is natively async where llama.cpp's is not).
- **Uniform cancellation**: explicit engine-level abort in a `finally` block on every exit path, absorbing vLLM v0/v1's inconsistent generator-GC cancellation behavior behind one Worker-visible contract.
- **SDK-free unit tier**: injectable `AsyncLLMLike` factory Protocol; importing `engines/vllm.py` requires neither `vllm`, `torch`, nor CUDA; the real SDK is imported lazily inside the default factory, only at first-acquire time.
- **Optional extra**: `vllm` is declared under `[project.optional-dependencies]`, absent from the core install and from the unit test tier.

### Architecture Decisions (VL1-VL14)

Full rationale in `design.md` (this archive) and Engram obs #137. Verified directly against shipped source during `sdd-verify`, not merely described:

- **VL8/LC11 precedent**: lazy `importlib` SDK seam, mirroring `llamacpp-text-backend`'s LC11 — the unit tier must never require the extra.
- **VL9**: `TextChunk.finished` sourced from the underlying output's `finished` field only, never inferred by lookahead — marked in source with a mandatory `# DELTA, not CUMULATIVE — see VL9` comment, pinned by its own test.
- **VL14**: single-owner `entry.live.pop()` — the fix for a double-abort race, present in both `release()` and `generate()`'s `finally` block.
- Backend Independence Principle (shared with `llamacpp-text-backend`): a Backend defines what operations are available, never how model residency is implemented — `BackendSession` stays identity-only (`backend_id`, `session_id`) regardless of whether residency is session-owned (llama.cpp) or shared/refcounted (vLLM).

### New Specifications

- **vllm-text-backend** (new): the full Backend spec — structural conformance, Model Runtime sharing/single-flight/refcounted teardown, native-async streaming, transport-agnostic output, uniform cancellation, SDK-free unit testing, optional-extra packaging.
- **backend-adapter** (delta merged): added the `BackendSession Carries No Model Residency` requirement, generalizing the Backend Independence Principle now that two structurally opposite residency shapes (`llamacpp-text-backend`'s per-session side table vs. `vllm-text-backend`'s shared Model Runtime) both prove it holds.

## Verification & Gate Status

### Verify Report Summary

- **Verdict**: PASS
- **Critical Issues**: 0
- **Warnings**: 0
- **Suggestions**: 2 (both optional test-strengthening additions, not defects)

| # | Type | Note |
|---|------|------|
| 1 | SUGGESTION | Add a `dataclasses.fields(BackendSession)`-based exact-field-set test |
| 2 | SUGGESTION | Add one cross-backend test proving both llamacpp and vllm sessions share the identity-only shape |

**Observation IDs for Traceability**:
- Verify Report: Engram obs #192

### Test Results

Command: `uv run pytest -q`

```
971 passed, 9 skipped in 2.18s
```

- vLLM-scoped subset: 54 passed, 5 skipped (skips are opt-in GPU smoke tests, correctly gated behind `TIBIOS_RAY_VLLM_MODEL`)
- Failures: 0

### Code Quality Gate

| Tool | Command | Status |
|------|---------|--------|
| ruff | `uv run ruff check .` | ✓ PASS — zero violations |
| pyright | `uv run pyright` | ✓ PASS — zero errors, zero warnings |

### Python 3.14 Regression — Caught and Corrected During Rebase

The branch's rebase surfaced a same-day commit that had silently downgraded the whole project (`pyproject.toml` `requires-python`, `.python-version`, `[tool.pyright] pythonVersion`, `[tool.ruff] target-version`, `README.md`, `CLAUDE.md`) from Python 3.14 to 3.13, to route around vLLM's `torch==2.7.0` pin lacking a cp314 wheel. This was reverted: the project stays on 3.14 project-wide; the `vllm` extra alone carries a `python_version < '3.14'` marker, letting `uv sync --extra vllm` target a dedicated 3.13 environment until upstream ships a cp314 build. Verified live: stripping the marker and running `uv lock` reproduces the exact `torch==2.7.0` resolution failure the marker exists to prevent.

## Archived Artifacts

All change artifacts have been moved to `openspec/changes/archive/2026-08-07-vllm-backend/`:

```
openspec/changes/archive/2026-08-07-vllm-backend/
├── proposal.md                    (Intent, scope, approach)
├── design.md                      (VL1-VL14 decisions)
├── tasks.md                       (27 tasks, all complete)
├── ARCHIVE-REPORT.md              (This file)
└── specs/
    ├── backend-adapter/spec.md    (Delta: BackendSession residency-free invariant)
    └── vllm-text-backend/spec.md  (New: full Backend spec)
```

## Merged Specifications

| Main Spec | Action | Details |
|-----------|--------|---------|
| `openspec/specs/vllm-text-backend/spec.md` | CREATED | Full spec from delta (9 requirements, new) |
| `openspec/specs/backend-adapter/spec.md` | MERGED | Added "BackendSession Carries No Model Residency" requirement |

## Next Steps

The change is **complete**. No follow-up work required for this change itself. The two verify SUGGESTIONs are optional test-strengthening, deferrable indefinitely. Out of scope for this change, tracked separately:

- ONNX Runtime backend (in progress in a separate worktree, `sdd-explore` phase done, `sdd-propose` next)
- TensorRT-LLM, Faster-Whisper backends (not yet started)

## Verification Chain

1. All artifacts read from Engram and the openspec filesystem
2. Verify report (obs #192) confirmed PASS, 0 CRITICAL/0 WARNING
3. Live test/lint/type re-run in this archive pass: 971 passed/9 skipped, ruff clean, pyright clean
4. Python 3.14 restoration independently re-confirmed coherent across `pyproject.toml`

## Archive Closure

This change is now closed. The change folder `openspec/changes/vllm-backend/` has been moved to archive. All change state is persisted:
- Engram: Proposal (obs #133), Spec (obs #134), Design (obs #137), Verify Report (obs #192)
- OpenSpec: Proposal, Design, Tasks, both specs (one new, one merged delta)
- This archive report serves as the final closure record

The SDD cycle is complete.
