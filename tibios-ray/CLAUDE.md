# tibios-ray

This project is one of two Worker implementations for TibiOS's Runtime — the heavy AI execution path, reached from `tibios-core` over gRPC. `local-infer` (in-process, llama.cpp) is the other; the Runtime treats both as interchangeable Workers and knows nothing about which one is running.

## Before touching the gRPC Worker interface

Read these first, from the sibling repo `../tibios-core`, pinned at git tag `architecture-v1.0`:

- `../tibios-core/docs/architecture/18-worker-model.md` — the Worker contract itself: Execution Context, Execution Channel, Execution Events, Execution Report, Execution Pulse, cancellation semantics, the four execution patterns (Batch/Streaming/Long-running Service/Pipeline).
- `../tibios-core/docs/architecture/25-ai-runtime.md` — confirms tibios-ray gets no special treatment: it is a Worker like any other, executing ordinary Objects (`13-object-model.md`) and Resources (`14-resource-model.md`).

Do not duplicate that spec here. If something here seems to contradict it, the contradiction is resolved in `tibios-core`'s architecture docs, not by reinterpreting it locally.

## Contract surface

The gRPC/proto contract between `tibios-core` and `tibios-ray` must live in exactly one place, shared by both repos (not yet created — proposed location: `../TibiOS/proto/`, a sibling of both repos, since both a Rust and a Python build need to compile against it). Until that exists, treat the Worker contract in `18-worker-model.md` as the source of truth for what the interface must express, even before the concrete `.proto` file exists.

## Conventions

No project-specific conventions yet — this is a fresh skeleton (`uv`, Python ≥3.14, `ray` dependency). Global CLAUDE.md policy applies: conventional commits, no AI attribution.
