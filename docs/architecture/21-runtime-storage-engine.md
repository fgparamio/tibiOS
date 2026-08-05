# TibiOS Runtime Storage Engine

Version: 1.0

## Purpose

The Runtime Storage Engine provides durable persistence for the Runtime. It is not a database, and it is not the Object Store — it is the infrastructure-neutral persistence layer that domain-specific services (Object Store, Admission Log, Snapshot Store, ...) are built on top of. It stores authoritative facts; it never owns Runtime behavior. The Runtime interprets persisted facts — the Storage Engine preserves them.

This document follows the principles in `00-philosophy.md` and `02-project-structure.md`.

## Core Principles

Persist facts. Reobserve observations. Storage owns durability; the Runtime owns meaning. Persistent state is authoritative; memory is an optimization.

## Responsibilities

Durable persistence, atomic commits, ordered append, recovery, replay, checkpoint persistence, content persistence.

The Storage Engine never performs scheduling, executes Workloads, evaluates policies, manages Resources, or interprets business semantics.

## Storage Domains

Four domains, three mechanisms — not five domains, as an earlier draft modeled it (see "Why Metadata Store Disappeared" below):

```
Runtime Storage Engine
├── Content Store                   (immutable, hash-addressed, no replay needed)
├── Authoritative Event Streams     (mutable: Events → Projection)
│      ├── Admission
│      ├── Trust
│      ├── Allocation
│      ├── Object Lifecycle
│      ├── Checkpoint Lifecycle (if authoritative)
│      └── (any other mutable Runtime aggregate)
├── Snapshot Store                  (observational, for replay/simulation/audit, never for recovery)
└── Report Store                    (immutable final artifacts, no evolution, no projection)
```

### Content Store

Immutable content addressed by Content Hash (`13-object-model.md`): Model Artifacts, Dataset Chunks, Binaries, Blobs. Content never changes; duplicate content transparently deduplicates for free (content-addressing).

### Authoritative Event Streams — Not a Generic "Log Store"

Each mutable Runtime aggregate owns its own ordered event stream, not one giant log: Admission Log, Trust Log, Allocation Log, Object Lifecycle Log, Checkpoint Lifecycle Log. This is the DDD Aggregate pattern combined with per-aggregate event sourcing (the same precedent as EventStoreDB or Kafka partitioned by aggregate ID) — each stream is ordered independently; there is no ordering relationship between different streams. **Every authoritative fact belongs to exactly one consistency domain** (`00-philosophy.md`) — this is exactly why no global log exists: it would recreate the same bottleneck a single global quota counter would (see `20-admission-control.md`).

**Trust Log** belongs here as an example stream: Node Granted, Node Revoked, Certificate Rotated, Trust Policy Updated. Trust is the single most security-critical example of authoritative state in the Runtime — losing it cannot be recovered by "observing the network again," unlike Membership or Health, which are freshly re-derivable.

### Why Metadata Store Disappeared

An earlier draft had a separate "Metadata Store" for Logical Object metadata. It was removed as redundant: per the Append Semantics rule below, "logical state evolves through new facts" — a Logical Object's current metadata (`13-object-model.md`) is simply the rebuildable projection of its own Object Lifecycle Log, exactly the same mechanism as Admission Log → Quota Projection or Trust Log → Trusted Node Set. There is no separate mechanism to maintain.

### Snapshot Store

Persists historical Cluster Snapshots (`17-cluster-snapshot.md`) for replay, simulation, benchmarking, and debugging. Snapshots are historical artifacts — **never required for Runtime recovery**; after a restart the Runtime simply observes reality again.

### Report Store

Stores immutable Execution Reports (`18-worker-model.md`) — for history, auditing, and analytics. Reports never transport execution output (that traveled through the Execution Channel while live) and are never versioned or re-evaluated — a finished report is a terminal fact, like a signed document, not a stream with a projection.

## Authoritative Facts vs Observational State

Authoritative facts cannot be reconstructed by observing the Runtime again — Admission Records, Trust events, Allocation metadata, Logical Object metadata, Execution Reports — and must be durable. Observational state (Health, Heartbeats, CPU/GPU/Memory utilization, network latency) can be reconstructed and should never require authoritative persistence.

**Persist facts. Reobserve observations.**

## Append Semantics and Ordering

Facts are appended; authoritative records are never updated in place — logical state evolves through new facts, never in-place mutation. Ordering is guaranteed only within a consistency domain (e.g. the Admission Log for one tenant, the lifecycle log for one Allocation, the lifecycle log for one Object) — global ordering across domains is neither required nor guaranteed.

## Atomic Commit and Durability

A committed fact is durable, recoverable, and replayable — partial commits are forbidden. Acknowledgement of persistence occurs only after durability is guaranteed; visibility without durability is forbidden. This ordering discipline (persist, then acknowledge/apply) is what prevents the durability-vs-concurrency confusion worked out in detail in `20-admission-control.md`.

## Recovery, Rebuildable Projections, and Checkpoints

Recovery reconstructs Runtime state from authoritative facts: loading checkpoints, replaying newer facts, rebuilding projections.

```
Authoritative Event Stream
        │
        ▼
    Replay
        │
        ▼
  Runtime Memory (Projection)
```

Runtime memory is rebuildable — the Storage Engine stores facts; the Runtime rebuilds projections from them. Checkpoints accelerate recovery; they are optimization artifacts and never replace the authoritative log. Storage reconstructs nothing. The Runtime rebuilds every projection.

## Replay

Replay enables Runtime recovery, simulation, testing, debugging, and benchmarking. Replay never changes historical facts. Replay reconstructs projections. It never reinterprets facts.

## Versioning and Serialization

Mutable Objects expose Object Versions; immutable Objects expose Content Hashes (`13-object-model.md`) — the Storage Engine preserves both identity models. Every persisted object must be serializable; serialization formats are implementation details, independent of the architectural model.

## Conceptual Model vs Implementation

Not every mutable aggregate must be persisted as a literal, explicit event-sourced stream. Conceptually: all mutable state evolves through authoritative facts and can be represented as a rebuildable projection. In implementation: some aggregates may use an explicit event stream; others may use an equivalent internal mechanism, as long as it preserves the same guarantees — order within its consistency domain, durability, reconstruction, auditability. This avoids coupling TibiOS to one literal Event Sourcing implementation while remaining compatible with the DDD + Aggregate Streams model described above.

## Garbage Collection

Applies only to unreferenced content. Authoritative facts are never removed while required for correctness. Retention policies belong to Runtime configuration.

## Observability

The Storage Engine exposes commit latency, replay latency, checkpoint duration, storage utilization, and recovery duration.

## Security

The Storage Engine protects integrity, durability, and confidentiality. Authorization decisions belong to the Runtime; the Storage Engine enforces persistence policy. Trust owns authorization. Storage enforces durability.

## Anti-Patterns

Avoid: treating caches as authoritative, mutable facts, global ordering across consistency domains, in-place mutation of logs, persisting observational state as authoritative, embedding Runtime logic inside storage, a single global event log.

## Review Checklist

Before persisting new state ask: is it a fact or an observation? Can it be reconstructed? Does it require durability? Which consistency domain owns it? Is append sufficient? Is a checkpoint merely an optimization?

## Principles

- The Runtime owns behavior. Storage owns durability.
- Facts are permanent. Observations are ephemeral. Memory is rebuildable.
- Persist facts. Reobserve observations.
- Every authoritative fact belongs to exactly one consistency domain — no global log.
- Trust is the most critical example of authoritative state; it is never merely observational.

## Motto

Persist facts. Recover deterministically. Treat memory as a cache. Never confuse storage with behavior.
