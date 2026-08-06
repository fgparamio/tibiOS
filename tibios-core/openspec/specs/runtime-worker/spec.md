# Worker Domain Specification

## Purpose

`runtime-worker` is the Worker domain's public language and its Inbound Port, implementing `18-worker-model.md`. It exposes `WorkerService` — the Inbound Port through which the Runtime invokes a Worker (`02-project-structure.md:196`) — and `ExecutionChannel` — the Worker-owned Outbound Port through which a Worker emits events — together with the domain types that flow through both, all outside `adapters/`.

## Requirements

### Requirement: Exhaustive Dependency Set

`runtime-worker` MUST depend on exactly `runtime-primitives`, `runtime-allocation`, and `runtime-object` among workspace crates, and on no other workspace crate. Its external (non-workspace, normal) dependencies MUST be a subset of `{tonic, prost}`, and its build-dependencies MUST be a subset of `{tonic-build}`.

#### Scenario: Declared dependencies match the allowed set

- GIVEN `runtime-worker/Cargo.toml`
- WHEN `cargo metadata` is inspected
- THEN its workspace-crate dependencies are exactly `runtime-primitives`, `runtime-allocation`, and `runtime-object`

#### Scenario: External deps stay within the allowlist

- GIVEN `runtime-worker/Cargo.toml`
- WHEN its `[dependencies]` are read
- THEN every non-workspace entry is `tonic`, `prost`, or a transitive dependency of those crates

#### Scenario: Build-dependency stays within the allowlist

- GIVEN `runtime-worker/Cargo.toml`
- WHEN its `[build-dependencies]` are read
- THEN every entry is `tonic-build` or a transitive dependency of it

### Requirement: Crate Doc Comment Cites the Owning Document

`runtime-worker/src/lib.rs` MUST carry a crate-level doc comment citing `18-worker-model.md`.

#### Scenario: Doc comment cites the owning doc

- GIVEN `runtime-worker/src/lib.rs`
- WHEN its crate doc comment is read
- THEN it references `18-worker-model.md`

### Requirement: WorkerService Is The Worker Domain's Public Inbound Port

`runtime-worker` MUST expose a public `WorkerService` trait, defined outside `src/adapters/`, naming exactly three capabilities — `execute`, `cancel`, and `pulse` — mirroring, one-to-one, the three permanent RPCs of the frozen wire contract (`SubmitJob`, `Cancel`, `Pulse`). `WorkerService` MUST NOT expose a fourth capability, and none of its method signatures MUST name a `tonic::`, `prost::`, or `tokio::` path. The async mechanism by which these capabilities are expressed is unconstrained by this requirement.

#### Scenario: WorkerService trait is public and lives outside adapters

- GIVEN `runtime-worker`'s public API
- WHEN `WorkerService` is looked up
- THEN it is a trait reachable from outside the crate
- AND its definition lives outside `src/adapters/`

#### Scenario: WorkerService exposes exactly three capabilities

- GIVEN the `WorkerService` trait definition
- WHEN its capabilities are enumerated
- THEN there are exactly three: one mirroring `SubmitJob` (`execute`), one mirroring `Cancel` (`cancel`), one mirroring `Pulse` (`pulse`)
- AND no fourth capability exists

#### Scenario: WorkerService signatures name no transport or async-runtime type

- GIVEN the `WorkerService` trait's method signatures
- WHEN each parameter type and return type is inspected
- THEN none names a `tonic::`, `prost::`, or `tokio::` path

### Requirement: ExecutionChannel Is The Worker-Owned Outbound Port

`runtime-worker` MUST expose a public `ExecutionChannel` trait, defined outside `src/adapters/`, naming exactly one capability — `emit`, taking one `ExecutionEvent` — through which a Worker publishes events. `ExecutionChannel` MUST be transport-agnostic: its definition MUST NOT name any `tonic::`, `prost::`, or `tokio::` path, and MUST NOT presuppose gRPC, WebSocket, Server-Sent Events, Kafka, or any other specific transport (`18-worker-model.md:88` — "A Worker does not even know the concept of a client").

#### Scenario: ExecutionChannel trait is public and lives outside adapters

- GIVEN `runtime-worker`'s public API
- WHEN `ExecutionChannel` is looked up
- THEN it is a trait reachable from outside the crate
- AND its definition lives outside `src/adapters/`

#### Scenario: ExecutionChannel exposes exactly one emit capability

- GIVEN the `ExecutionChannel` trait definition
- WHEN its capabilities are enumerated
- THEN there is exactly one, accepting a single `ExecutionEvent` value

#### Scenario: ExecutionChannel signature names no transport or async-runtime type

- GIVEN the `ExecutionChannel` trait's `emit` signature
- WHEN its parameter and return types are inspected
- THEN none names a `tonic::`, `prost::`, or `tokio::` path

### Requirement: ExecutionContext Is Immutable Data With No Channel And No Cancellation Field

`ExecutionContext` MUST be plain immutable data: once constructed, none of its fields are mutable, and it MUST NOT contain interior mutability (e.g. `Cell`, `RefCell`, `Mutex`) that would block a derived `Clone` implementation. `ExecutionContext` MUST NOT contain a field of an `ExecutionChannel` (or any channel/sender) type, and MUST NOT contain a field carrying a cancellation signal (a cancellation token, flag, or equivalent) — per `worker.proto:68` and this change's Decision #3, cancellation and the channel each arrive as separate port parameters, never as `ExecutionContext` fields. `ExecutionContext` MUST be trivially constructible — via a public constructor or public fields — inside a unit test, with no async runtime and no transport dependency. `ExecutionContext` MUST also carry a `WorkerCapability` field — a `runtime-worker`-local newtype shaped like `ContentHash` (`new(impl Into<String>)` plus a read accessor), not a bare `String` — naming the requested behavior. This field is immutable like every other field, is exposed via a public accessor, and is mandatory: `ExecutionContext::new()` MUST require it as a constructor argument, with no default and no optional-field escape hatch.
(Previously: `new()` took 7 arguments and enumerated no `WorkerCapability` field or accessor.)

#### Scenario: ExecutionContext derives or implements Clone

- GIVEN the `ExecutionContext` type definition
- WHEN its derive list or trait impls are inspected
- THEN `Clone` is implemented for it

#### Scenario: ExecutionContext carries no channel field

- GIVEN the `ExecutionContext` type definition
- WHEN its fields are enumerated
- THEN none is of an `ExecutionChannel` type, a channel type, or a sender type

#### Scenario: ExecutionContext carries no cancellation field

- GIVEN the `ExecutionContext` type definition
- WHEN its fields are enumerated
- THEN none carries a cancellation token, cancellation flag, or equivalent signal

#### Scenario: ExecutionContext is constructible in a unit test without an async runtime or transport

- GIVEN a test module inside `runtime-worker`
- WHEN it constructs an `ExecutionContext` value using only public constructors or public fields
- THEN the test compiles and passes without starting an async runtime (no `#[tokio::test]`, no `tokio::runtime::Runtime`) and without depending on any transport type

#### Scenario: ExecutionContext::new() takes WorkerCapability as a required 8th argument

- GIVEN `ExecutionContext::new`'s signature
- WHEN its parameters are counted
- THEN there are 8, one of them a `WorkerCapability` value
- AND a call site omitting it does not compile

#### Scenario: WorkerCapability is readable via a public accessor

- GIVEN a constructed `ExecutionContext` value
- WHEN its capability accessor is called
- THEN it returns the exact `WorkerCapability` value supplied at construction, unchanged

### Requirement: ExecutionEvent Is A Closed Six-Arm Enum

`ExecutionEvent` MUST be a Rust enum with exactly six variants — `OutputChunk`, `Progress`, `Warning`, `CheckpointCreated`, `MetricsSnapshot`, `EndOfStream` — corresponding one-to-one to the six arms of the frozen wire contract's `ExecutionEvent` oneof. `ExecutionEvent` MUST NOT gain a seventh variant and MUST NOT collapse or merge any of the six.

#### Scenario: ExecutionEvent has exactly six variants

- GIVEN the `ExecutionEvent` type definition
- WHEN its variants are enumerated
- THEN there are exactly six: `OutputChunk`, `Progress`, `Warning`, `CheckpointCreated`, `MetricsSnapshot`, `EndOfStream`

#### Scenario: Each variant corresponds to one wire arm

- GIVEN each of `ExecutionEvent`'s six variants
- WHEN it is compared against `worker.proto`'s `ExecutionEvent.arm` oneof
- THEN it corresponds to exactly one wire arm of the same name/purpose, with no wire arm left unmapped and no domain variant left unmapped

### Requirement: ExecutionPhase Has Exactly Six States And No Placeholder

`ExecutionPhase` MUST be a Rust enum with exactly six variants — `Received`, `Prepared`, `Running`, `Completed`, `Failed`, `Cancelled` — corresponding to six of the frozen wire contract's seven `ExecutionPhase` values. The wire's `EXECUTION_PHASE_UNSPECIFIED` proto3 tag-zero obligation MUST NOT be modeled as a domain variant. `ExecutionPhase` MUST NOT define any variant equivalent to `Unspecified` or `Unknown`, and MUST NOT implement `Default`.

#### Scenario: ExecutionPhase has exactly six variants

- GIVEN the `ExecutionPhase` type definition
- WHEN its variants are enumerated
- THEN there are exactly six: `Received`, `Prepared`, `Running`, `Completed`, `Failed`, `Cancelled`

#### Scenario: ExecutionPhase has no Unspecified-equivalent variant

- GIVEN the `ExecutionPhase` type definition
- WHEN its variants are enumerated
- THEN none is named or behaves as `Unspecified`, `Unknown`, or any other default/placeholder state

#### Scenario: ExecutionPhase does not implement Default

- GIVEN the `ExecutionPhase` type definition
- WHEN its trait implementations are inspected
- THEN `Default` is not implemented for it

### Requirement: Generated Transport Code Stays Private

`runtime-worker` MUST confine all `prost`/`tonic` generated code (including anything produced by `include_proto!`) to a non-`pub` module tree rooted at `src/adapters/`, MUST NOT re-export any part of that tree via `pub use`, MUST set the `private_interfaces` lint to `deny` (not the default `warn`), and MUST NOT expose any `tonic::`, `prost::`, or `tokio::` path in its public API — including the new public domain surface (`WorkerService`, `ExecutionChannel`, and the domain types) introduced by this change.

#### Scenario: Generated code module is not public

- GIVEN `runtime-worker/src/adapters/mod.rs` and every descendant module housing generated code
- WHEN the module declarations from `lib.rs` down to the generated module are inspected
- THEN none carries the `pub` keyword

#### Scenario: No re-export escapes the private module

- GIVEN every source file in `runtime-worker`
- WHEN the crate is searched for `pub use` statements
- THEN none names `adapters`, any of its submodules, or any item defined inside them

#### Scenario: private_interfaces lint is denied

- GIVEN `runtime-worker`'s lint configuration (crate attribute or `Cargo.toml` lints table)
- WHEN the level set for `private_interfaces` is read
- THEN it is `deny`

#### Scenario: Public API carries no tonic/prost/tokio path

- GIVEN every item reachable from outside `runtime-worker` (its public API, including `WorkerService`, `ExecutionChannel`, and every domain type)
- WHEN each signature, field type, and trait bound is inspected
- THEN no `tonic::`, `prost::`, or `tokio::` path appears anywhere in it
