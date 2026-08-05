# TibiOS Replication

Version: 1.0

## Purpose

Replication ensures that immutable Content Objects (`13-object-model.md`) remain available across the Runtime by maintaining Physical Replicas. It is not the Object Store (`23-object-store.md`) — it does not resolve references or identity. It is not the Storage Engine (`21-runtime-storage-engine.md`) — it does not own durability of authoritative facts. Replication owns exactly one question: **does an accessible copy of this Content Object exist?**

Replication never decides where a Workload executes. Replication never replicates Logical Objects — a Logical Object is a reference, not content; there is nothing physical about it to copy.

## Ownership

Replication owns its own crate, `runtime-replication`, per `00-philosophy.md`'s "every domain owns the services that speak its language": Replication speaks the language of Physical Replicas and replication policy, distinct from both Object resolution (`runtime-object`) and persistence (`runtime-storage`).

```
                 runtime-replication
                 ┌───────────────────────┐
                 │                       │
                 │      Replication      │
                 │                       │
                 └───────────┬───────────┘
                             │
                   Outbound Ports
                             │
              ┌───────────────┴───────────────┐
              ▼                               ▼
      Object Store (23)              Runtime Storage Engine (21)
```

Replication consumes the Object Store to resolve which Content Objects exist and what they depend on, and consumes the Storage Engine to read/write the actual bytes of a Physical Replica. It never bypasses the Object Store to interpret Object semantics itself. The Object Store remains the canonical resolver of Object identity. Replication only consumes its published view of Content Objects.

## Core Principles

- Replication owns the lifecycle of Physical Replicas — never Content Objects, never Logical Objects.
- Pull guarantees correctness. Push is an optional optimization policy.
- Replication guarantees content availability. Scheduling determines workload placement.
- Trust boundaries are never crossed implicitly.
- Replica availability is observational and may always be re-observed. Replication policy is authoritative because it expresses desired Runtime behavior rather than current Runtime state.

## Replication Model

Replication has exactly one fundamental mechanism: **Pull**. Any Runtime node may request a Physical Replica of a Content Object from any node that already holds one, provided Trust authorizes the exchange. This is sufficient for correctness on its own: as long as at least one accessible Physical Replica exists, any node can eventually obtain the content it needs, with no coordination, no prediction, and no advance policy required.

Everything else Replication does — proactive pre-positioning, redundancy targets, geographic distribution — is policy layered on top of Pull, never a second mechanism.

```
Content Object required
        │
        ▼
Object Store: resolve ContentHash
        │
        ▼
Physical Replica already held?
        │
   ┌────┴────┐
   ▼         ▼
  Yes        No
   │         │
   │         ▼
   │    Locate a node holding one (via Object Store)
   │         │
   │         ▼
   │    Authorized by Trust?
   │         │
   │    ┌────┴────┐
   │    ▼         ▼
   │   Yes        No → Refuse
   │    │
   │    ▼
   │   Pull Content Object
   │    │
   └────┴──────────► Physical Replica available
```

The Pull itself uses the Storage Engine to transfer and store the underlying bytes (`21-runtime-storage-engine.md`) — Replication speaks only of Content Objects; bytes remain Storage's vocabulary, the same discipline `23-object-store.md` already applies.

## Physical Replicas

A Physical Replica is what `13-object-model.md` already defines it as: one or more physical copies of a Content Object's bytes, an implementation detail managed by the Runtime. Replication does not redefine this — it owns the lifecycle of Physical Replicas: creating them (via Pull), verifying them (hash matches the Content Object's `ContentHash`), and removing them when policy or garbage collection (`13-object-model.md`, `21-runtime-storage-engine.md`) determines they are no longer required.

A Physical Replica's bytes are stored by the Storage Engine (`21-runtime-storage-engine.md`'s Content Store). Replication never stores bytes itself — it orchestrates *when* and *where* a Physical Replica is created or removed, and delegates the actual storage to the Storage Engine through an Outbound Port.

## Trust Boundaries

Replication applies, without redefining, the rule already established in `13-object-model.md`: *"Physical Replicas never cross a trust boundary automatically — replication across islands requires explicit authorization, never happens implicitly."*

Concretely: before any Pull crosses from one trust island to another, Replication queries Trust (`22-networking.md`) for authorization, exactly as Networking does before establishing a Session. Replication never makes this decision itself, and never caches a stale authorization — every cross-island Pull is authorized at the time it happens, not merely "once, in the past." Authorization is evaluated per transfer, not per replica.

Within a single trust island, no additional authorization is required beyond the Membership/Health checks any Runtime communication already assumes.

## Replication Policies

A Replication Policy decides when and where Physical Replicas should be created, retained, relocated, or removed. Pull is the fundamental mechanism through which a policy materializes additional replicas — policy never introduces a second replication mechanism.

Examples: `MinimumReplicaCount(n)`, `CapabilityAffinity(GPU)`, `GeographicDistribution(regions)`, `PopularityWeighted`.

A policy answers "should more (or fewer) copies of this Content Object exist, and where?" It never answers "where should this Workload execute?" — that question belongs exclusively to Scheduling's Locality Score Policy (`16-scheduling-engine.md`, see Relationship with Scheduling below).

**Replication places content. Scheduling places computation.**

Policies are Replication's authoritative configuration — they express desired Runtime behavior, not observed state (see Core Principles above). The MVP may ship with no active policy at all — Pull alone remains correct and complete without one, per `00-philosophy.md`'s "model larger than today's implementation."

## Replica Lifecycle

```
Requested
    │
    ▼
Pulling
    │
    ▼
Verified
    │
    ▼
Available
    │
    ├──────────────┐
    ▼              ▼
Relocating   Pending Removal
    │              │
    └──────┬───────┘
           ▼
        Removed
```

`Requested` and `Pulling` exist only while a Pull is in flight — they are transient, observational states, never persisted as facts (see Replica Availability, below). `Available` is the steady state: a verified, reachable Physical Replica. `Pending Removal` occurs through policy decision or garbage collection, never through time-based expiration — a Physical Replica does not expire the way a Lease-governed Allocation or Session does (`15-allocation-model.md`, `22-networking.md`); it is removed because policy no longer requires it.

`Relocating` is not a state a single Physical Replica passes through — there is no "the replica is in motion." Relocation is: Pull a new replica at the destination, verify it, mark it `Available`, then remove the old one. Two Physical Replicas of the same Content Object briefly coexist; availability is never interrupted.

## Replica Availability

This section deliberately does not use the word "consistency" — Content Objects are immutable and content-addressed, so there is no divergence to reconcile, no staleness to detect, and no conflict to resolve. A Physical Replica either matches its `ContentHash` or it is not a replica of that Content Object at all.

Replica Availability answers exactly three questions, all observational, all re-derivable by observing reality again:

1. **Does a Physical Replica exist?** — at least one node holds verified bytes matching the `ContentHash`.
2. **Is it reachable?** — the node holding it is currently reachable (Networking/Membership/Health, `22-networking.md`).
3. **Does policy require additional or fewer replicas?** — evaluated against the currently observed count and the active Replication Policy.

None of these require persistence. If every observation of every Physical Replica were lost, Replication would simply re-scan the cluster and rebuild the same picture — exactly the reconstructability `00-philosophy.md` describes for observational state.

## Failure & Recovery

A failed Pull is retried or abandoned — it never leaves a partially-written Physical Replica marked as available. A Physical Replica is either fully verified against its `ContentHash`, or it does not exist yet.

Recovery re-observes reality rather than replaying historical facts, because Physical Replicas are observational state, not authoritative state (`00-philosophy.md`). After a restart, Replication re-observes which Physical Replicas the local Storage Engine already holds and re-evaluates policy against the current cluster view. The only thing Replication ever recovers from durable storage is **policy** — the authoritative configuration itself (Core Principles, above), never the observed replica count.

## Relationship with Object Store

Object Store resolves *which* Content Object something is — identity, versions, references (`23-object-store.md`). Replication decides *whether enough accessible copies of it exist*. Replication never resolves identity itself; every Pull begins by asking the Object Store which `ContentHash` it needs, and ends by informing the Object Store's view of where replicas exist. Replication is a consumer of the Object Store, never a second resolver.

## Relationship with Storage

The Storage Engine answers *can these bytes be stored, durably and correctly* (`21-runtime-storage-engine.md`). Replication answers *should these bytes exist here*. Storage has no opinion on how many copies should exist anywhere — it persists whatever it is asked to persist. Replication never implements storage itself; it only decides when to ask Storage to persist or delete a Physical Replica.

Together with the Object Store, this closes a triangle where no domain speaks another's language:

```
        Object Store
     (which Content Object?)
           ▲       │
           │       ▼
   Replication ──► Storage
(should it exist here?)  (can these bytes be stored?)
```

## Relationship with Scheduling

Scheduling decides where a specific Workload executes, using the current Cluster Snapshot (`16-scheduling-engine.md`). Replication decides where Content Objects should have accessible copies, using Replication Policy. Neither depends on the other to function: Pull makes the system correct even with zero Replication Policies, and Scheduling can place a Workload on a node with no local replica — the Worker's Execution Context (`18-worker-model.md`) simply triggers a Pull for whatever dependency isn't already present.

**Replication places content. Scheduling places computation.**

This is where TibiOS's separation of knowledge and work plane becomes visible end to end: Object → Object Store → Replication is the knowledge plane; Admission → Scheduling → Allocation → Worker is the work plane. The two planes intersect exactly once during execution: the Runtime assembles an Execution Context that combines resolved dependencies (knowledge plane) with an Allocation Contract (work plane) before handing it to a Worker.

## Observability

Replication exposes: Pull latency, Pull success/failure rate, current replica count per Content Object, policy evaluation duration, cross-trust-island transfer count, and bytes transferred. Metrics describe Replication; they never drive Replication decisions directly.

## Anti-Patterns

Avoid: replicating Logical Objects, treating Physical Replica existence as authoritative state, implicit cross-trust-island transfers, a second replication mechanism alongside Pull, persisting observed replica counts, Replication deciding Workload placement, Replication storing bytes itself instead of delegating to Storage, bypassing the Object Store to discover Content Objects directly from Storage.

## Review Checklist

Before extending Replication ask: does it operate on Content Objects, never Logical Objects? Does it stay reachable through Pull alone, with policy as a pure optimization? Is replica existence treated as observational, never authoritative? Does every cross-island transfer get authorized at transfer time? Does it avoid deciding Workload placement? Does it preserve the separation between the knowledge plane and the work plane?

## Principles

- Replication owns the lifecycle of Physical Replicas — never Content Objects, never Logical Objects.
- Pull guarantees correctness. Push is an optional optimization policy.
- Replication guarantees content availability. Scheduling determines workload placement.
- Replication places content. Scheduling places computation.
- Trust boundaries are never crossed implicitly; authorization is evaluated per transfer, not per replica.
- Replica availability is observational and may always be re-observed. Replication policy is authoritative because it expresses desired Runtime behavior, not current Runtime state.
- Replication continuously converges toward policy; it never reconstructs history.

## Motto

Resolve identity elsewhere. Store bytes elsewhere. Decide only whether a copy should exist here.
