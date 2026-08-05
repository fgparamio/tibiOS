# TibiOS Object Model

Version: 2.0

## Purpose

The Object Model defines every entity managed by TibiOS.

Everything inside TibiOS is represented as an Object. Objects are the universal abstraction shared by Runtime, Scheduler, Storage, Networking, AI Runtime, and Applications.

The Runtime manipulates Objects — not implementation-specific structures.

This document follows the ownership and identity principles defined in `00-philosophy.md` and `02-project-structure.md`. It does not redefine them.

## Core Principle

Everything is an Object.

Examples include Workloads, Messages, Files, Models, Tensors, Agents, Services, Pipelines, Checkpoints, Datasets, Configuration, Secrets, Metrics.

The Runtime understands one abstraction: Objects.

`Object` owns its own crate (`runtime-object`, per `02-project-structure.md`) precisely because the Object Model exists independently of how it is persisted — the same reasoning as the Repository pattern. `runtime-storage` implements the persistence adapters; it never owns the model.

## Three Kinds of Object

Not every Object has the same nature. TibiOS distinguishes three kinds, corresponding directly to the Authoritative/Observational distinction in `00-philosophy.md` and the identity rules in `02-project-structure.md`.

### Logical Object (mutable, versioned)

A Logical Object is a mutable, named reference. Its identity is a `ObjectId` (ULID, per Runtime Primitives) plus an `ObjectVersion`.

Examples: `Node`, `Resource`, `Model Reference`, `Dataset Reference`, `Configuration`, `Queue`, `Allocation`.

A Logical Object does not itself hold content — it points to a Content Object.

Example: `Model Reference` (ULID, Version = 18) → `sha256:AF2398...`. A rollout creates `Model Reference` Version = 19 pointing to a new hash; the old artifact is untouched.

### Content Object (immutable, content-addressed)

A Content Object is immutable content addressed by a `ContentHash` (per Runtime Primitives). It never changes once created.

Examples: `Model Artifact`, `Dataset Chunk`, `Binary Artifact`, `Blob`, `Checkpoint Block`.

Content Objects never expose a version — there is nothing to version. A new revision is a new Content Object with a new hash, linked from the Object Graph.

### Physical Replica

A Physical Replica is an implementation detail managed by the Runtime — one or more physical copies of a Content Object's bytes.

```
Logical Object (mutable, ULID + Version)
        │
        ▼
Content Object (immutable, Content Hash)
        │
        ▼
Physical Replica, Physical Replica, ...
```

Precedent: this is the same three-tier separation used by Git (tag/commit), container registries (image tag/digest), and IPNS/IPFS (mutable name/immutable content).

Physical Replicas never cross a trust boundary automatically — replication across islands requires explicit authorization, never happens implicitly (see `08-security.md` / trust boundaries in `22-networking.md`).

## Object Identity

Every Object owns an identity appropriate to its kind. Logical Objects are identified by `ObjectId`; Content Objects are identified by `ContentHash`. Every Object also owns a Type, Owner, Metadata, Security Context, Lifecycle, Placement, and State.

Identity never changes. Metadata and State may evolve; identity remains stable. The identity scheme itself (ULID vs Content Hash) is defined by Runtime Primitives, not by this document.

## Object Lifecycle

```
Created
    │
    ▼
Validated
    │
    ▼
Registered
    │
    ▼
Available
    │
    ▼
Referenced
    │
    ▼
Updated (optional, Logical Objects only)
    │
    ▼
Archived
    │
    ▼
Deleted
```

Deletion should be explicit. A Logical Object's "update" produces a new version pointing to a (possibly new) Content Object — it never mutates a Content Object in place.

## Object Types

The Runtime recognizes object categories: Workload, Message, Actor, Service, Dataset, Tensor, Checkpoint, Configuration, Artifact, Model.

Future object types may be added without modifying existing ones.

## References

Objects reference other Objects through IDs — never through memory addresses. Object references remain valid across machines.

## Ownership

Every Object has exactly one logical owner, per the Ownership principle in `00-philosophy.md`. Ownership determines lifecycle, permissions, replication, and recovery.

## Object State

Objects expose state. State transitions are explicit. Hidden transitions are forbidden.

## Metadata

Metadata describes an Object. Metadata does not define behavior.

Examples: labels, priority, region, compression, replication policy.

## Versioning

Every Logical Object is versioned (ULID + `ObjectVersion`, per Runtime Primitives). Versioning enables compatibility, replication, migration, and rollback.

Content Objects are never versioned, because their content hash already uniquely identifies both identity and version — see "Three Kinds of Object" above.

## Serialization

Objects are transportable. Serialization is implementation-independent — see the structural-contract-vs-protocol distinction for Runtime Primitives in `02-project-structure.md`. Applications should not depend on serialization format.

## Mobility

Objects may move. Applications should not care where an Object is stored. The Runtime decides placement. Identity never changes during movement.

## Locality

Objects should remain close to computation whenever practical. Moving Objects has cost; moving computation is often cheaper (per `00-philosophy.md`'s locality principle).

## Replication

Replication is policy, not object identity. Replicas represent the same logical Content Object.

Replication creates Physical Replicas. It never creates new Content Objects.

Replication never crosses a trust boundary implicitly — see "Physical Replica" above.

## Caching

Caches never own Objects. Caches hold temporary copies; ownership remains unchanged.

> This is what makes a Worker "stateless" in the sense required by `18-worker-model.md` despite holding a multi-gigabyte model resident in memory: the loaded model is a cache of the canonical Model Object (owned by `runtime-object` / persisted via `runtime-storage`), not something the Worker owns. The cache may legitimately survive across multiple Execution Contexts handled by the same Worker; it is never shared with a different Worker.

## Object Graph

Objects may reference other Objects. References form a graph.

Logical Objects form the mutable graph of Runtime knowledge. Content Objects form an immutable dependency graph.

Because Content Objects are content-addressed, a cycle among them is structurally impossible — a hash cannot depend on itself. Cycles are only a theoretical concern for Logical Object references, and should be avoided unless explicitly required.

## Persistence

Persistence is independent of execution. Execution consumes Objects. Storage preserves Objects.

Per `00-philosophy.md`'s Authoritative/Observational distinction: Logical Object metadata and Content Objects are authoritative facts (persisted, see `21-runtime-storage-engine.md`'s Authoritative Event Streams / Content Store). A Logical Object's current state is a rebuildable projection of its Object Lifecycle Log — not a separately-persisted "metadata store" (see `21-runtime-storage-engine.md`).

## Security

Every Object owns identity, permissions, trust level, and audit information. Security travels with the Object.

## Observability

Every Object exposes creation time, owner, version, metrics, lifecycle, and trace identifiers. Nothing becomes invisible after creation.

## Garbage Collection

Objects become eligible for cleanup through policy. Deletion is never implicit. References determine reachability. Retention rules are configurable.

## AI Objects

AI workloads introduce additional Objects: Model, Tokenizer, Tensor, Embedding, Inference Result, Prompt, Conversation Context.

The Runtime treats them exactly like every other Object — Model Artifact is a Content Object (hash-addressed, immutable); Model Reference is a Logical Object (ULID + version) pointing to it, consistent with the dual-path inference design (`local-infer` and tibios-ray both consume Model Artifacts through the same Object Model).

## Distributed Systems

Objects are location independent. Nodes host Objects; nodes do not own the global namespace. The Runtime maintains logical identity.

## Public API

Applications manipulate Object references. Applications should not manipulate internal storage representations.

## Dependency Validation (Allocation Plans)

When an Allocation Plan (see `16-scheduling-engine.md`) references Objects as dependencies, materialization validates each according to its kind — not with a single generic mechanism:

- **Logical Object dependency** → Version Validation: is the referenced `ObjectId` still at the observed `ObjectVersion`?
- **Content Object dependency** → Existence Validation: does the referenced `ContentHash` still exist and remain accessible? There is no version to check.

This is why Object identity is dual-schemed in the first place — see Runtime Primitives in `02-project-structure.md`.

## Anti-Patterns

Avoid: memory addresses as references, machine-local identifiers, implicit ownership, hidden replication, implicit serialization, runtime-specific object layouts, versioning a Content Object, treating a Logical Object's cache as its source of truth.

## Review Checklist

Before introducing a new Object ask:

- Does it require identity? Logical or Content?
- Does it require ownership?
- Can it move?
- Can it be versioned, or is it content-addressed?
- Can it be replicated? Across trust boundaries, or only within one?
- Can it be observed?
- Can it survive node failure?

## TibiOS Philosophy

Objects represent knowledge. Workloads represent computation. Schedulers place computation. Storage preserves Objects. Networking transports Objects. The Runtime coordinates everything.

## Engineering Motto

Everything is an Object.

Objects outlive machines.
