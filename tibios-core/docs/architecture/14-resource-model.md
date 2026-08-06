# TibiOS Resource Model

Version: 2.0

## Purpose

The Resource Model defines how the Runtime represents assignable capacity.

A Resource is not hardware. A Resource is the language the Scheduler uses to describe capacity — a CPU Pool, a GPU Device, a Memory Pool, a Storage Pool, Network Bandwidth. Whether that capacity is physical (a GPU) or logical (an Inference Slot, an Embedding Cache, an LLM Context Window, a Tensor Cache) is irrelevant to the model — a Resource is anything the Runtime can check for availability, allocate against, and release.

This document builds directly on `13-object-model.md` and follows the ownership and identity principles defined in `00-philosophy.md` and `02-project-structure.md`. It does not redefine them.

## Ownership

`Resource` belongs to `runtime-scheduler` — it has no autonomous lifecycle of its own (unlike `Object`, which owns its own crate). Resource is the language of the scheduling pipeline: Candidate Discovery, Filter, Score, and Allocation all speak it. There is no `runtime-resource` crate.

Internally, `runtime-scheduler` organizes this responsibility into modules: `resource/`, `candidate/`, `filter/`, `score/` — this internal organization is invisible to other crates (`02-project-structure.md`).

## Resource as a Logical Object

A Resource is a specialized Logical Object (`13-object-model.md`): identity is `ObjectId` (ULID) + `ObjectVersion`. This document does not redefine identity — it specializes it. Resource specializes the *behavior* of a Logical Object; it does not redefine identity, ownership, or lifecycle.

## Resource Identity

Resources inherit their identity from the Object Model:

```
ObjectId
    │
    ▼
ObjectVersion
```

Capacity, availability, and capability never participate in Resource identity — they describe the current *state* of the Resource, not what the Resource *is*. If `Available` changes, the Resource's identity does not change; only its observed state does.

## Granularity

A Resource is neither a single physical unit (one core, one byte) nor the entire machine. It is a hierarchical pool:

```
Cluster
    │
    ├── Node
    │     │
    │     ├── CPU Resource
    │     │      ├── Core Group
    │     │      ├── NUMA Node
    │     │      └── SMT Threads
    │     │
    │     ├── GPU Resource
    │     │      ├── VRAM
    │     │      ├── Compute Units
    │     │      └── MIG Partitions (if present)
    │     │
    │     ├── Memory Resource
    │     ├── Network Resource
    │     └── Storage Resource
```

The Scheduler asks for "4 CPUs, 16 GB RAM, 1 GPU with 12 GB VRAM" — it does not ask for cores 3, 4, 5, and 6. Which specific units satisfy that request is decided by the Runtime, not expressed by the Scheduler.

**Granularity belongs to the provider of the Resource.** A CPU Resource is modeled as a pool with capacity, not as an Object per core — modeling per-core Objects would be identity explosion with no benefit, since hardware is allocated fractionally against a pool, not against individually-identified cores.

## Non-Physical Resources

A Resource does not have to be physical. Examples: Inference Slot (how many concurrent requests a serving instance accepts), Embedding Cache (capacity of a cache pool), LLM Context Window (how much of a model's attention window is in use), Tensor Cache. All of these satisfy the same behavioral contract — check availability, allocate, release — as CPU or GPU. That shared behavior, not a shared physical nature, is what makes them Resources.

## Capability, Not Just Capacity

Because Red Tibi nodes are far more heterogeneous than a typical single-owner datacenter cluster, a Resource carries typed capability metadata alongside its scalar capacity — VRAM size *and* compute architecture (CUDA, Metal, ROCm), not merely "one GPU available." Modeling GPU capacity as a bare count (the way Ray does) would let a Filter Policy match a workload needing 24GB CUDA against an 8GB Metal device and fail at execution time rather than at scheduling time.

Capability participates in Filter. Capacity participates in Allocation — they are evaluated at different stages of the pipeline (`16-scheduling-engine.md`).

## Observational State

`Capacity`, `Allocated`, and `Available` are observational state, per `00-philosophy.md`'s Authoritative/Observational distinction — they can be reconstructed by observing reality again (re-querying the OS/driver for current usage), so they are never persisted through an Authoritative Event Stream. After a restart, the Runtime simply re-observes current capacity; it does not replay a log to reconstruct it.

This is distinct from the Allocation Contract that binds a Workload to a Resource, which *is* authoritative (see `15-allocation-model.md`).

## Relationship with State Assembler

The Resource Model does not build Cluster Snapshots. It publishes observed Resource state; State Assembler observes it, together with Trust, Membership, and Health, to construct the Cluster Snapshot (`17-cluster-snapshot.md`, `19-state-assembler.md`).

## Relationship with Scheduling

Scheduling consumes Resources during Candidate Discovery, Filter, and Score (`16-scheduling-engine.md`). Scheduling evaluates Resources; it never becomes their authoritative owner — it reads a Cluster Snapshot's observation of them, per `00-philosophy.md`'s Ownership principle.

## Relationship with Allocation

Allocation references Resources; it never modifies them directly. Allocation consumes Resource capacity through an Allocation Contract — it never changes Resource identity. An `AllocationContract` binds to a specific Resource (see `15-allocation-model.md`'s Resource Binding), but the Resource's own capacity accounting is owned exclusively by the Node hosting it — single-writer-per-Resource, consistent with `00-philosophy.md`'s Ownership principle. A remote Scheduler never creates an Allocation directly against a Resource it does not own; it only requests one.

## Relationship with Health

Resource availability and Health answer different questions and must never be conflated. A node can have ample Resources available and still be `Draining` or `Unhealthy` — Health measures operational fitness (load, degradation, internal errors), not resource capacity. See `17-cluster-snapshot.md` and `22-networking.md` for the full set of non-overlapping questions each Runtime domain answers (Networking: reachability, Membership: cluster participation, Health: operational fitness) — Resources add a fourth, independent axis: *what capacity does this node currently offer?*

## Anti-Patterns

Avoid: modeling a Resource per physical unit (per-core Objects), modeling scalar-only capacity for heterogeneous hardware, persisting Resource capacity as an authoritative fact, letting Scheduling or Allocation mutate a Resource directly, conflating Resource availability with Health.

## Review Checklist

Before introducing a new Resource type ask:

- Does it behave like a pool — checkable, allocatable, releasable?
- Is its granularity chosen by its provider, not imposed by a consumer?
- Does it carry the capability metadata a heterogeneous cluster requires, or only a scalar count?
- Is its live state observational, never authoritative?

## Principles

- A Resource is a language for describing assignable capacity, not a description of hardware.
- Resource belongs to `runtime-scheduler`; there is no independent Resource domain.
- Granularity is chosen by the provider, never imposed by the consumer.
- Resource capacity is observational state — reconstructed by observation, never persisted as fact.
- Resource availability and Health are independent axes; neither implies the other.
- Identity is stable. Capacity is observed. Allocation is temporary.

## Motto

A Resource describes what could be used. An Allocation describes what is being used.
