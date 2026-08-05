# TibiOS Admission Control

Version: 1.0

## Purpose

Admission Control determines whether a Workload is eligible to enter the scheduling pipeline. It never performs scheduling and never decides where a Workload runs — it decides whether planning should begin.

**Admission is authoritative** — not a passive filter. It owns the admission decision, the idempotency of that decision, and the administrative consumption (quotas, limits, budgets) associated with it. Once a Workload is accepted, the Scheduler's only job is to plan.

Admission creates administrative commitments. Allocation creates execution commitments (`15-allocation-model.md`).

This document follows the principles in `00-philosophy.md` and `02-project-structure.md`.

## Core Principles

Reject early. Schedule only valid Workloads. Admission decisions are idempotent. Quota ownership is partitioned. Persistent facts are authoritative; in-memory state is rebuildable. Administrative state is authoritative.

## Responsibilities

Validating Workload requests, enforcing admission policies and quotas, recording admission decisions, guaranteeing admission idempotency, maintaining rebuildable quota projections.

Admission Control never schedules Workloads, selects Nodes, allocates Resources, creates Allocations, performs placement, or executes Workloads.

## Architectural Position

```
Workload → Requirement Analysis → Admission Control ──┬── Accepted ──→ Scheduling Engine
                                                        └── Rejected
```

## Workload Identity and Idempotency

Every admission request contains a `WorkloadId` (ULID, per Runtime Primitives) — the idempotency key for admission. A network retry must reuse the same `WorkloadId`; it must never create a second logical Workload.

```
Admission Request → WorkloadId Lookup ──┬── Existing → Return Recorded Decision
                                          └── New → Validation → Policy Evaluation → Quota Authority → Admission Record → Persist → Admission Decision
```

If the same `WorkloadId` is received again, Admission Control returns the previously recorded decision — it never re-evaluates quota, consumes quota again, or creates a second Admission Record.

## Validation and Policy Evaluation

Validation verifies Workload integrity, schema correctness, required fields, supported execution model, supported Runtime version — invalid Workloads never reach scheduling.

Policy Evaluation determines whether execution is *permitted* (maximum duration, allowed execution classes, tenant/namespace restrictions, administrative policy) — Policies determine eligibility, never placement.

## Cluster Summary, Not Cluster Snapshot

Admission Control consumes a lightweight **Cluster Summary** — coarse cluster-wide capability (GPU available anywhere? WASM support? AI Workers available? maintenance mode?) — rather than the full Cluster Snapshot the Scheduling Engine uses. Building the full per-node Snapshot for every admission check would be disproportionate: "admission should remain inexpensive relative to scheduling." Both views are derived from the same State Assembler observations, at different granularity.

Admission Control never selects individual Nodes or Resources — that fine-grained filtering belongs entirely to the Scheduling Engine.

## Admission Decisions

Exactly one of: `Accepted` (may enter scheduling — never a placement guarantee), `Queued` (eligible, execution delayed by Runtime policy), `Deferred` (blocked on an external condition — dependency unavailable, maintenance window, scheduled execution, administrative approval; not equivalent to Rejected), `Rejected` (never enters scheduling, with a machine-readable reason: invalid request, unsupported Runtime, policy violation, quota exhaustion, authorization failure).

## Quota Authority: Atomic, Partitioned, Never Global

Quota is not a Resource — it is an administrative token, and it must be consumed atomically to avoid a classic check-then-act race (two concurrent requests both observe "quota available" before either decrements it, over-admitting past the limit).

A single global quota counter would violate `00-philosophy.md`'s Ownership-reduces-synchronization principle directly — contention, cache-line bouncing, a global lock, worse scalability. Instead, quota is **partitioned by scope** (tenant, namespace, project) into independent `Quota Account`s, implemented as one actor per scope:

```
Quota Service
      │
      ├── Quota Actor — Tenant A
      ├── Quota Actor — Tenant B
      └── Quota Actor — Tenant C
```

Actor serialization guarantees atomicity against **concurrent access** for a single scope — no two mutations to the same account execute simultaneously. Independent scopes never compete with each other.

### Concurrency Atomicity Is Not Crash Durability

These are two distinct problems that "atomicity" often blurs together. Actor serialization solves the first (no interleaving between concurrent requests to the same account) but not the second: if the actor updates in-memory state and then the process crashes *before* persisting, the durability guarantee is gone regardless of how sequential the actor's processing was.

**Therefore the Quota Actor's in-memory state is never the source of truth — it is a rebuildable projection of the Admission Log (`21-runtime-storage-engine.md`).**

```
Admission Log (authoritative)
        │
        ▼
    Replay
        │
        ▼
Quota Projection (Quota Actor, rebuildable)
```

The correct write order for an Admission Transaction is:

```
Validate
    │
    ▼
Reserve Quota
    │
    ▼
Append Admission Record
    │
    ▼
Admission Record Persisted
    │
    ▼
Update Quota Projection
    │
    ▼
Return Admission Decision
```

The Admission Record must become durable *before* updating the in-memory projection or acknowledging success — reversing this order is the exact bug this ordering exists to prevent.

### Recovery

```
Restart → Load Projection Checkpoint → Replay New Admission Records → Rebuild Quota Account → Ready
```

Checkpoints optimize recovery; the Admission Log remains authoritative. Recovered state must be equivalent, for every committed Admission Record, to the state before failure. Quota release is also an authoritative fact — release must be durably recorded, never inferred solely from mutating an in-memory counter.

Replay reconstructs Quota Projection. It never reconstructs physical Resource usage (`14-resource-model.md`) — that is re-observed, not replayed.

## Resource Separation

Administrative quota is distinct from physical Resource allocation. Admission Control owns administrative quotas; the Runtime owns Resources and Allocations (`14-resource-model.md`, `15-allocation-model.md`). Admission Control never reserves CPU, memory, GPU, or storage. Admission never owns execution capacity.

## Separation of Responsibilities

Admission Control answers "should this Workload enter scheduling?" The Scheduling Engine answers "where should it execute?" Runtime Materialization answers "can this Allocation Plan still be materialized?" These remain independent (`16-scheduling-engine.md`, `15-allocation-model.md`).

## Observational vs Authoritative State

Not every mutable state requires an authoritative log (`00-philosophy.md`). Admission Records and Quota Accounts are authoritative (cannot be reconstructed by observing reality) and require one; Health, Heartbeats, and resource usage are observational and do not.

## Failure

Admission failures never produce partially committed admissions — a Workload is either durably admitted or not; there is no externally visible intermediate state. A failure never consumes quota without producing a durable Admission Record.

## Performance

Admission should remain inexpensive relative to scheduling. Scalability is achieved through partitioned ownership — independent quota scopes never serialize against each other.

## Storage Requirements

Admission Control requires the Runtime Storage Engine (`21-runtime-storage-engine.md`) to support: durable Admission Records, idempotent lookup by `WorkloadId`, ordered replay within each quota scope, atomic admission commit semantics, projection checkpoints, and recovery after process failure. Admission depends on Storage through an outbound port defined by Admission itself, per `02-project-structure.md`.

## Anti-Patterns

Avoid: scheduling during admission, physical Resource allocation, global quota locks, check-then-act quota evaluation, authoritative in-memory quota state, non-idempotent retries, duplicated Admission Records, hidden quota mutation, treating caches as sources of truth.

## Review Checklist

Before adding an Admission capability ask: does it determine eligibility? Does it belong before scheduling? Who owns the mutable state? What is the authoritative source of truth? Is it idempotent by `WorkloadId`? Is quota mutation atomic? Can it recover after a crash? Can independent quota scopes progress independently? Is it fully observable?

## Principles

- Admission determines eligibility. Scheduling determines placement. The Runtime determines execution.
- Quota ownership is partitioned by scope; actors serialize concurrent mutation within a scope only.
- Persistent facts provide durability. In-memory state is rebuildable.
- Every mutable state has exactly one authoritative owner. Every authoritative state has exactly one source of truth.
- Administrative decisions become authoritative facts only after durable persistence.

## Motto

Reject early. Admit once. Persist before acknowledging. Rebuild from facts. Never schedule invalid work.
