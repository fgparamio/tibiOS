# TibiOS Worker

Version: 1.0

## Purpose

Workers execute Workloads. Workers never perform scheduling, allocate Resources, or own cluster state.

This document follows the principles in `00-philosophy.md` and `02-project-structure.md`. It does not redefine Ownership, Ports, or the Object Model.

## Core Principles

Workers own execution. The Runtime owns orchestration. The Scheduling Engine owns planning. Execution is deterministic. Communication is Runtime-owned.

## Responsibilities

Workers are responsible for: preparing execution, executing Workloads, honoring Allocation Contracts, emitting Execution Events, producing Execution Reports, exposing execution observability.

Workers never: schedule, allocate Resources, modify Runtime state, resolve dependencies, decide retries, decide recovery, communicate with the Scheduling Engine.

## Architectural Position

```
Allocation Contract
    │
    ▼
Runtime
    │
creates
    ▼
Execution Context
    │
contains
    ▼
Execution Channel
    │
assigned to
    ▼
Worker
    │
    ├──────────────┐
    ▼              ▼
Execution      Execution
 Events          Report
    │              │
    ▼              ▼
Runtime        Runtime
```

## Execution Context

Workers never receive raw Workloads — they receive an immutable Execution Context containing every piece of information required to execute: Workload, Allocation, Allocation Contract, Dependency References (already resolved — Workers never locate Objects or perform scheduling-time discovery), Worker Capability, Execution Channel, Security Context, Observability Context, Execution Parameters. Workers never request additional execution metadata. Execution Context is immutable after creation. Worker Capability names the behavior the execution requests (e.g. `chat.generate`) so a Worker fronting several providers can dispatch to the right one; it is not the hardware/platform Capability of `14-resource-model.md`.

## Allocation Contract

Workers honor the Allocation Contract, which is immutable during execution: exclusive/shared execution, renewable lease, preemptible, migration allowed, checkpoint required, maximum execution duration. Workers enforce it; the Runtime owns it (`15-allocation-model.md`). Workers consume Allocation Contracts — they never create, modify, or renew them.

## Execution Lifecycle

```
Received
    │
    ▼
Prepared
    │
    ▼
Running
    │
    ├───────────────┐
    ▼               ▼
Completed       Failed
    │               │
    └──────┬────────┘
           ▼
Execution Report
```

Workers execute this lifecycle; the Runtime owns lifecycle management. This is a Worker-local, fine-grained state machine — distinct from the Runtime-wide `WorkloadState` (`Created → Scheduled → Running → Completed/Failed → Recovered`, see `11-runtime.md`). They share the word "Running" but are two separate state machines at two different layers; model them as two separate enums.

Preparation validates the Execution Context, prepares the execution environment, initializes observability, verifies dependency availability, and prepares execution resources — it never performs scheduling.

## Execution Is Not "Return a Result" — It Produces Events, Then a Report

TibiOS supports four execution patterns on the same Runtime: Batch (one result), Streaming (many results), Long-running Service (events), Pipeline (intermediate results, then a final one). Modeling the Worker around "batch job, return a value" was an early design mistake — it does not generalize.

### Execution Channel

The Execution Context contains an Execution Channel, created by the Runtime — Workers write to it; they never own it. Execution does not return results, it emits events. The Runtime decides how events are delivered (gRPC, WebSocket, Server-Sent Events, Kafka, persistent storage); Workers remain transport-agnostic. **A Worker does not even know the concept of "client"** — its entire world is `Execution Context → Execution Channel → emit(event)`. It does not know whether an event ends up in gRPC, a file, another Workload, or a test. This is what makes a Worker trivially unit-testable: a fake Execution Context plus an in-memory channel, no real infrastructure required (`06-testing.md`).

Concretely, the channel is a bounded `tokio::sync::mpsc` (Worker = `Sender`, Runtime = sole `Receiver`) — bounded per the backpressure rule in `05-async-concurrency.md`. The Runtime is the only consumer of a given Worker's channel; fan-out to actual external consumers (a gRPC stream, logs, metrics) happens downstream of that single point via the Runtime's own mechanism (e.g. `tokio::sync::broadcast`).

### Execution Events

A typed stream of `ExecutionEvent`: `OutputChunk`, `Progress`, `Warning`, `CheckpointCreated`, `MetricsSnapshot`, `EndOfStream`. This is what our own core↔ray gRPC contract (`SubmitJob() → stream<Response>`) already was — it simply lacked the formal name.

Execution Events are Runtime Events local to a single execution — not the same category as cluster-wide Runtime Events (`TrustRevoked`, `SessionClosed`, `MemberJoined`, etc., see `22-networking.md`). Both use the word "event" for the same underlying idea (a fact, not a command), but at different scopes; this is not a contradiction, only a distinction worth keeping straight.

### Execution Report

Execution Reports summarize execution — they never transport application output. They contain status, duration, resource usage, execution metrics, trace identifiers, logs, and failure information. Application data travels through the Execution Channel; operational data belongs to the Execution Report.

**"Execution produces events. Completion produces a report."**

## Isolation and Worker Reuse

Every execution occurs inside an isolated Execution Context; Execution Contexts never share mutable state. Communication occurs through Objects, Messages, and Storage — never global mutable state.

Workers are reusable; Execution Contexts are not. A Worker may execute multiple independent Contexts sequentially. Execution state never survives between Contexts — but **private caches owned by the Worker may survive between executions when permitted by Runtime policy**: a loaded AI model, a compiled WASM module, a JIT cache. These caches are implementation details and never become globally shared state.

> This is the resolution that lets a Worker remain "stateless" (`12-execution-model.md`) despite holding a multi-gigabyte model resident in memory: the loaded model is a *cache* of the canonical Model Object (`13-object-model.md`), owned by `runtime-object`, never something the Worker itself owns. The cache legitimately persists across multiple Execution Contexts handled by the *same* Worker; it is never shared with a different Worker.

## Execution Pulse

Workers publish an Execution Pulse describing the health of a single execution — distinct from process health, and deliberately not called a "heartbeat," since that term is already used for node/process liveness in Networking and Health (`22-networking.md`, `17-cluster-snapshot.md`). One Worker may execute many Workloads over its lifetime; a Pulse belongs to one execution, never to the process.

## Cancellation

Cancellation is cooperative. The Runtime issues a cancellation request; Workers acknowledge, perform cleanup, terminate execution, emit final events, and generate an Execution Report. Forced termination belongs to the Runtime. Cancellation is *requested* by the Runtime; completion remains *owned* by the Worker — ownership holds even mid-cancellation.

## Resource Usage and Failure

Workers consume Allocations; they never modify or request additional Resources — Resource ownership belongs exclusively to the Runtime. Workers report failures; they never decide recovery (retry, restart, migration, escalation) — that is Runtime policy, and Workers remain unaware of the strategy.

## Checkpointing

Checkpointing is optional. Future Runtime versions may introduce manual, automatic, or migration checkpoints. Workers expose checkpoint capabilities; the Runtime decides when they are used. Checkpoint creation is a Worker capability; checkpoint policy belongs to the Runtime.

## Worker Types

The Runtime may support multiple Worker implementations — Native Rust Worker, Python Worker, WASM Worker, GPU Worker, AI Inference Worker — every Worker follows the same execution semantics.

> Concretely, this is the trait both `local-infer` (llama.cpp, in-process, CPU-bound — must run on a dedicated blocking thread pool per `05-async-concurrency.md`, never directly on a Tokio task) and tibios-ray (external Python process, via the gRPC contract) implement. From the Runtime's perspective they are interchangeable Workers.

## Observability and Security

Workers emit logs, metrics, traces, an execution pulse, and execution events — execution is fully observable. Execution Reports are authoritative execution facts (`21-runtime-storage-engine.md`); Execution Events describe execution as it unfolds. Workers execute under the Security Context supplied by the Runtime; they never authenticate nodes, establish trust, or validate cluster membership — that belongs to Networking/Trust (`22-networking.md`).

## Anti-Patterns

Avoid: scheduling inside Workers, Resource allocation, Runtime state mutation, dependency discovery, hidden retries or migrations, transport-specific logic, global mutable state.

## Review Checklist

Before adding a Worker capability ask: does it belong to execution? Should the Runtime own it instead? Does it preserve deterministic execution? Does it require scheduling knowledge? Does it remain transport-independent? Does it preserve isolation?

## Principles

- Workers own execution. The Runtime owns orchestration and communication.
- Execution produces events. Completion produces a report.
- A Worker never knows the concept of a client.
- Private caches may survive across Execution Contexts of the same Worker; business state never does.

## Motto

Execute faithfully. Stream continuously. Report completely. Own nothing except execution.
