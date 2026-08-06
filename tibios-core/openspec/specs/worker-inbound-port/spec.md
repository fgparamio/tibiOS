# Worker Inbound Port Specification

## Purpose

`worker-inbound-port` is the Worker domain's public language and its Inbound Port capability: the domain types the Runtime and a Worker implementation exchange, and the guarantee that this whole surface is exercisable in a plain `cargo test` — no async runtime, no transport, no I/O — realizing `18-worker-model.md`'s testability claim ("a fake Execution Context plus an in-memory channel, no real infrastructure required", `06-testing.md`).

This capability is realized by `runtime-worker` (which owns the concrete trait and type definitions — see its own spec delta for crate-level structural requirements: module layout, exact enum arm counts, containment) and consumes `runtime-allocation`'s `AllocationContract` and `runtime-primitives`'s `Classify`. This spec states the cross-cutting, capability-level guarantees that make the port real and independently testable, deferring the concrete async mechanism (AFIT, enum dispatch, boxed future) to `sdd-design`.

## Requirements

### Requirement: WorkerService Exposes Exactly The Three Wire-Mirrored Capabilities

The Worker domain's Inbound Port, `WorkerService`, MUST expose exactly three capabilities — one to start an execution (`execute`), one to cooperatively request cancellation of an in-flight execution (`cancel`), and one to check the health of an in-flight execution (`pulse`) — mirroring, one-to-one and permanently, the three RPCs of the frozen wire contract (`SubmitJob`, `Cancel`, `Pulse`). The domain MUST never be poorer than its wire projection: no capability the wire exposes may be missing from `WorkerService`, and no capability may be added that the wire does not also expose.

#### Scenario: WorkerService's three capabilities match the wire's three RPCs one-to-one

- GIVEN `WorkerService`'s capabilities and `WorkerExecution`'s RPCs (`worker.proto`)
- WHEN the two sets are compared
- THEN each of the three RPCs (`SubmitJob`, `Cancel`, `Pulse`) has exactly one corresponding `WorkerService` capability (`execute`, `cancel`, `pulse`), and neither set has an entry unmatched in the other

### Requirement: ExecutionContext Carries No Channel And No Cancellation Signal

`ExecutionContext`, the immutable data a Worker receives to perform one execution, MUST NOT contain the Execution Channel and MUST NOT contain a cancellation signal as fields — both arrive as separate parameters to the Inbound Port capability that uses them, never as part of the context value itself. This holds even though `18-worker-model.md:52`'s prose lists the Execution Channel among what a Context "contains": the frozen wire contract already resolved this literally (`worker.proto:68` — "There is no Channel field and no CancellationToken field... neither serializes"), and the domain follows the same split so that a fake `ExecutionContext` remains trivially constructible without also having to fake a channel or a cancellation primitive.

#### Scenario: A fake ExecutionContext needs no channel or cancellation value to construct

- GIVEN a test that constructs an `ExecutionContext` value using only public constructors or fields
- WHEN the constructed value is inspected
- THEN it required no channel value and no cancellation-signal value to build

### Requirement: ExecutionEvent Has Exactly Six Arms And ExecutionPhase Has No Unspecified State

`ExecutionEvent`, the Worker's typed event stream, MUST be a closed enum of exactly six variants, matching the wire's six `oneof` arms permanently. `ExecutionPhase`, the Worker-local lifecycle enum reported by `ExecutionReport` and `ExecutionPulse`, MUST have exactly six states and MUST NOT define an `Unspecified`, `Unknown`, or other default/placeholder state — the wire's `EXECUTION_PHASE_UNSPECIFIED` is a proto3 tag-zero wire obligation, not a state a Worker can occupy, and the boundary conversion rejects it as `Permanent` rather than mapping it into the domain.

#### Scenario: ExecutionEvent's six domain arms and ExecutionPhase's six domain states are exhaustive

- GIVEN the `ExecutionEvent` and `ExecutionPhase` domain enums
- WHEN their variants are enumerated
- THEN `ExecutionEvent` has exactly six and `ExecutionPhase` has exactly six, with no placeholder state in either

### Requirement: The Domain Surface Names No Transport Type And No Tokio Type

Every public type and trait making up the Worker domain's language and its Inbound/Outbound Ports (`WorkerService`, `ExecutionChannel`, `ExecutionContext`, `ExecutionEvent`, `ExecutionReport`, `ExecutionPhase`, `ExecutionPulse`, the cancellation-acknowledgement type, `WorkerError`, and every other type reachable from them) MUST NOT name, in any field, parameter, return type, or trait bound, a `tonic::`, `prost::`, or `tokio::` path. The domain's language belongs to `runtime-worker`, never to a transport library or an async runtime.

#### Scenario: The full domain surface is free of transport and Tokio paths

- GIVEN every public type and trait that makes up the Worker domain's language and ports
- WHEN each signature, field type, and trait bound reachable from them is inspected
- THEN no `tonic::`, `prost::`, or `tokio::` path appears anywhere in it

### Requirement: The Port Is Exercisable With A Fake Context And An In-Memory Channel, Zero Tokio Runtime, Zero Transport, Zero I/O

A test-only fake `ExecutionContext` value together with a test-only in-memory `ExecutionChannel` implementation MUST be sufficient to invoke every `WorkerService` capability (`execute`, `cancel`, `pulse`) end-to-end inside a `cargo test` run that starts no async runtime (no `#[tokio::test]`, no `tokio::runtime::Runtime`, no executor of any kind), opens no network connection, and performs no filesystem I/O. This is `18-worker-model.md`'s own testability claim, made concrete and enforced as a test: "a fake Execution Context plus an in-memory channel, no real infrastructure required."

#### Scenario: execute runs against a fake context and an in-memory channel with zero runtime, zero transport, zero I/O

- GIVEN a fake `ExecutionContext` value and an in-memory `ExecutionChannel` implementation that records emitted events in memory
- WHEN a test invokes the `execute` capability with both
- THEN the test compiles and runs to completion without starting any async runtime, without opening a network connection, and without touching the filesystem
- AND the events recorded by the in-memory channel are inspectable by the test

#### Scenario: cancel and pulse run under the same constraints

- GIVEN a `WorkloadId` correlating a test scenario to an in-flight (faked) execution
- WHEN a test invokes the `cancel` capability and, separately, the `pulse` capability, using only fakes and test doubles
- THEN both run to completion without starting any async runtime, without opening a network connection, and without touching the filesystem

### Requirement: ExecutionContext Carries A Mandatory Worker Capability

`ExecutionContext` MUST carry a `WorkerCapability` value naming which behavior an execution requests (e.g. `chat.generate`). This value MUST be exposed via a public read accessor and MUST NOT be optional, defaultable, or omittable — every path that constructs an `ExecutionContext` (public constructor or public fields) MUST supply one. This closes the gap where `tibios-ray`'s `context.py` already models `capability: str` with no contractual wire source.

#### Scenario: A fake ExecutionContext must supply a capability to construct

- GIVEN a test that constructs an `ExecutionContext` value using only public constructors or fields
- WHEN the construction is attempted without a `WorkerCapability` value
- THEN it does not compile — no default or optional path exists to skip it

#### Scenario: WorkerCapability is readable via a public accessor

- GIVEN a constructed `ExecutionContext` value
- WHEN its capability accessor is called
- THEN it returns the exact `WorkerCapability` value supplied at construction
