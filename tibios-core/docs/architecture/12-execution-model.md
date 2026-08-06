# TibiOS Execution Model

Version: 1.1

## Purpose

Execution is the core responsibility of the TibiOS Runtime. Applications never execute code directly — applications declare Workloads, and the Runtime transforms Workloads into execution.

Execution is location independent, resource aware, and fault tolerant.

## Core Principle

Applications describe what should happen. The Runtime decides how it happens.

## Fundamental Abstraction

Everything executable is a Workload: function, actor, AI inference, agent, pipeline, service, background task, stream processor. The Runtime does not distinguish between them — they differ only in execution policy.

## Workload Identity

Every Workload owns a unique identifier, owner, type, lifecycle, resource profile, execution policy, security context, and observability context. Identity never changes.

## Execution Flow

```
Application
      │
      ▼
Create Workload
      │
      ▼
Runtime Validation
      │
      ▼
Scheduler
      │
      ▼
Placement
      │
      ▼
Worker
      │
      ▼
Execution
      │
      ▼
Result
```

Every stage is observable.

## Stateless Execution

Workers should remain stateless — persistent state belongs elsewhere (Workers execute, Storage stores).

> This applies to a Workload's *business state* — a Worker never lets one execution's data leak into the next. It does **not** forbid a Worker from caching infrastructure state, such as a resident loaded model: per `13-object-model.md`, that model in VRAM/RAM is a *cache* of the canonical Model Object, never something the Worker owns. A cache surviving between Execution Contexts handled by the same Worker is expected; leaking business state between Workloads is not.

## Ownership / Locality / Isolation

Exactly one Runtime owns every Workload. Execution may migrate; ownership does not.

The Runtime always attempts Compute → Data, never Data → Compute — moving computation is usually cheaper than moving datasets.

Every Workload executes inside an isolated execution context, protecting correctness, security, and recovery.

## Scheduling Independence

The execution model does not know the scheduling algorithm, networking, or storage engine. Execution remains independent.

## Resource Awareness

Every Workload declares minimum, preferred, and maximum resources. The Runtime chooses placement.

## Execution Policies

Examples: Immediate, Delayed, Scheduled, Replicated, Exclusive, Distributed, Streaming, Batch. Execution policy is metadata, not implementation.

## Cancellation / Retry

Cancellation is cooperative — Workloads should terminate cleanly, observably. Retry belongs to the Runtime, not the application, and retry policy is explicit, never implicit.

## Migration / Checkpointing

The Runtime may migrate Workloads and long-running Workloads may create checkpoints — but these policies are scoped, not universal:

- For **Inference** Workloads in the MVP (Paradigm B): failure recovery is simple retry-from-scratch on another island. There is no practical way to migrate a mid-generation inference, and the cost of a full retry is bounded (seconds, not days) — migration and checkpointing do not apply here.
- For **long-running / training** Workloads (Paradigm A / Phase 2, e.g. reserving hundreds of GPUs for days): migration and checkpointing are standard, expected practice.

Applications should not depend on machine identity in either case.

## Failure

Failure produces events, never hidden behavior. Failures may trigger retry, migration, escalation, replication, or compensation — policy determines behavior, scoped as above.

## Resource Leasing

Resources are leased, not permanently owned. Idle resources return to the Runtime.

## Affinity / Priority

Applications may express affinity; the Runtime decides whether it can be honored — affinity is advisory, never mandatory. Priority affects scheduling; it never bypasses correctness.

## Communication

Workloads exchange messages, never shared mutable memory across nodes. Communication is explicit, observable, versioned.

## State

Execution state is temporary; persistent state belongs to storage. The Runtime should survive worker failure.

## Observability / Security

Every execution emits metrics, logs, traces, lifecycle events. Nothing executes invisibly. Execution context includes identity, permissions, capabilities, trust level — security follows the Workload.

## Extensibility

New execution policies may be added without changing existing Workloads. Execution evolves; applications remain stable.

## Anti-Patterns

Avoid: machine-specific execution, hidden retries, hidden migrations, implicit ownership, long-lived mutable global state, scheduler-aware applications, network-aware business logic.

## Review Checklist

Before introducing a new execution feature ask: can applications remain unaware? Does ownership stay explicit? Can execution migrate (if applicable to this Workload kind)? Is recovery automatic? Is execution observable? Does it preserve locality? Can it scale horizontally?

## TibiOS Philosophy

Applications declare intent. Workloads describe execution. The Runtime owns execution. Workers execute. Schedulers coordinate. Storage preserves. Networking transports. Everything else is implementation.

## Engineering Motto

Execution is declarative. Placement is dynamic. Ownership is permanent. Machines are temporary.
