# Delta for Worker Domain (runtime-worker)

## MODIFIED Requirements

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
