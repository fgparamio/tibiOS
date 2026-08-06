# Worker Wire Adapter Specification

## Purpose

`worker-wire-adapter` is the fallible conversion boundary living inside `runtime-worker`'s private `adapters::grpc::convert` module, between the generated `tonic`/`prost` wire types and their `runtime-primitives` domain counterparts. It does not redefine the wire shape — `worker-wire-contract` remains normative for that — this spec constrains only what the boundary conversion MUST do when handed data that does not conform to that shape.

This spec is scoped exactly to the boundary that exists today: the five identity-wrapper messages in `identity.proto` (`ObjectId`, `ObjectVersion`, `ContentHash`, `WorkloadId`, `AllocationId`) and their round-trip to `runtime-primitives`, plus exhaustive decoding of the two `oneof`s: `ExecutionEvent`'s six arms (`OutputChunk`, `Progress`, `Warning`, `CheckpointCreated`, `MetricsSnapshot`, `EndOfStream`) and `ExecutionResponse`'s two arms (`event`, `report`). Worker domain types (`ExecutionContext`, `ExecutionReport`, and the rest of `18-worker-model.md`'s domain model) now exist, defined by `worker-inbound-port` and the `runtime-worker` spec delta; every conversion this boundary performs targets those real domain types, never a private local mirror.

## Requirements

### Requirement: Identity Wrapper Messages Convert Losslessly And Reject Invalid Content

For each of the five identity-wrapper messages (`ObjectId`, `ObjectVersion`, `ContentHash`, `WorkloadId`, `AllocationId`), `TryFrom<proto::X> for` its `runtime-primitives` counterpart MUST succeed and reproduce the original identity when the message's payload is well-formed, and MUST fail — without panicking — when the payload cannot be parsed as its underlying representation: an invalid ULID string for `ObjectId`, `WorkloadId`, or `AllocationId`; text that is not a valid unsigned 64-bit integer for `ObjectVersion`. `ContentHash` wraps an arbitrary string with no invalid-content case of its own, so its only rejection path is the unset-field case covered by the next requirement.

#### Scenario: Well-formed identity value round-trips

- GIVEN a `runtime-primitives` identity value (e.g. a freshly generated `ObjectId`)
- WHEN it is converted to its wire message and back through `TryFrom`
- THEN the result equals the original value

#### Scenario: Invalid ULID text is rejected, not defaulted

- GIVEN a wire `ObjectId`, `WorkloadId`, or `AllocationId` message whose text field is not a valid ULID
- WHEN `TryFrom` is attempted
- THEN it returns `Err`, never panics, and never substitutes `Self::default()` or any other silent stand-in

#### Scenario: Invalid ObjectVersion text is rejected, not defaulted

- GIVEN a wire `ObjectVersion` message whose text field is not a valid unsigned 64-bit integer
- WHEN `TryFrom` is attempted
- THEN it returns `Err`, never panics, and never substitutes `ObjectVersion::initial()` or any other silent stand-in

### Requirement: Unset Required Message Fields Are Rejected

Where a `prost`-generated field is `Option`-wrapped because proto3 makes a message-typed field optional at the wire level, but the domain conversion has no meaningful empty/absent variant to substitute, `TryFrom` MUST reject a `None` value for that field rather than fabricating a placeholder identity to continue.

#### Scenario: Missing required identity field fails conversion

- GIVEN a wire message within this boundary's scope that carries a required identity-wrapper field left unset (`None`) at the wire level
- WHEN `TryFrom` is attempted on the containing message
- THEN it returns `Err` naming the missing field, and no placeholder identity is fabricated to let the conversion continue

### Requirement: ExecutionEvent's Six Arms Decode Exhaustively, Rejecting An Unset Oneof

`TryFrom` for `ExecutionEvent` MUST match all six wire arms (`OutputChunk`, `Progress`, `Warning`, `CheckpointCreated`, `MetricsSnapshot`, `EndOfStream`) exhaustively, and MUST reject the case where the `oneof` itself is unset (`None`) at the wire level rather than defaulting to any one arm.

#### Scenario: Each of the six arms converts to its counterpart

- GIVEN a wire `ExecutionEvent` with exactly one of its six arms populated
- WHEN `TryFrom` is attempted
- THEN it succeeds and produces the corresponding representation for that arm — this holds in turn for all six arms

#### Scenario: Unset ExecutionEvent oneof is rejected

- GIVEN a wire `ExecutionEvent` whose `oneof` field is unset (`None`)
- WHEN `TryFrom` is attempted
- THEN it returns `Err`, never panics, and never defaults to any of the six arms

### Requirement: ExecutionResponse's Two Arms Decode Exhaustively, Rejecting An Unset Oneof

`TryFrom` for `ExecutionResponse` MUST match both wire arms (`event`, `report`) exhaustively, and MUST reject the case where the `oneof` payload itself is unset (`None`) at the wire level rather than defaulting to either arm.

#### Scenario: Event arm converts

- GIVEN a wire `ExecutionResponse` with its `event` arm populated
- WHEN `TryFrom` is attempted
- THEN it succeeds and produces the corresponding event representation

#### Scenario: Report arm converts

- GIVEN a wire `ExecutionResponse` with its `report` arm populated
- WHEN `TryFrom` is attempted
- THEN it succeeds and produces the corresponding report representation

#### Scenario: Unset ExecutionResponse oneof is rejected

- GIVEN a wire `ExecutionResponse` whose `payload` oneof is unset (`None`)
- WHEN `TryFrom` is attempted
- THEN it returns `Err`, never panics, and never defaults to either arm

### Requirement: Worker Capability Field Is Rejected When Missing Or Empty

`TryFrom<proto::ExecutionContext> for` the domain `ExecutionContext` MUST reject a `worker_capability` field that is unset (`None`) or present but wrapping an empty string, returning `Err` rather than defaulting to an empty `WorkerCapability`, a placeholder value, or silently omitting the field — consistent with the existing pattern for an unset `payload` (`worker.proto:186-189`): absence is a protocol error the receiver MUST reject via `TryFrom`, never silently skip.

#### Scenario: Missing worker_capability is rejected

- GIVEN a wire `ExecutionContext` whose `worker_capability` field is unset (`None`)
- WHEN `TryFrom` is attempted
- THEN it returns `Err` naming the missing field, and no placeholder `WorkerCapability` is fabricated

#### Scenario: Empty worker_capability is rejected

- GIVEN a wire `ExecutionContext` whose `worker_capability` field is present but wraps an empty string
- WHEN `TryFrom` is attempted
- THEN it returns `Err`, and the empty value is neither accepted nor silently defaulted

#### Scenario: Well-formed worker_capability round-trips

- GIVEN a `WorkerCapability` domain value with a non-empty name (e.g. `chat.generate`)
- WHEN it is converted to its wire message and back through `TryFrom`
- THEN the result equals the original value

### Requirement: Every Conversion Rejection Is Classified Permanent, Never Silent Or Panicking

Every `Err` produced by a conversion in this boundary — an invalid ULID string, invalid `ObjectVersion` text, an unset required message field, a missing or empty `worker_capability` field, an unset `ExecutionEvent` oneof, or an unset `ExecutionResponse` oneof — MUST be represented by a conversion error type that implements `Classify` (`04-error-handling.md`) returning `ErrorClass::Permanent`, and MUST NOT be represented by a panic, an `unwrap()`/`expect()`, or a silently substituted default value.
(Previously: enumerated rejection cases did not include a missing or empty `worker_capability` field.)

#### Scenario: Every rejection variant classifies as Permanent

- GIVEN each distinct rejection case this spec defines (invalid ULID text, invalid `ObjectVersion` text, unset required field, missing or empty `worker_capability`, unset `ExecutionEvent` oneof, unset `ExecutionResponse` oneof)
- WHEN its `Classify::classify()` is called
- THEN it returns `ErrorClass::Permanent` in every case

#### Scenario: No conversion path panics

- GIVEN any malformed wire input covered by this spec
- WHEN the corresponding `TryFrom` is exercised
- THEN it returns `Err` and neither panics nor aborts the process

### Requirement: Conversions Target Real Domain Types, No Local Mirror Remains

Now that Worker domain types exist (`worker-inbound-port`), every `TryFrom` impl in this boundary MUST convert into the real `runtime-worker` domain type, not into a private local mirror type defined for lack of a real target. `convert.rs` MUST NOT define a local mirror enum or struct standing in for a domain type that now exists (e.g. no local counterpart to `ExecutionEvent` or `ExecutionResponse`'s payload), and MUST NOT define a private copy of `Classify` — it MUST implement the public `runtime_primitives::Classify` on `ConversionError` instead.

#### Scenario: No local mirror type stands in for a domain type

- GIVEN `crates/runtime-worker/src/adapters/grpc/convert.rs`
- WHEN its type definitions are inspected
- THEN it defines no local enum or struct that duplicates the shape of a domain type now defined by `runtime-worker` (`ExecutionEvent`, `ExecutionResponse`'s payload, or any other)

#### Scenario: No private Classify copy remains

- GIVEN `crates/runtime-worker/src/adapters/grpc/convert.rs`
- WHEN it is searched for a `trait Classify` declaration
- THEN none is found, and `ConversionError` implements `runtime_primitives::Classify` instead

#### Scenario: Every prior rejection scenario still passes against the real domain types

- GIVEN every rejection scenario this spec already defines (invalid identity text, unset required field, unset `ExecutionEvent` oneof, unset `ExecutionResponse` oneof)
- WHEN it is re-run after `convert.rs` is retargeted to the real domain types
- THEN it passes unchanged, producing a value of the real domain type on success and the same classified rejection on failure
