# Delta for Worker Wire Adapter

## ADDED Requirements

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

## MODIFIED Requirements

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
