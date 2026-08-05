# TibiOS Cluster Snapshot

Version: 2.0

## Purpose

The Cluster Snapshot is an immutable observation of the cluster at a specific point in time — the bridge between the mutable Runtime and the pure Scheduling Engine (`16-scheduling-engine.md`).

This document follows the principles in `00-philosophy.md` and `02-project-structure.md`. It does not redefine Ownership, Object identity, or the Authoritative/Observational distinction.

## Core Principle

Planning is based on observations. Execution is based on reality. These concerns are intentionally separated: the Runtime owns reality, the Scheduling Engine never operates on live state, only on immutable Snapshots. This guarantees deterministic planning while allowing concurrent execution.

```
Runtime → creates → Cluster Snapshot → consumed by → Scheduling Engine
                                                            │
                                                     produces Allocation Plan
                                                            │
                                                validated by → Runtime → materializes → Allocation
```

## Layer Responsibilities: Separated by Volatility, Not Only by Function

Every architectural layer answers exactly one question, at its own natural rate of change (`00-philosophy.md`'s Volatility principle):

| Layer | Question | Volatility | Owner |
|---|---|---|---|
| Trust | Can this node be trusted? | Very low | Trust |
| Membership | Is this trusted node currently part of the cluster? | High | Membership |
| Health | Can this node currently execute work? | Very high | Health |
| Resources | What execution capacity is currently available? | Very high | `runtime-scheduler` (`14-resource-model.md`) |

Mixing data with radically different volatility in one component causes unnecessary cache invalidation, unnecessary recomputation, and unnecessary coupling. Trust should never be recomputed because a heartbeat arrived; Membership should never require repeating cryptographic authentication.

Only Runtime-approved (trusted, per Networking) members appear inside a Snapshot at all.

## Snapshot Contents

A Snapshot contains Runtime-approved Nodes, Health observations, Resource summaries, Allocation summaries, cluster topology, and Runtime capabilities — only scheduling-relevant information, never mutable Runtime objects or secrets/credentials.

A Snapshot contains observations. It never contains authoritative Runtime state.

### Mutable vs Immutable Dependencies

Consistent with the dual identity scheme (`13-object-model.md`):

- Mutable Objects (Node, Resource, Logical Object Reference, Allocation Summary) are represented by Object ID + Object Version.
- Immutable Objects (Model Artifact, Dataset Chunk, Binary Artifact, Blob) are represented by Content Hash — they never expose a version.

The Snapshot preserves enough information for an Allocation Plan to validate its dependencies later: mutable dependencies preserve the observed Object Version; immutable dependencies preserve the Content Hash.

## Snapshot Identity and Cluster Generation

Every Snapshot owns a Snapshot ID, a Creation Timestamp, and a **Cluster Generation**.

Cluster Generation (originally named "Runtime Epoch") records significant Runtime-wide events — topology changes, cluster partitions, membership reconfiguration. **It is metadata for observability, diagnostics, and topology-level events — it is never used to validate an individual Allocation Plan.**

This distinction exists because of a real granularity bug caught during design: a single global counter incremented on *any* Runtime-wide change (in a 2000-node cluster, effectively continuously) would invalidate every Allocation Plan on nearly every materialization attempt — Node-231's heartbeat has nothing to do with an Allocation Plan for 8 CPUs on Node-17. The fix: **a plan is invalidated only by changes to the objects it depends on** (see `15-allocation-model.md` and `16-scheduling-engine.md`) — validated per-dependency via Object Version / Content Hash, never via a global counter.

## Internal Consistency and Publication

Every published Snapshot must be internally consistent — if consistency cannot be guaranteed, the Snapshot is discarded and the previous valid Snapshot remains available. Publication is atomic: a Snapshot is either completely visible or not visible at all. Partially published Snapshots are forbidden.

## Freshness

Snapshots should be recent, but need not represent the very latest Runtime state — consistency is preferred over immediacy. This is compatible with the per-dependency Optimistic Concurrency model: a slightly stale Snapshot is fine, because materialization re-validates exactly what the Plan depends on, not the whole cluster.

Snapshot freshness influences planning *quality*. It never determines planning *correctness* (`15-allocation-model.md`) — that is guaranteed by dependency-based revalidation at materialization time, independent of how fresh the Snapshot used for planning was.

## Serialization and Replay

Snapshots are fully serializable, enabling replay, offline debugging, benchmarking, simulation, and scheduler comparison — different Scheduling Engines can evaluate identical Runtime observations, making scheduling decisions deterministic and reproducible. Replay never changes historical facts. Snapshots are observational, historical artifacts (see `19-state-assembler.md` / `21-runtime-storage-engine.md`'s Snapshot Store) — they are never required for Runtime recovery; after a restart, the Runtime simply observes reality again and builds a fresh Snapshot.

Replay reconstructs historical *observation*. It never reconstructs authoritative Runtime *state* — that distinction is what keeps Snapshot replay (for debugging/simulation) categorically separate from Runtime recovery (replaying an Authoritative Event Stream, `21-runtime-storage-engine.md`). The two are never mixed.

## Performance

Snapshot construction should minimize copying, allocation, serialization, and locking — observation must never become a Runtime bottleneck. In practice: once published, a Snapshot is immutable and can be shared across concurrent Scheduling Engine calls via `Arc<Snapshot>` — cloning is a refcount increment, not a copy. This already satisfies the performance goal without needing the deferred Incremental Assembly optimization (`19-state-assembler.md`).

## Observability

Every Snapshot publication records Snapshot ID, creation latency, observed Object count, Resource count, and publication status.

## Relationship with State Assembler

State Assembler owns Snapshot construction (`19-state-assembler.md`). Cluster Snapshot owns immutable observation. Scheduling owns planning. These responsibilities never overlap.

## Relationship with Allocation

Allocation Plans reference exactly the Objects observed in the Snapshot at planning time. Allocation Materialization revalidates those specific dependencies (`15-allocation-model.md`). Snapshots never participate in Allocation after planning — their role ends once a Plan is produced.

## Anti-Patterns

Avoid: planning on live Runtime state, mutable Snapshots, duplicated authentication or membership checks inside scheduling, using Capability Filters for trust decisions, partial Snapshots, using Cluster Generation to validate an individual Allocation Plan.

## Review Checklist

Before adding information to a Snapshot ask: is it required for planning? Does it belong to observation? Can it remain immutable? Can it be serialized and replayed? Does another architectural layer already own this responsibility?

## Principles

- Trust determines who may join. Membership determines who belongs. Health determines who may execute. Resources determine what can execute.
- Snapshots observe. The Scheduling Engine plans. The Runtime executes.
- A Plan is invalidated only by changes to the objects it depends on — never by a global generation counter.
- Cluster Generation is observability metadata, not a validation mechanism.
- Snapshots are immutable observations. Reality continues evolving independently.

## Motto

Observe. Plan. Validate. Materialize. Never plan on moving ground.
