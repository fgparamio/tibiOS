# TibiOS Object Store

Version: 1.0

## Purpose

The Object Store is the Runtime service responsible for resolving, retrieving, and managing Objects.

It is the canonical entry point through which Runtime domains and applications discover Objects.

The Object Store is **not** the Object Model (`13-object-model.md`), and it is **not** the Runtime Storage Engine (`21-runtime-storage-engine.md`).

The Object Model defines what an Object is.

The Runtime Storage Engine defines how authoritative facts and immutable content are persisted.

The Object Store connects both by exposing Objects as Runtime entities while hiding persistence details.

Applications and Runtime domains interact with Objects through the Object Store, never through the underlying storage implementation.

This document follows the principles defined in `00-philosophy.md` and `02-project-structure.md`.

---

## Ownership

The Object Store belongs to `runtime-object`.

This follows directly from the Ownership principle (`00-philosophy.md`) and the Ports & Adapters architecture (`02-project-structure.md`):

> Every domain owns the services that speak its language.

The Object Store speaks the language of Objects.

Persistence is merely one capability it consumes.

```
                  runtime-object
                  ┌────────────────────┐
                  │                    │
                  │   Object Store     │
                  │                    │
                  └─────────┬──────────┘
                            │
                    Outbound Ports
                            │
          ┌─────────────────┴─────────────────┐
          ▼                                   ▼
   Content Store                    Event Streams
          │                                   │
          └─────────────────┬─────────────────┘
                            ▼
                    runtime-storage
```

The Object Store consumes the persistence services provided by the Runtime Storage Engine to reconstruct and resolve Objects.

Within `runtime-object`, the Object Store is responsible for Object resolution.

It does **not** own Object identity or Object lifecycle. Those remain the responsibility of the Object Model (`13-object-model.md`), even though they live alongside the Object Store in the same crate.

Persistence, Replication, and Authorization belong to entirely separate Runtime domains (`runtime-storage`, the Replication domain, and Trust, respectively).

---

## Core Principles

Objects are discovered through the Object Store.

Storage is an implementation detail.

The Runtime never resolves Objects directly from storage.

Identity belongs to the Object Model.

Durability belongs to the Runtime Storage Engine.

Resolution belongs to the Object Store.

---

## Responsibilities

The Object Store is responsible for:

- resolving Object references;
- resolving Object versions;
- resolving immutable Content Objects;
- exposing Object metadata;
- exposing Object queries;
- maintaining lookup indexes;
- traversing Object reference graphs;
- caching frequently used Objects;
- cooperating with Replication;
- rebuilding indexes during recovery.

The Object Store never:

- defines Object identity;
- schedules Workloads;
- allocates Resources;
- executes Workloads;
- owns persistence;
- owns replication policy;
- interprets authorization rules.

---

## Object Resolution

Objects are always resolved through logical identity.

```
ObjectId
    │
    ▼
Logical Object
    │
    ▼
Content Object
    │
    ▼
Content Store
```

Consumers never navigate these relationships themselves.

The Object Store performs every lookup.

---

## Version Resolution

Logical Objects are resolved through:

- ObjectId
- ObjectVersion

Content Objects are resolved through:

- ContentHash

This distinction follows the Object Model (`13-object-model.md`).

The Object Store applies it.

It never redefines it.

---

## Object Queries

The Object Store exposes conceptual operations rather than storage operations.

Typical operations include:

- GetObject(ObjectId)
- GetVersion(ObjectId, Version)
- ResolveContent(ContentHash)
- Exists(ObjectId)
- ListVersions(ObjectId)
- FindReferences(ObjectId)

The architectural model intentionally avoids defining a concrete API.

Different implementations may expose these capabilities through Rust traits, gRPC, REST, or embedded libraries.

---

## Object Lifecycle Integration

The Object Store does not own Object Lifecycle.

Lifecycle transitions originate in `runtime-object`.

Whenever lifecycle changes occur, the Object Store updates its lookup structures accordingly.

The authoritative source remains the Object Lifecycle Log (`21-runtime-storage-engine.md`).

---

## Relationship with Storage

The Runtime Storage Engine provides persistence capabilities.

The Object Store consumes those capabilities to reconstruct and resolve Objects.

```
Runtime Domain
        │
        ▼
Object Store
        │
        ▼
Runtime Storage Engine
```

No Runtime component bypasses the Object Store to access persistent Objects directly.

---

## Replication Integration

Replication never changes Object identity.

Replication creates additional Physical Replicas of immutable Content Objects.

The Object Store exposes canonical Object relationships required for Replication:

- Object → Content
- Object versions
- Object references
- Content identity

Replication policy belongs to the Replication domain.

The Object Store simply exposes canonical Object information.

---

## Caching

The Object Store may cache:

- Object metadata;
- version indexes;
- reference graphs;
- recently resolved Objects.

Caches are never authoritative.

Every cache is disposable.

After failure, every cache can be rebuilt from authoritative Runtime state.

---

## Recovery

Recovery rebuilds Object resolution from authoritative storage.

```
Runtime Storage Engine
        │
        ▼
Object Lifecycle Log
        │
        ▼
Replay
        │
        ▼
Rebuild Indexes
        │
        ▼
Object Store Ready
```

Recovery never depends on cache contents.

---

## Observability

The Object Store exposes:

- lookup latency;
- cache hit ratio;
- cache miss ratio;
- index rebuild duration;
- resolution failures;
- reference graph statistics.

---

## Anti-Patterns

Avoid:

- bypassing the Object Store;
- exposing storage identifiers;
- making caches authoritative;
- embedding scheduling logic;
- embedding replication policy;
- embedding lifecycle logic;
- accessing Runtime Storage directly from Runtime domains.

---

## Review Checklist

Before extending the Object Store ask:

- Does it resolve Objects rather than define them?
- Does it preserve the separation between Object Model and Storage?
- Is persistence still hidden?
- Can recovery rebuild it?
- Is every cache disposable?
- Does another Runtime domain already own this responsibility?

---

## Principles

- Objects are discovered through the Object Store, never through Storage.
- The Object Store is the canonical resolver of Object identity.
- Every domain owns the services that speak its language.
- Storage owns durability.
- The Object Store owns resolution.
- Caches are optimizations, never sources of truth.

---

## Motto

Resolve Objects.

Hide persistence.

Preserve identity.
