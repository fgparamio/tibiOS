# TibiOS Project Structure & Dependency Architecture

Version: 2.0

## Purpose

This document defines the architectural organization of the TibiOS codebase.

It specifies

- project structure
- dependency direction
- ownership boundaries
- Runtime composition
- Ports & Adapters
- shared primitives
- dependency rules

The goal is not merely to organize source files.

The goal is to preserve architectural integrity as the Runtime evolves.

## Architectural Principles

The project structure follows five fundamental principles.

1. **Share language, never behavior.**

   Shared behavior creates coupling. Shared primitives create consistency.

2. **Dependencies point toward abstractions.**

   Runtime domains never depend on concrete implementations. Implementations remain replaceable.

3. **Consumers own their ports.**

   Every domain defines the interfaces it requires. Providers implement those interfaces.

4. **Composition happens exactly once.**

   Concrete implementations are assembled only in the Composition Root. Runtime domains never perform dependency wiring.

5. **Every crate owns one responsibility.**

   Each crate represents one architectural capability. Responsibilities never overlap.

## Project Layout

```
tibios/
├── crates/
│   ├── runtime-primitives/
│   ├── runtime-object/
│   ├── runtime-admission/
│   ├── runtime-scheduler/
│   ├── runtime-allocation/
│   ├── runtime-worker/
│   ├── runtime-network/
│   ├── runtime-storage/
│   ├── runtime-security/
│   ├── runtime-observability/
│   ├── runtime-state/
│   └── runtime-api/
└── runtime/
```

The root Runtime crate is the Composition Root. All Runtime services are assembled there.

## Runtime Domains

Each crate owns exactly one architectural domain.

Examples include Admission, Scheduling, Allocation, Object, Networking, Storage, Workers, Trust, Observability.

No crate owns multiple independent domains.

## Dependency Rule

Dependencies always point toward abstractions. Never toward implementations.

Correct:

```
Admission
    ↓
AdmissionLogStore
    ↑
Storage
```

Never:

```
Admission
    ↓
Storage
```

## Shared Behavior

Shared behavior is prohibited. Examples include scheduling helpers, networking utilities, storage helpers, business services.

If behavior belongs to one domain, it remains inside that domain.

## Shared Primitives

Some concepts belong to the Runtime itself rather than to any individual domain. These concepts live in `runtime-primitives`.

This is the only intentionally shared Runtime crate.

### Runtime Primitives

Runtime Primitives contain only infrastructure-neutral concepts. Examples include `ObjectId`, `NodeId`, `RuntimeId`, `WorkloadId`, `AllocationId`, `SessionId`, `TenantId`, `Lease`, `Timestamp`, `ContentHash`, `ObjectVersion`, `ErrorClass`.

`RuntimeId` identifies a Runtime instance independently of the Nodes currently composing it — it is the Identity component of a Deployment Unit (`29-deployment.md`'s "Runtime + Configuration + Identity"), assigned when a Deployment Unit is created. `NodeId` answers which machine participates; `RuntimeId` answers which Runtime it belongs to — two different granularities, both needed once more than one Runtime instance can cooperate.

These types form the ubiquitous language of the Runtime. They are shared because they describe concepts. They never implement domain behavior.

### Primitive Categories

Runtime Primitives contain four categories.

**1. Primitive Types** — `Lease`, `ObjectId`, `Timestamp`, `ContentHash`, etc.

**2. Pure Operations** — `lease.is_expired(now)`, `lease.remaining(now)`, `content_hash.matches(data)`, `object_version.next()`. These operations are deterministic, have no side effects, perform no I/O, and never orchestrate Runtime behavior.

**3. Primitive Generators** — `ObjectId::new()`, `WorkloadId::new()`, `Timestamp::now()`. Primitive Generators intentionally produce new values. They are allowed to depend on local system time and local cryptographic randomness. They never depend on networking, storage, databases, Runtime services, or remote systems. Primitive Generators create values; they never coordinate domains. They are plain functions — no trait, no adapter, no dependency injection — because no architectural need for substitution exists (no domain decision depends on the concrete value produced, and no test needs to control it).

**4. Primitive Interfaces** — universal capabilities where substitution provides genuine architectural value: `Clock` and `RandomGenerator` only. Primitive Interfaces are domain-independent, contain no business semantics, perform no orchestration, and avoid infrastructure dependencies. They exist to preserve deterministic behavior and testability (e.g. `SystemClock` in production, `FakeClock` in tests, so that time-dependent logic like `lease.is_expired(clock.now())` remains testable). **`IdentityGenerator<T>` does not exist as an interface anywhere in the Runtime** — no test needs to control the concrete value of a generated identity, so no substitution need justifies an abstraction; domains call the concrete Primitive Generators directly.

### Primitive Philosophy

Primitives describe. Primitives calculate. Primitives generate. Primitives never orchestrate.

No abstraction should be introduced without demonstrated architectural value — including inside `runtime-primitives` itself.

### Dependency Constraints

The `runtime-primitives` crate must remain infrastructure-neutral.

It must not depend on:

- asynchronous runtimes
- networking libraries
- storage libraries
- RPC frameworks
- databases
- other Runtime crates

It may depend on libraries that provide structural derives, pure algorithms, deterministic utilities, format-agnostic serialization, or local identity generation. Examples include `serde` and `ulid`.

The distinction is between a **structural contract** (`serde` — does not decide a wire format) and a **protocol** (`prost`, `tonic`, `flatbuffers`, `capnproto`, `avro` — each commits the type to a specific wire format or RPC framework). Structural contracts are allowed; protocols are not.

The exact dependency list may evolve. The architectural rule remains stable: infrastructure must never leak into Runtime Primitives.

### Identity Model

Mutable Runtime entities use ULID-based identities: `ObjectId`, `NodeId`, `RuntimeId`, `WorkloadId`, `AllocationId`, `SessionId`, etc.

The concrete ULID implementation remains encapsulated in newtypes (e.g. `pub struct ObjectId(Ulid)`). Runtime domains depend only on Runtime primitive types. They never depend directly on the underlying `ulid` library.

### Dependency Graph

```
runtime-primitives
        │
        ▼
 All Runtime Domains
```

No Runtime domain may appear above Runtime Primitives. Runtime Primitives form the root of the dependency graph.

---

## Ports & Adapters

TibiOS follows Ports & Adapters (Hexagonal Architecture, Cockburn). Runtime domains communicate exclusively through contracts. Concrete implementations remain isolated.

### Architectural Rule

Dependencies always point toward abstractions. Implementations never determine dependency direction.

### Consumer-Owned Contracts

Every Runtime domain defines the interfaces it requires. Consumers own contracts. Providers implement contracts. This guarantees that every domain expresses its own language. Providers never impose technology-specific APIs.

This rule applies to **domain-specific service contracts** — see "Universal Capabilities" below for the exception covering Clock/RandomGenerator.

### Ports

Ports are contracts. Ports belong to the domain that consumes them. Ports describe capabilities. Ports never expose implementation details.

**Inbound Ports** represent the public capabilities of a Runtime domain — how external components interact with it. Examples: `AdmissionService`, `SchedulingService`, `AllocationService`, `TrustService`, `WorkerService`. Inbound Ports belong to the owning domain and define its public language.

**Outbound Ports** represent external capabilities required by a Runtime domain. Examples: `AdmissionLogStore`, `ObjectRepository`, `TrustProvider`, `Transport`. Outbound Ports are defined by the consuming domain. They never belong to infrastructure.

### Technology Independence

Ports express domain language. Ports never expose technology.

Correct: `append(record)`, `find(workload_id)`, `load(object_id)`.

Incorrect: `execute_sql(...)`, `put_to_rocksdb(...)`, `send_grpc(...)`, `publish_kafka(...)`.

Ports describe intent. Adapters implement technology.

### Adapters

Adapters implement Outbound Ports. Examples: Runtime Storage, Runtime Networking, Runtime Security, Runtime Observability. Adapters translate domain language into infrastructure.

**Adapter Ownership**: Providers own adapters. Consumers own ports. This separates domain behavior from infrastructure.

Correct:

```
Admission
    ↓
AdmissionLogStore
    ↑
Storage Adapter
```

Incorrect:

```
Admission
    ↓
Storage
```

Runtime domains never depend on infrastructure.

### Universal Capabilities (exception to Consumer-Owned Contracts)

`Clock` and `RandomGenerator` are not domain-specific service contracts — they are universal, structurally identical regardless of who consumes them, with no domain semantics. Duplicating their trait definition per domain would be pure boilerplate with no architectural benefit. They are therefore defined once, in `runtime-primitives`, as Primitive Interfaces (see above), and every domain uses that single definition directly.

**Rule**: Consumer-owned ports apply only to domain-specific capabilities. Universal Runtime capabilities belong to `runtime-primitives`.

Identity generation (`ObjectId::new()`, `WorkloadId::new()`, etc.) is **not** abstracted behind any port or interface, anywhere. No domain decision and no test assertion depends on the concrete value of a freshly generated identity — so no substitution need exists, and introducing `IdentityGenerator<T>` would violate the next rule.

**Rule**: Abstractions are introduced to solve demonstrated architectural problems, not to maximize symmetry.

### Composition Root

Concrete implementations are assembled only once. The `runtime` crate is the Composition Root. It creates concrete services, injects implementations, and wires the Runtime graph. No other crate performs dependency composition.

```
runtime (Composition Root)
    │
    ├── Storage Engine
    ├── Networking
    ├── Trust
    ├── Scheduler
    ├── Allocation
    ├── Workers
    └── Observability
```

The Runtime owns assembly. Domains own behavior.

### Dependency Injection

Domains receive dependencies. Domains never construct infrastructure.

Correct: `Admission::new(log_store, clock)`

Incorrect: `Admission::new(StorageEngine::new())`

Construction belongs exclusively to the Composition Root.

### Domain Isolation

Runtime domains remain independent:

- Admission never depends on Storage, Networking, Scheduler.
- Scheduler never depends on Storage, Workers.
- Allocation never depends on Worker implementations.
- Networking never depends on Storage, Scheduler, Admission.

Domains communicate only through Ports — except for **Data Contracts** flowing along the natural pipeline direction (see "Data Contracts" below): e.g. `runtime-allocation` depends on `runtime-scheduler` for the `AllocationPlan` and `Resource` types it consumes, since those are data produced upstream, not a service dependency.

### Shared Infrastructure

Infrastructure implementations may serve multiple domains (Storage, Networking, Observability). Sharing implementations is acceptable. Sharing behavior is not.

### Composition Responsibility

The Composition Root owns implementation selection, dependency wiring, lifecycle creation, Runtime startup, and Runtime shutdown. Domains never perform these tasks.

### Dependency Graph

```
runtime-primitives
        │
        ▼
  Domain Crates
        │
        ▼
      Ports
        ▲
        │
Infrastructure Adapters
        ▲
        │
runtime (Composition Root)
```

Every dependency follows one direction. No cycles are permitted.

### Architectural Philosophy

Domains own behavior. Consumers own contracts. Providers own adapters. The Runtime owns composition. Technology remains replaceable. Behavior remains stable.

---

## Data Contracts

Runtime domains exchange immutable data contracts. Data contracts describe information. They never contain behavior.

### Data Contract Ownership

Data contracts belong to the domain that **produces** them. They represent the public language of the producing domain. Consumers depend on these contracts. Producers never depend on consumers.

```
Admission     → AdmissionDecision → Scheduler
Scheduler     → AllocationPlan    → Allocation
Allocation    → AllocationContract → Worker
```

The producer owns the contract. Consumers never redefine it.

### Service Contract Ownership

Service contracts follow the opposite direction: they belong to the **consuming** domain (this is the Outbound Port rule above, restated for symmetry with Data Contracts).

```
Admission   → AdmissionLogStore ← Storage
Allocation  → ResourceRepository ← Storage
Networking  → TrustProvider      ← Security
```

This keeps infrastructure replaceable.

**Rule**: Data contracts belong to the producer. Service contracts belong to the consumer.

### Crate Responsibilities

Each Runtime crate owns one domain, one public language, one responsibility. Crates never overlap responsibilities. Large domains may contain internal modules — they are never split by technology.

### Internal Organization

A Runtime crate may internally organize code into `api/`, `domain/`, `ports/`, `adapters/`, `model/`, `tests/`. This internal organization is invisible to other crates. Only public APIs define inter-crate communication.

### Domain Evolution

New Runtime capabilities should extend existing domains whenever ownership remains unchanged. A new crate is introduced only when a genuinely new architectural responsibility appears. Avoid creating crates for utilities, helpers, abstractions, or convenience APIs. Crates represent domains, never implementation details.

### Dependency Cycles

Dependency cycles are prohibited. Every Runtime dependency graph must remain acyclic.

Correct: `Admission → Scheduler → Allocation → Worker`

Incorrect: `Admission → Scheduler → Allocation → Admission`

Cycles indicate misplaced ownership.

### Cross-Domain Communication

Runtime domains communicate only through Data Contracts, Service Contracts, and Runtime Events. No Runtime domain directly manipulates another domain's internal state.

### Runtime Events

Events communicate facts. Events never request actions.

Correct: `AllocationCreated`, `LeaseExpired`, `TrustRevoked`, `WorkerStarted`.

Incorrect: `AllocateResources`, `CloseSession`, `RunWorker`, `StoreObject`.

Commands belong to services. Events describe completed facts.

**Rule**: Events communicate facts. Commands request actions. Domains decide their own reactions.

> Applied example: when Trust revokes an identity, the fact is `TrustRevoked` (owned by Trust/Security). Networking subscribes to that fact and, as the owner of Sessions, decides internally to close matching sessions. Closing a session is Networking's own reaction, not a shared event named after the action (e.g. never `SessionRevocation`).

### Ownership Boundaries

Every Runtime concept belongs to exactly one owner.

| Concept | Owner (crate) |
|---|---|
| AdmissionDecision | `runtime-admission` |
| AllocationPlan | `runtime-scheduler` |
| AllocationContract | `runtime-allocation` |
| Session | `runtime-network` |
| Object | `runtime-object` |
| Resource | `runtime-scheduler` (internal modules: `resource/`, `candidate/`, `filter/`, `score/`) |
| Lease | `runtime-primitives` |

Ownership determines modification rights. Consumers observe. Owners decide.

This applies to services as much as it applies to state — see `00-philosophy.md`'s Ownership principle: every domain owns the services that speak its language; infrastructure provides capabilities, never meaning.

`Object` owns its own crate because the Object Model (identity, metadata, lifecycle, relationships, content reference) exists independently of how it is persisted — the same reasoning as the Repository pattern: the domain entity never depends on its persistence mechanism. `runtime-storage` implements `ObjectRepository` / `ContentStore` / the Object Lifecycle Log, but never owns the model.

`Resource` stays inside `runtime-scheduler` because, unlike Object, it has no autonomous lifecycle — it is the language of the scheduling pipeline (Candidate Discovery → Filter → Score → Allocation).

### Public Surface

Every Runtime crate exposes a minimal public API. Everything else remains private. Public APIs should expose services, data contracts, and public types. Implementation details remain hidden.

### Stable Dependencies

Changing an implementation should never require changing dependent domains. Only contract evolution should affect consumers. Stable contracts reduce architectural coupling.

### Adding New Dependencies

Before introducing a new dependency, ask:

1. Does this dependency introduce infrastructure?
2. Does it belong to Runtime Primitives?
3. Does it belong to a single domain?
4. Can an existing Port express this capability?
5. Does it preserve the DAG?

If the answer is no, the dependency should not be introduced.

### Runtime Growth

As the Runtime grows, new domains should naturally fit into the existing dependency graph. Architectural growth should be additive. Never disruptive.

### Architecture Review Checklist

Before creating a new crate, verify:

1. Does it own a new architectural responsibility?
2. Does it expose a unique public language?
3. Does it preserve ownership?
4. Does it avoid dependency cycles?
5. Does it require its own Ports?
6. Does it justify becoming a first-class Runtime domain?

If any answer is no, the capability probably belongs inside an existing crate.

### Engineering Philosophy

A Runtime grows by adding responsibilities. Never by adding layers. The dependency graph should become richer. Never more tangled. Architecture should become clearer as the system evolves.

---

## Cargo Workspace

The Runtime is organized as a Cargo workspace. Each Runtime domain is implemented as an independent crate.

The workspace provides unified dependency management, consistent versioning, shared tooling, isolated compilation, and incremental builds.

Workspace organization never changes architectural ownership.

### Versioning

Runtime crates evolve independently. Internal implementation changes must not affect dependent domains. Public contract evolution must remain explicit. Breaking changes should occur only through intentional contract evolution.

## Runtime Composition

The Runtime executable is the Composition Root. It is responsible for creating infrastructure implementations, wiring dependencies, configuring Runtime services, starting Runtime actors, managing lifecycle, and graceful shutdown.

The Composition Root owns no business behavior. Its responsibility is assembly only.

### Runtime Startup

```
Create Configuration
        │
        ▼
Create Infrastructure
(Storage, Networking, Observability)
        │
        ▼
Create Domain Services
(Admission, Scheduler, Allocation, Worker)
        │
        ▼
Inject Dependencies
        │
        ▼
Start Runtime
```

Construction and execution remain separate concerns.

### Runtime Shutdown

Shutdown follows the reverse order:

```
Stop accepting new work
        │
        ▼
Drain active operations
        │
        ▼
Release leases
        │
        ▼
Flush authoritative logs
        │
        ▼
Terminate infrastructure
```

Ownership determines shutdown order.

## Architectural Evolution

The Runtime evolves by introducing new responsibilities. Never by increasing coupling. New capabilities should naturally fit into the existing dependency graph. If a capability cannot be placed without violating ownership, the ownership model should be reconsidered before adding code.

### Adding a New Runtime Domain

Before introducing a new Runtime crate, verify:

1. Does it own a unique responsibility?
2. Does it define a unique language?
3. Does it expose a public API?
4. Does it preserve the dependency graph?
5. Can it evolve independently?

If the answer is no, the capability belongs inside an existing Runtime domain.

### Adding a New Port

Before defining a new Port, verify:

1. Is the capability domain-specific?
2. Does substitution provide architectural value?
3. Is it already represented by Runtime Primitives?
4. Is the contract expressed in the consumer's language?

If the answer is no, a new Port should not be introduced.

### Adding a New Primitive

Runtime Primitives are intentionally difficult to extend. Before introducing a new primitive, verify:

1. Is it fundamental to the entire Runtime?
2. Is it independent of any domain?
3. Does it avoid infrastructure?
4. Does it avoid business behavior?
5. Will multiple Runtime domains naturally use it?

Only concepts satisfying all conditions belong to Runtime Primitives.

## Anti-Patterns

Avoid:

- shared business logic
- utility crates accumulating unrelated code
- cyclic dependencies
- infrastructure-aware domain models
- provider-owned service contracts
- technology-specific Ports
- infrastructure leaking into Runtime Primitives
- composition outside the Composition Root

Each anti-pattern increases architectural coupling.

## Architecture Map

This document defines structural rules. Other architecture documents define domain behavior.

| Document | Defines |
|---|---|
| `00-philosophy` | Architectural principles |
| `11-runtime` | Runtime responsibilities |
| `02-project-structure` | Dependency architecture (this document) |
| `13-object-model` | Object domain |
| `14-resource-model` | Resource language |
| `15-allocation-model` | Allocation domain |
| `16-scheduling-engine` | Scheduling Engine |
| `17-cluster-snapshot` | Cluster Snapshot |
| `18-worker-model` | Worker domain |
| `19-state-assembler` | Runtime state assembly |
| `20-admission-control` | Admission domain |
| `21-runtime-storage-engine` | Storage domain |
| `22-networking` | Networking domain |
| `23-object-store` | Object resolution service |
| `24-replication` | Content availability service |
| `25-ai-runtime` | AI workload specialization (introduces no new primitives) |
| `26-runtime-api` | Public capability surface (Block 2 begins) |
| `27-sdk` | Typed projection pattern (multi-language, no canonical crate) |
| `28-cli` | Human command projection (closes the Runtime API / SDK / CLI trilogy) |
| `29-deployment` | Runtime instance lifecycle (plane of existence, complements the Composition Root) |
| `30-ai-services` | AI capability composition (no new crate — pure composition of 13/18/25/26/29) |

The pipeline these documents describe together:

```
Resource Model → State Assembler → Cluster Snapshot → Scheduling Engine → Allocation → Worker
```

This document never defines domain behavior. It defines where that behavior belongs.

## Architecture Summary

The Runtime is organized around ownership.

- Every concept belongs to exactly one owner.
- Every domain owns exactly one responsibility.
- Every dependency points toward an abstraction.
- Every implementation is assembled exactly once.
- Shared behavior is prohibited.
- Shared primitives are intentionally minimal.
- The dependency graph remains acyclic.

The Runtime grows by adding responsibilities, never by increasing coupling.

## Engineering Principles

Share language. Never share behavior.

Consumers own service contracts. Producers own data contracts.

Compose once. Depend on abstractions.

Preserve ownership. Protect the dependency graph.

## Final Principle

The project structure exists to protect the architecture.

Directories may change. Modules may change. Implementations may change.

Ownership, dependency direction, and architectural boundaries must remain stable.
