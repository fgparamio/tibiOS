# TibiOS State Assembler

Version: 1.0

## Purpose

The State Assembler observes mutable Runtime state and constructs immutable Cluster Snapshots (`17-cluster-snapshot.md`) — it does not transform state, it transforms *observation of* state. The Runtime owns reality; the Scheduling Engine owns planning; the State Assembler bridges both.

This document follows the principles in `00-philosophy.md` and `02-project-structure.md`.

## Core Principle

The Runtime continuously changes. Planning requires deterministic observations. The State Assembler converts mutable Runtime state into immutable planning data.

## Responsibilities

Observing Runtime state, collecting scheduling-relevant information, normalizing heterogeneous Runtime data into a unified scheduling model, constructing immutable Snapshots, publishing consistent Snapshots.

The State Assembler never executes Workloads, never performs scheduling, and never modifies Runtime state — it is strictly read-only; observation must never interfere with execution. The State Assembler owns neither the observed state nor the resulting scheduling decisions.

```
Runtime → observed by → State Assembler → produces → Cluster Snapshot → consumed by → Scheduling Engine
```

## Snapshot Construction Pipeline

Enriching a Node through progressively lower-volatility to higher-volatility layers (`00-philosophy.md`'s Volatility principle), each stage owned by exactly one domain, each answering exactly one question:

```
Networking / Trust
        │
        ▼
    Membership
        │
        ▼
      Health
        │
        ▼
    Resources
        │
        ▼
 Cluster Snapshot
```

The mechanics of each stage (Noise handshake, certificates, ACLs, heartbeats) belong to their owning domains (`22-networking.md`) — this pipeline shows only the domain-level sequence the State Assembler observes, not their internals.

Each stage enriches the node; it never re-derives what an earlier, lower-volatility stage already established — Trust is never recomputed because a heartbeat arrived, and Membership never requires repeating cryptographic authentication. On revocation, propagation is forward: a `TrustRevoked` fact (see `22-networking.md`) invalidates the current Snapshot, triggering a fresh one built without that node — reusing the same invalidation mechanism already used for Optimistic Concurrency Control, not a special-cased "backward" flow.

The internal pipeline is: Observation → Normalization → Consistency Validation → Snapshot Assembly → Publication. Normalization transforms heterogeneous internal representations from different Runtime components into a unified scheduling model — scheduling never depends on Runtime implementation details.

## Internal Consistency and Publication

Every published Snapshot must be internally consistent — if consistency cannot be guaranteed, the Snapshot is discarded and the previous valid Snapshot remains available. Publishing is atomic: fully visible, or not visible at all.

## Failure

Snapshot construction may fail; failures are observable, and never expose partially assembled Snapshots. The Runtime continues operating using the latest valid Snapshot — Runtime execution continues independently: a failed Snapshot construction affects the ability to plan *new* work, never the execution of work already underway.

## Performance

Snapshot construction should minimize copying, allocations, serialization, and locking — observation must never become a Runtime bottleneck. See `17-cluster-snapshot.md` for the `Arc<Snapshot>`-based sharing that satisfies this without needing incremental assembly yet.

## Incremental Assembly

Future Runtime versions may support incremental Snapshot construction; the conceptual model remains unchanged — consistent with `00-philosophy.md`'s "model larger than implementation."

## Observability

Every Snapshot publication records Snapshot ID, creation latency, observed Object count, Resource count, and publication status.

## Security

The State Assembler never exposes secrets, credentials, private keys, or authentication material — only scheduling-relevant observations become visible. Trust decisions remain owned by Trust; the State Assembler only observes their result.

## Relationship with Cluster Snapshot

State Assembler owns Snapshot construction. Cluster Snapshot owns immutable observation (`17-cluster-snapshot.md`). These responsibilities are intentionally separate.

## Relationship with Scheduling

Scheduling consumes published Snapshots. Scheduling never observes Runtime state directly. The State Assembler is the only bridge between Runtime reality and scheduling.

## Anti-Patterns

Avoid: mutable Snapshots, partial publications, Runtime mutation, duplicated ownership, exposing Runtime internals, scheduling inside the State Assembler.

## Review Checklist

Before adding information to a Snapshot ask: is it required for planning? Does it belong to observation? Can it remain immutable? Does another component already own it? Can it be serialized?

## Principles

- The Runtime owns reality. The State Assembler owns observation. The Scheduling Engine owns planning.
- Reality is mutable. Observations are immutable.
- Each enrichment stage answers exactly one question, at its own natural volatility — never re-deriving a lower-volatility fact.
- Revocation propagates forward via the same Snapshot invalidation mechanism used for Optimistic Concurrency, not a special backward flow.

## Motto

Observe once. Normalize consistently. Publish immutably. Plan deterministically.
