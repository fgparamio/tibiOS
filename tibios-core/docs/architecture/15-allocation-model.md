# TibiOS Allocation Model

Version: 2.0

## Purpose

The Allocation Model defines how Resources are temporarily assigned to Workloads.

Resources describe capacity (`14-resource-model.md`). Allocations describe consumption. Scheduling creates Allocation Plans; the Runtime materializes them into Allocations. When execution finishes, Allocations disappear — Resources remain.

This document follows the principles defined in `00-philosophy.md` and `02-project-structure.md`. It does not redefine Ownership, Lease, or the Authoritative/Observational distinction — it applies them.

## Ownership

`Allocation` owns its own crate (`runtime-allocation`), separate from `runtime-scheduler`. This is a direct consequence of the Composition Root rule in `02-project-structure.md`: Allocation Materialization (Validate, Reserve, Commit, Rollback) is domain logic, and domain logic cannot live in the thin Composition Root — it needs a dedicated crate.

**Schedulers plan. Allocators commit.** The Scheduler answers "where should this execute?" and produces an `AllocationPlan` (a Data Contract it owns, per `02-project-structure.md`'s producer-owns-data-contracts rule). Allocation answers "can this plan become real resources?" and owns the resulting `AllocationContract`.

```
Admission → Scheduler → Allocation → Worker
```

## Core Principles

Resources are permanent. Allocations are temporary. Workloads never own Resources — they lease Allocations. The Runtime owns the lifecycle of every Allocation.

## Design Philosophy: Model Larger Than Implementation

Per `00-philosophy.md`, the Allocation Model is intentionally larger than its first implementation.

**MVP (Phase 1)**: strict allocation. No overcommit, no preemption, no allocation migration, no elastic allocations. Capacity must exist before Allocation; every Allocation represents real, guaranteed capacity; allocation failures are deterministic. The objective is simplicity, predictability, correctness.

**Phase 2**: elastic allocations, allocation migration, checkpoint-aware migration, reservation policies, priority-aware scheduling, allocation renewal. These extend the implementation — they do not change the model.

**Phase 3**: controlled overcommit, controlled preemption, predictive allocation, dynamic resource borrowing, energy/cost/AI-aware scheduling. These are scheduling *policies*, not part of the Allocation Model itself.

The boundary that keeps this honest: the "larger" part of the model must cost nothing until exercised — it lives in the type system (an `AllocationPolicy` enum with a `Strict` variant implemented today and `Overcommit(ratio)`/`Preemptible` variants that exist as types but have no code behind them yet), never in unused infrastructure built ahead of a caller.

## Allocation Identity

Every Allocation owns an `AllocationId` (ULID — it has mutable Runtime State, so per `13-object-model.md` it cannot be content-addressed), a `ResourceId`, a `WorkloadId`, and an owner. Identity never changes.

## Three Kinds of Information

An earlier draft of this model put `Policy` directly on `Allocation`. That conflated three things with different owners and different lifetimes:

### 1. Scheduling Metadata (ephemeral, owned by the Scheduler)

Exists only while Placement is being computed: `Priority`, `Cost`, `Affinity`, `Locality Score`, `Energy Score`, `Rack Preference`, `AI Placement Score`. Lives in the `AllocationPlan`. Once an Allocation is created, this disappears — it never reaches the Runtime.

### 2. Allocation Contract (persistent, immutable once created, owned by the Runtime, authoritative)

Defines how the Allocation must behave during its entire life — a small contract the Runtime commits to honoring: `Exclusive`/`Shared`, `Preemptible`, `Renewable`, `MigrationAllowed`, `CheckpointRequired`, `MaxDuration`. This is not scheduling policy; it is a binding commitment between Scheduler and Runtime — an Allocation Contract is an authoritative fact (`21-runtime-storage-engine.md`), not a derived or observational value. "The Scheduler says: I want this Allocation. The Runtime replies: from now on I will honor this contract."

### 3. Runtime State (mutable, owned by the Runtime)

What is happening to the Allocation right now: `Created`, `Reserved`, `Assigned`, `Active`, `Renewing`, `Expiring`, `Released`. This is the lifecycle field that, in an earlier draft, incorrectly lived under "Identity" (which is supposed to never change) — it belongs in its own mutable bucket.

```
Allocation
    │
    ├── Identity        (AllocationId, ResourceId, WorkloadId, Owner — immutable)
    ├── Resource Binding
    ├── Lease
    ├── Contract         (immutable once created)
    └── Runtime State    (mutable)
```

`Priority` and the rest of Scheduling Metadata are not fields of `Allocation` at all — they live only in the `AllocationPlan`.

## Allocation Lifecycle

```
Created
    │
    ▼
Reserved
    │
    ▼
Assigned
    │
    ▼
Active
    │
    ├───────────────┐
    ▼               ▼
Released         Expired
    │               │
    └──────┬────────┘
           ▼
       Destroyed
```

Resources never follow this lifecycle — only Allocations do.

## Lease

Every Allocation is leased, using the Lease primitive defined in Runtime Primitives (`02-project-structure.md`) — the same generalized concept used for Networking Sessions (`22-networking.md`). Leases begin, may be renewed, and eventually expire. Lease expiration releases the Allocation and returns capacity to the owning Resource — this release is itself an authoritative fact, durably recorded, never inferred solely from an in-memory state mutation (the equivalent rule for Quota release lives in `20-admission-control.md`, where it belongs).

## Capacity

Allocations consume Resource capacity. Capacity is always computed by the Runtime — applications never calculate it.

```
CPU Resource
Capacity:   32
Allocated:  18
Available:  14
```

Capacity remains observational state owned by the Resource (`14-resource-model.md`). Allocation consumes capacity; it never owns capacity.

## Scheduler Invariant

The Scheduler must never create an Allocation that exceeds currently available capacity — but the Scheduler never creates Allocations at all (see Ownership above). The Runtime enforces this invariant at materialization time.

This invariant is preserved without distributed consensus, because of a stricter rule: **the Node hosting a Resource is the sole authority that creates Allocations against it.** A remote Scheduler never decides unilaterally — it only requests, and the owning Node's Runtime accepts or rejects atomically and locally. Single-writer-per-Resource, consistent with `00-philosophy.md`'s Ownership principle — no Raft, no distributed consensus needed for capacity accounting.

## Allocation Plan

The Scheduler never touches Resources directly — it produces an `AllocationPlan`, a pure data artifact representing intent, not yet materialized into any Allocation. This makes the Scheduling Engine a pure function (`Cluster Snapshot + Workload Requirements → AllocationPlan`), trivially property-testable without any real Resource state (see `16-scheduling-engine.md`).

The Runtime (`Allocation Materializer`) validates the Plan, reserves the Resource, creates the Allocation, and returns its ID — and may reject the Plan.

### Dependency-Based Validation, Not a Global Counter

An `AllocationPlan` declares its explicit dependencies (the specific Resources and Objects it references), each carrying the Object Version or Content Hash observed at planning time (see `13-object-model.md`'s Dependency Validation and `17-cluster-snapshot.md`). Materialization revalidates only those specific dependencies — never a global "did anything in the cluster change?" check. **A plan is invalidated only by changes to the objects it depends on.**

## Allocation Commit Transaction

Allocation acceptance requires one durable logical transaction, performed by the Allocation Materializer, in the correct order:

```
Validate
    ↓
Reserve Resource
    ↓
Append Allocation Record
    ↓
Record Persisted
    ↓
Update Runtime State Projection
    ↓
Return Allocation Decision
```

Validation is performed against the `AllocationPlan`'s declared dependencies (see Dependency-Based Validation below and `16-scheduling-engine.md`) before any Resource reservation occurs.

The record must become durable *before* updating in-memory state or acknowledging success — reversing this order reintroduces exactly the durability bug this ordering exists to prevent. `20-admission-control.md` works through the same transaction shape in full for Quota — Allocation and Admission are two independent instances of the identical pattern, not one borrowing from the other.

## Recovery

Allocation Runtime State is a rebuildable projection of the Allocation Lifecycle Log (an Authoritative Event Stream, `21-runtime-storage-engine.md`), not separately persisted "metadata." After a restart, the Runtime replays the log (optionally from the last checkpoint) to reconstruct current Allocation state — it never trusts in-memory state as the source of truth.

The replay reconstructs Runtime State. It never reconstructs Resource capacity, which is re-observed (`14-resource-model.md`) rather than replayed — capacity is observational, Allocation Runtime State is authoritative, and recovery treats each according to its nature (`00-philosophy.md`).

## Relationship with Worker

Workers consume Allocation Contracts (`18-worker-model.md`). Workers never materialize Allocations and never modify Allocation state. Execution begins only after an Allocation has been successfully committed by the Allocation Materializer.

## Known MVP Limitation: Starvation

Under sustained contention, a large resource request can be starved indefinitely by a stream of smaller requests re-winning the placement race each time. The MVP intentionally favors simplicity over fairness. Preemption, reservation windows, workload aging, and fairness policies are Phase 2/3 concerns that do not require changing this model.

## Anti-Patterns

Avoid: permanent reservations, hidden overcommit, hidden preemption, hidden migration, unlimited leases, machine-specific allocations, Resource ownership by Workloads, implicit capacity borrowing, treating in-memory Allocation state as authoritative.

## Review Checklist

Before introducing a new Allocation type ask: does it represent temporary consumption? Can it expire? Can it be renewed? Can it migrate (if the Contract allows)? Can it be observed? Can it be audited? Does it preserve the single-writer-per-Resource invariant?

## Principles

- Resources describe possibility. Allocations describe commitment. Policies describe behavior.
- Scheduling Metadata is ephemeral and Scheduler-owned. Allocation Contract is persistent and Runtime-owned. Runtime State is mutable and Runtime-owned.
- A plan is invalidated only by changes to the objects it depends on — never by a global counter.
- The Node owning a Resource is the sole authority that creates Allocations against it.
- The model supports overcommit, preemption, and migration; the MVP does not implement them.
- Allocation Contracts are authoritative facts. Runtime State is a rebuildable projection.

## Motto

Allocate. Execute. Release. The model is permanent. Implementations evolve.
