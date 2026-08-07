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
