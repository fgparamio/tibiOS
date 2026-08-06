# Proposal: Python Foundation

## Intent

`tibios-ray` is one of two Worker implementations for `tibios-core`'s Runtime (the heavy AI path, reached over gRPC; `local-infer` is the in-process one). Today it is a placeholder: one `__init__.py` with a `main()` that prints, no tests, no lint, no type checker.

The gRPC/proto contract this project must eventually implement (per the Worker contract in `../tibios-core/docs/architecture/18-worker-model.md`) **does not exist yet** in any shared location between the Rust and Python repos — candidate `../TibiOS/proto/`, neither created nor decided. Rather than block on that cross-repo decision, this change builds the skeleton only. It mirrors how `tibios-core`'s own `workspace-foundation` change deferred public domain traits to a follow-up.

## Scope

### In Scope

- Package layout `src/tibios_ray/{__init__.py, server.py, worker.py}`. `server.py` and `worker.py` are **stubs — module docstring only**, citing the doc they will implement: `server.py` → future gRPC Worker contract (`18-worker-model.md`); `worker.py` → AI Runtime specialization (`25-ai-runtime.md`), i.e. future dispatch to internal capability handlers.
- Dev tooling in `pyproject.toml` as dev-dependencies: `pytest`, `ruff`, and `pyright` (chosen over mypy: zero-config on a fresh codebase, faster feedback, no stub bootstrapping). Sane default config for `ruff` and `pyright`.
- `tests/test_smoke.py`: one test asserting `import tibios_ray` succeeds.

### Out of Scope

- gRPC server implementation; Ray integration / distributed execution logic.
- Model backends (llama.cpp, vLLM, TensorRT-LLM, ONNX Runtime, …).
- Internal capability-dispatch design (Chat/Embedding/Vision providers). **Naming constraint for that future work — resolved in `ray-worker-runtime`**: these MUST NOT be called "Workers" — "Worker" is reserved in `18-worker-model.md` for the whole `tibios-ray` process as seen by the Runtime. Settled name: **Capability Provider** (not "Handler" — implies a callback/endpoint; not "Adapter" — a Provider can support multiple model families, not just one).
- Model Selection Policy, model catalog format, anything model-family-specific (Qwen/Llama/DeepSeek/Kimi/Gemma/Mistral).

## Capabilities

### New Capabilities

- `python-foundation`: package layout, dev tooling (pytest/ruff/pyright via `uv run`), and smoke test for the `tibios_ray` package.

### Modified Capabilities

- None.

## Approach

Extend `pyproject.toml` with a dev-dependency group and `[tool.ruff]` / `[tool.pyright]` sections; add two docstring-only modules and a `tests/` directory. No business logic anywhere. All commands run through `uv run`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `pyproject.toml` | Modified | dev-deps + ruff/pyright config |
| `src/tibios_ray/server.py` | New | docstring-only stub |
| `src/tibios_ray/worker.py` | New | docstring-only stub |
| `tests/test_smoke.py` | New | import smoke test |

## Open Design Questions (non-blocking)

Neither question affects the Runtime, the Worker Contract, the SDK, gRPC, or `architecture-v1.0`. Both are internal `tibios-ray` decisions for later — **not blockers for this change**.

1. **Inference Intent layer?** Should an internal enum (`reasoning`, `coding`, `creative`, `fast`, `vision`) sit between a Runtime-visible capability (e.g. `chat.generate`) and the Model Selection Policy? It would keep the policy from degenerating into ad-hoc conditionals (`if reasoning && tools && context > 128k …`).
2. **Declarative model catalog?** Should family/variant → capability, minimum resources, and compatible backend live in loaded descriptors (YAML/TOML/JSON) rather than code registration — so supporting a new model generation is "add a descriptor file"?

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Stub modules drift from the eventual proto contract | Med | Docstrings cite the authoritative doc; no code to become stale |
| `pyright` choice regretted vs `mypy` | Low | Config-only swap; no source annotations are tool-specific |
| Python 3.14 tooling gaps | Low | Pin ranges, not exact versions; verify in apply |

## Rollback Plan

Revert the single commit. All changes are additive (two stub files, one test file, one `pyproject.toml` section); no existing behavior is touched, so `git revert` restores the placeholder state exactly.

## Dependencies

- None. Explicitly independent of the unresolved `../TibiOS/proto/` decision.

## Success Criteria

- [x] `uv run pytest` passes
- [x] `uv run ruff check` passes
- [x] `uv run pyright` passes
- [x] `src/tibios_ray/{server,worker}.py` exist with docstrings only — zero business logic

## Applied

Applied directly (not through the full spec/design/tasks pipeline — user explicitly
requested a direct apply given the small, mechanical scope). `pytest`, `ruff`, `pyright`
added as dev dependencies; `[tool.ruff]`/`[tool.pyright]` configured in `pyproject.toml`;
`src/tibios_ray/{server,worker}.py` created as docstring-only stubs (`worker.py`'s
docstring already uses the `Capability Provider` terminology settled in
`ray-worker-runtime`, per that proposal's Risks note); `tests/test_smoke.py` added. All
three Success Criteria commands verified passing.
