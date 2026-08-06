# Worker Wire Adapter Specification

## Purpose

`worker-wire-adapter` is the fallible conversion boundary living inside `runtime-worker`'s private `adapters::grpc::convert` module, between the generated `tonic`/`prost` wire types and their `runtime-primitives` domain counterparts. It does not redefine the wire shape — `worker-wire-contract` remains normative for that — this spec constrains only what the boundary conversion MUST do when handed data that does not conform to that shape.

This spec is scoped exactly to the boundary that exists today: the five identity-wrapper messages in `identity.proto` (`ObjectId`, `ObjectVersion`, `ContentHash`, `WorkloadId`, `AllocationId`) and their round-trip to `runtime-primitives`, plus exhaustive decoding of the two `oneof`s: `ExecutionEvent`'s six arms (`OutputChunk`, `Progress`, `Warning`, `CheckpointCreated`, `MetricsSnapshot`, `EndOfStream`) and `ExecutionResponse`'s two arms (`event`, `report`). Worker domain types (`ExecutionContext`, `ExecutionReport`, and the rest of `18-worker-model.md`'s domain model) are explicitly out of scope — they do not exist yet and are not converted by this boundary.

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

### Requirement: Every Conversion Rejection Is Classified Permanent, Never Silent Or Panicking

Every `Err` produced by a conversion in this boundary — an invalid ULID string, invalid `ObjectVersion` text, an unset required message field, an unset `ExecutionEvent` oneof, or an unset `ExecutionResponse` oneof — MUST be represented by a conversion error type that implements `Classify` (`04-error-handling.md`) returning `ErrorClass::Permanent`, and MUST NOT be represented by a panic, an `unwrap()`/`expect()`, or a silently substituted default value.

#### Scenario: Every rejection variant classifies as Permanent

- GIVEN each distinct rejection case this spec defines (invalid ULID text, invalid `ObjectVersion` text, unset required field, unset `ExecutionEvent` oneof, unset `ExecutionResponse` oneof)
- WHEN its `Classify::classify()` is called
- THEN it returns `ErrorClass::Permanent` in every case

#### Scenario: No conversion path panics

- GIVEN any malformed wire input covered by this spec
- WHEN the corresponding `TryFrom` is exercised
- THEN it returns `Err` and neither panics nor aborts the process
