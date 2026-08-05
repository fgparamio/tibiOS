# TibiOS SDK

Version: 1.0

## Purpose

The SDK is not another API. It is how a developer consumes the Runtime API (`26-runtime-api.md`) without hand-rolling requests against it — a typed, idiomatic projection of capabilities that already exist, in whatever host language the developer works in.

The SDK defines no capability the Runtime API does not already expose, and no capability the Runtime API exposes may be reinterpreted by the SDK. It contains no domain logic: every decision it surfaces was already made by whichever Runtime domain owns it, exactly as `26-runtime-api.md` already established for the capability surface itself — the SDK projects that boundary into the developer's host language.

## Ownership

The SDK is a projection pattern, not a canonical implementation. This document defines how a Runtime API is projected into an idiomatic programming language. Individual SDKs (Rust, Python, TypeScript, …) implement that pattern independently — none of them is architecturally "the" SDK.

This mirrors a shape the architecture has already used twice: `18-worker-model.md` defines one Worker contract with multiple implementations (`local-infer`, `tibios-ray`); `26-runtime-api.md` defines one capability surface with multiple technology adapters (gRPC, REST, embedded). `27-sdk.md` defines one projection pattern with multiple language implementations. Same shape, different level.

A Rust SDK may be implemented as a crate inside the Cargo workspace because it shares the language ecosystem with the Runtime, while SDKs for other languages live as independent packages — the same way `tibios-ray` already lives as an independent sibling repository. This is an organizational choice about where source code happens to sit; it does not change the architectural model, and no SDK gains any capability by living inside this workspace that an out-of-workspace SDK lacks.

## Core Principles

- The SDK projects the Runtime API into the host language. It never projects Runtime internals.
- The SDK is a pattern with multiple implementations, never a single canonical crate.
- The SDK introduces no capability the Runtime API does not already expose.
- The SDK contains no domain logic. Every decision it surfaces was already made by the Runtime domain that owns it.
- Consumers program against the SDK; the SDK programs against the Runtime API.
- Where source code lives is an organizational choice. It is never an architectural one.

## SDK Surface

An SDK exposes one client type and one operation per Runtime API capability, named idiomatically for its host language but never renamed in meaning — the Runtime API capabilities already defined in `26-runtime-api.md`, no more, no fewer.

An SDK may add language-idiomatic ergonomics on top of a capability — a builder for `WorkloadSpec`, an async iterator over a streamed capability, a retry helper around a transient transport error — provided none of it changes what capability is being invoked or what it means. Ergonomics are presentation. Capabilities are contract.

## Relationship with Runtime API

Every SDK operation maps to exactly one Runtime API capability, one to one, in both directions: no SDK operation exists without a corresponding capability, and no capability lacks an SDK operation projecting it. The Capability Surface defined in `26-runtime-api.md` is projected unchanged into the SDK.

The SDK never talks to a Runtime domain, an Inbound Port, or a transport directly — only to the Runtime API. If an SDK ever needs information the Runtime API doesn't expose, that is a gap in `26-runtime-api.md`, never a reason for the SDK to reach past it.

## Technology Independence

An SDK is free to use any transport adapter the Runtime API supports (gRPC, REST, embedded in-process calls) internally, and may even switch between them across versions, without the SDK's own public interface changing. A developer who calls `client.submit_workload(spec)` never knows, and never needs to know, whether that call became a gRPC request, an HTTP request, or a direct in-process function call — exactly the same technology-independence guarantee `26-runtime-api.md` already makes for the capability surface, now made for the SDK's own surface as well. Changing transports must never require changing application code.

## Type Mapping

Every public type in the Runtime API's contract maps to exactly one idiomatic type in the host language — a `WorkloadSpec` becomes a Rust struct, a Python dataclass, a TypeScript interface, each following its own language's conventions, all representing the identical contract. **Type Mapping translates representation, never meaning**: a field that is required in the contract is required in every language projection; an enum variant in the contract is not silently widened into a looser type in any SDK.

Identity types (`ObjectId`, `WorkloadId`, `AllocationId`, …) are opaque in every SDK, exactly as they already are inside the Runtime (`02-project-structure.md`'s newtype pattern) — a developer may compare, serialize, and pass them around, but never construct or interpret one directly. Identity generation remains a Runtime responsibility. The SDK does not loosen an invariant the Runtime itself enforces.

## Error Model

An SDK never invents an error the Runtime API doesn't already surface. Every domain error the Runtime API defines (`AdmissionRejected`, `AllocationDenied`, `ObjectNotFound`, …, per `26-runtime-api.md`'s Error Model) is projected into the host language's native error-handling idiom — a `Result<T, TibiosError>` in Rust, an exception hierarchy in Python — without collapsing distinct errors into one generic failure, and without adding a new failure category the Runtime API never produced.

A transport-level failure (a dropped connection, a timeout) is distinct from a domain error and must never be reported as one — a `ConnectionLost` is not an `AdmissionRejected`. Conflating the two would let application code mistake "the request never reached Admission" for "Admission rejected the request," which is a correctness bug in the SDK, not a Runtime API concern. Transport failures belong to the SDK implementation. Domain failures belong to the Runtime contract.

## Streaming Model

Runtime API capabilities that stream (`Observe Events`, the in-flight half of `Query Execution`) are projected into the host language's native streaming abstraction (an async iterator, a channel, a callback), without exposing the underlying transport mechanism (`22-networking.md`'s Runtime Streams remain entirely invisible at this layer, exactly as `26-runtime-api.md` already requires).

A streamed SDK operation still carries only one capability's worth of meaning per item — an `ObserveEvents` iterator yields Runtime Events, never a mix of events and reports, never an auxiliary channel introducing information the capability did not declare.

## Versioning & Compatibility

An SDK version tracks the Runtime API contract version it projects, never the Runtime's internal implementation. A new SDK version is required only when the Runtime API contract evolves (`26-runtime-api.md`'s Versioning & Stability); an internal Runtime change that doesn't touch the contract requires no SDK change at all.

An SDK may support multiple contract versions concurrently, the same way the Runtime API may serve multiple contract versions through different adapters. Compatibility is a property of the contract each SDK version projects, never of the Runtime version it happens to run against.

## Observability

An SDK should expose enough client-side observability (request latency as seen by the caller, retry counts, connection state) to debug integration issues, without duplicating the Runtime API's own Observability (`26-runtime-api.md`) or reaching into Runtime-internal metrics it has no access to and no need for.

## Anti-Patterns

Avoid: an SDK capability with no corresponding Runtime API capability, an SDK operation that changes the meaning of the capability it projects, constructing or interpreting identity types client-side, collapsing distinct domain errors into one generic exception, reporting a transport failure as a domain error, a transport-specific type leaking into the SDK's public interface, treating any single language's SDK as architecturally canonical.

## Review Checklist

Before adding an SDK operation ask: does a corresponding Runtime API capability already exist? Does the mapping preserve the contract's meaning exactly? Does it distinguish domain errors from transport errors? Does it hide the underlying transport completely? Would this SDK operation make sense in every other language's SDK too? Does this operation project an existing capability, or is it accidentally inventing a new one?

## Principles

- The SDK projects the Runtime API into the host language. It never projects Runtime internals.
- The SDK is a pattern with multiple implementations, never a single canonical crate.
- Every Runtime API capability has exactly one SDK projection in each host language.
- Consumers program against the SDK; the SDK programs against the Runtime API.
- Type Mapping translates representation, never meaning.
- Transport failures belong to the SDK implementation. Domain failures belong to the Runtime contract.
- Ergonomics are presentation. Capabilities are contract.
- Where source code lives is an organizational choice. It is never an architectural one.

## Motto

Project the contract. Speak the language. Change nothing in between.
