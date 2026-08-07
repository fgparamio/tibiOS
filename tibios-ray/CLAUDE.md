# tibios-ray

This project is one of two Worker implementations for TibiOS's Runtime — the heavy AI execution path, reached from `tibios-core` over gRPC. `local-infer` (in-process, llama.cpp) is the other; the Runtime treats both as interchangeable Workers and knows nothing about which one is running.

## Before touching the gRPC Worker interface

`tibios-core` and `tibios-ray` are two directories in one shared git repository (single `.git` at the `TibiOS/` root, not separate repos) — `git log`/`git branch` here reflect the whole monorepo, not just this directory.

Read these first, from `../tibios-core`, pinned at git tag `architecture-v1.0`:

- `../tibios-core/docs/architecture/18-worker-model.md` — the Worker contract itself: Execution Context, Execution Channel, Execution Events, Execution Report, Execution Pulse, cancellation semantics, the four execution patterns (Batch/Streaming/Long-running Service/Pipeline).
- `../tibios-core/docs/architecture/25-ai-runtime.md` — confirms tibios-ray gets no special treatment: it is a Worker like any other, executing ordinary Objects (`13-object-model.md`) and Resources (`14-resource-model.md`).

Do not duplicate that spec here. If something here seems to contradict it, the contradiction is resolved in `tibios-core`'s architecture docs, not by reinterpreting it locally.

## Contract surface

The gRPC/proto contract between `tibios-core` and `tibios-ray` lives in `../proto/` (sibling of both directories, so both the Rust and the Python build compile against it). `tibios-ray` does not yet consume it — the `.proto` is ahead of this codebase (e.g. `ExecutionContext.worker_capability` has no Ray-side wiring yet). Where this codebase and the `.proto` disagree, the `.proto` wins; treat `18-worker-model.md` as the source of truth only for interface behavior the `.proto` doesn't yet express.

## Conventions

No project-specific conventions yet — this is a fresh skeleton (`uv`, Python ≥3.14, `ray` dependency). Global CLAUDE.md policy applies: conventional commits, no AI attribution.

## Worktree hygiene (mandatory)

`tibios-core` and `tibios-ray` share one `.git` — a worktree checked out anywhere in the monorepo contains BOTH projects. This has caused near-misses:

- One worktree ending up host to two unrelated, concurrently in-flight changes (one per project), where a cleanup driven by one made the other's uncommitted state look at risk.
- Before running `git worktree remove` on any worktree, check `git status --short` in **every** project subdirectory it contains (`tibios-core/`, `tibios-ray/`, not just the one you're working in) — not only your own.
- If something looks uncommitted-and-at-risk, check whether it's already committed/merged upstream (`git log`, `origin/main`) before treating it as unique, unrecoverable work.
- Prefer one worktree per unit of work, and commit early/often (even as unpushed WIP) so nothing valuable exists only as uncommitted state in a working tree.
