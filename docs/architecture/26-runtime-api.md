# TibiOS Runtime API

Version: 1.0

## Purpose

The Runtime API is the single coherent surface through which anything external — an application, the SDK, the CLI, another TibiOS Runtime — addresses the Runtime. It is not a protocol, not a transport, and not a new domain. It introduces no operation that does not already exist inside a Runtime domain (`13-object-model.md`–`25-ai-runtime.md`); it only makes those operations addressable from outside the Runtime.

This document does not choose REST, gRPC, or any other protocol. It defines what can be asked of the Runtime, expressed in the Runtime's own language — the same discipline `02-project-structure.md`'s Ports already require: *"Ports express domain language. Ports never expose technology."*

## Ownership

The Runtime API owns its own crate, `runtime-api` — already reserved for this purpose in `02-project-structure.md`'s Project Layout. Unlike every domain crate from `13-object-model.md` to `25-ai-runtime.md`, `runtime-api` owns no domain logic of its own: it is a thin routing layer that maps external requests onto existing Inbound Ports, and existing Runtime Events into externally observable ones. If `runtime-api` ever needs to make a decision a domain hasn't already made, that is a signal the request doesn't belong here — not a reason to add logic to this crate.

## Core Principles

- The Runtime API exposes Runtime operations, never Runtime implementation.
- The Runtime API is addressed to Runtime API operations, never Runtime components. A consumer never talks to a Worker, a Scheduler, or a State Assembler — it talks to an operation, and the Runtime routes it internally to whichever domain owns that operation.
- Every public operation corresponds to exactly one authoritative Runtime domain.
- The Runtime API implements no domain logic. Every decision it surfaces was already made by the domain that owns it.
- The Runtime API composes existing operations. It never invents new ones.
- Technology is an adapter. The Runtime API Surface is stable independent of REST, gRPC, or any future protocol.

## Runtime API Surface

The Runtime exposes a finite set of operations, never a resource, endpoint, or transport shape. Each operation answers one question a consumer can ask of the Runtime:

- **Submit Workload** — request that a Workload be admitted and, eventually, executed.
- **Query Objects** — resolve an Object reference to its current state or content.
- **Manage Objects** — register, update, or archive a Logical Object.
- **Observe Events** — subscribe to Runtime Events as they are published.
- **Query Execution** — inspect the state of a Workload's execution, in flight or completed.
- **Inspect Cluster** — obtain a scheduling-relevant view of cluster state.
- **Manage Allocations** — inspect, renew, or release the Allocations bound to a Workload.

This list is deliberately not exhaustive and not final — an operation is added only when a Runtime domain already exposes it through an Inbound Port and no existing operation already covers it (see Review Checklist). The Runtime API Surface grows only by discovery, the same rule `00-philosophy.md` applies to the architecture as a whole.

## Technology Independence

An operation has typed inputs and outputs, never an HTTP verb, a URL path, or a protobuf message. `SubmitWorkload(WorkloadSpec) -> WorkloadId` is an operation; `POST /v1/workloads` is one possible adapter over it. The Runtime API may be exposed simultaneously through multiple adapters (gRPC, REST, an embedded Rust library) without the operation definitions changing — exactly `02-project-structure.md`'s Adapter Ownership rule, applied at the Runtime's outermost boundary instead of between two internal domains.

## Relationship with Runtime Domains

Every Runtime API operation maps to exactly one authoritative Runtime domain. The Runtime API owns no operation's meaning — only its address. This table is the Ownership principle applied at the Runtime boundary.

| Runtime API Operation | Runtime Domain |
|---|---|
| Submit Workload | Admission (`20-admission-control.md`) |
| Query Objects | Object Store (`23-object-store.md`) |
| Manage Objects | Object Store (`23-object-store.md`) |
| Observe Events | The authoritative domain that publishes each Runtime Event; delivery is transport-agnostic and handled by the Runtime using the Networking transport services (`22-networking.md`) |
| Query Execution | Runtime execution services: live Execution Events while in flight, and Execution Reports from the Report Store after completion (`21-runtime-storage-engine.md`) — never a Worker directly (`18-worker-model.md`) |
| Inspect Cluster | State Assembler (`19-state-assembler.md`) via the published Cluster Snapshot (`17-cluster-snapshot.md`) |
| Manage Allocations | Allocation (`15-allocation-model.md`) |

Clients subscribe to event streams. They never subscribe to Runtime domains directly — the domain that owns an event never knows, or needs to know, that a client exists.

Each row is a pointer to an operation the owning domain already exposes. `runtime-api` contains no business logic. It merely exposes these operations through technology-specific adapters.

Every document in the Runtime Core answered a question of the shape "who owns X?" This document answers a different one: **who is allowed to expose X to the outside world?** The public Runtime API Surface is owned by exactly one crate: `runtime-api`. Domains remain the sole owners of meaning; `runtime-api` is the sole owner of the public surface.

## Authentication and Authorization at the Boundary

Every request arriving at `runtime-api` carries an identity. Authentication verifies that identity; authorization decides what it may do — the same two-stage separation `22-networking.md` already established for peer-to-peer communication (*"Authentication proves identity. It does not grant authorization."*), applied here at the external boundary instead of between Runtime instances.

`runtime-api` never makes an authorization decision itself. It authenticates the caller, then asks Trust whether the authenticated identity is authorized for the requested operation — exactly the same query Networking already makes before establishing a Session (`22-networking.md`'s Trust Authorization). Authorization is evaluated before routing. Routing is never used to determine authorization. A request that fails authorization is rejected before it reaches any Runtime domain; the owning domain never sees an unauthorized request.

## Error Model

A Runtime domain that rejects a request produces a domain-specific error: `AdmissionRejected(reason)`, `AllocationDenied(reason)`, `ObjectNotFound`. `runtime-api` never invents a new error category — it translates each domain error into the public contract's error shape, preserving the domain's reason rather than replacing it with a generic one.

Only the domain that owns a decision may produce the error describing that decision: Admission produces `AdmissionRejected`, Allocation produces `AllocationDenied`, Object Store produces `ObjectNotFound`. `runtime-api` never produces a domain error on a domain's behalf — the same Ownership rule that already governs Runtime Events (`00-philosophy.md`'s State Propagation) applies symmetrically to errors.

This is the same responsibility an Adapter has in Ports & Adapters (`02-project-structure.md`): an Adapter translates between a Port's language and infrastructure's language without changing meaning. `runtime-api`'s Error Model translates between a domain's error language and the public contract's error language, in exactly the same spirit, at exactly the same boundary — an adapter, not a new source of truth.

## Versioning & Stability

An operation's contract may evolve, but only forward: new optional fields, new operations, never a silent change in the meaning of an existing one. `runtime-api` exposes a new contract version when an operation's contract evolves — the evolution is the owning domain's decision; `runtime-api` only publishes it, consistent with `02-project-structure.md`'s Stable Dependencies rule (*"Changing an implementation should never require changing dependent domains. Only contract evolution should affect consumers."*).

Multiple contract versions may be served concurrently by different adapters over the same underlying operations — versioning is a property of the public contract, never of the Runtime domain behind it. Consumers version against operations, never against implementations.

Three adapters now share the same shape across the architecture: Storage translates facts into persistence (`21-runtime-storage-engine.md`), Networking translates facts into transport (`22-networking.md`), and `runtime-api` translates operations into public contract. All three preserve meaning; none of them owns it; each changes only the medium.

## Observability

`runtime-api` exposes request latency, request volume per operation, authentication failures, authorization failures, and per-operation error rates. It never exposes domain-internal metrics directly — those belong to the owning domain's own Observability (`09-observability.md`); `runtime-api` only measures its own translation layer.

## Anti-Patterns

Avoid: business logic inside `runtime-api`, operations that don't map to an existing Inbound Port, authorization decisions made inside `runtime-api` instead of delegated to Trust, protocol-specific concepts (HTTP verbs, gRPC streams) leaking into operation definitions, a generic error type that discards a domain's specific reason, breaking an existing operation's contract instead of versioning it, clients addressing a Runtime domain or component by name.

## Review Checklist

Before adding a new operation ask: does an existing Runtime domain already expose this through an Inbound Port? Does it map to exactly one authoritative domain? Is it expressed independently of any transport? Does authorization happen before routing, not inside it? Does its error surface preserve the owning domain's reason? Would removing `runtime-api` still leave every domain fully capable internally?

## Principles

- The Runtime API exposes Runtime operations, never Runtime implementation.
- The Runtime API is addressed to Runtime operations, never Runtime components.
- Every public operation corresponds to exactly one authoritative Runtime domain.
- The Runtime API composes existing operations. It never invents new ones.
- The Runtime API implements no domain logic. Every decision it surfaces was already made by the domain that owns it.
- Authorization is evaluated before routing, never determined by it.
- Only the domain that owns a decision may produce the error describing it.
- Consumers version against operations, never against implementations.
- Domains remain the sole owners of meaning; `runtime-api` is the sole owner of the public surface.
- Technology is an adapter. The Runtime API Surface is stable independent of REST, gRPC, or any future protocol.

## Motto

Expose operations. Preserve meaning. Translate faithfully.
