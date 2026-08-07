# Worker Wire Conversion Specification

## Purpose

The fallible boundary between generated gRPC wire messages and
`tibios_ray.execution` domain types, isolated inside the `transport`
package. This spec mirrors tibios-core's `worker-wire-adapter` spec's
rejection surface (reject-don't-guess), applied to the inbound direction
tibios-ray actually receives: `ExecutionContext`, `CancelRequest`,
`PulseRequest`, and the identity-wrapper messages nested inside them
(`ObjectId`, `ObjectVersion`, `ContentHash` via `ResolvedModelRef`;
`WorkloadId`, `AllocationId` directly). It also constrains the one
outbound invariant named in the proposal's success criteria: domain
`ExecutionPhase` MUST never map to `EXECUTION_PHASE_UNSPECIFIED`.

## Requirements

### Requirement: Identity Wrapper Messages Convert Wire-to-Domain, Rejecting Invalid Content

For each of the five identity-wrapper messages, converting a wire message
to its domain counterpart MUST succeed and reproduce the wire value when
well-formed, and MUST fail — raising a classified conversion error,
never panicking — when the payload cannot be parsed as its underlying
representation: an invalid ULID string for `ObjectId`, `WorkloadId`, or
`AllocationId`; text that is not a valid unsigned 64-bit integer for
`ObjectVersion` (wire `string` to domain `int`).

#### Scenario: Well-formed identity value converts successfully

- GIVEN a wire identity message with a well-formed payload
- WHEN it is converted to its domain counterpart
- THEN conversion succeeds and the domain value carries the same identity

#### Scenario: Invalid ULID text is rejected, not defaulted

- GIVEN a wire `ObjectId`, `WorkloadId`, or `AllocationId` message whose `value` is not a valid ULID
- WHEN conversion is attempted
- THEN it raises a classified conversion error and never substitutes a default identity

#### Scenario: Non-numeric ObjectVersion text is rejected, not defaulted

- GIVEN a wire `ObjectVersion` message whose `value` is not a valid unsigned 64-bit integer
- WHEN conversion is attempted
- THEN it raises a classified conversion error and never substitutes a default version

### Requirement: Unset Required Message Fields Are Rejected

Where a wire message field is optional at the wire level (proto3
message-typed fields) but the domain has no meaningful empty/absent
variant, conversion MUST reject an unset field rather than fabricating a
placeholder.

#### Scenario: Missing required identity field fails conversion

- GIVEN a wire `ExecutionContext`, `CancelRequest`, `PulseRequest`, or `ResolvedModelRef` with a required identity field unset
- WHEN conversion is attempted
- THEN it raises a classified conversion error naming the missing field, and no placeholder identity is fabricated

### Requirement: worker_capability Is Rejected When Missing Or Empty

Converting a wire `ExecutionContext` MUST reject a `worker_capability`
that is unset or wraps an empty string, rather than defaulting to an
empty capability string.

#### Scenario: Missing worker_capability is rejected

- GIVEN a wire `ExecutionContext` whose `worker_capability` is unset
- WHEN conversion is attempted
- THEN it raises a classified conversion error naming the missing field

#### Scenario: Empty worker_capability is rejected

- GIVEN a wire `ExecutionContext` whose `worker_capability.value` is an empty string
- WHEN conversion is attempted
- THEN it raises a classified conversion error; the empty value is neither accepted nor defaulted

### Requirement: Domain ExecutionPhase Never Maps To EXECUTION_PHASE_UNSPECIFIED

Converting a domain `ExecutionPhase` value to its wire enum counterpart
MUST exhaustively map every domain phase to a defined, non-zero wire
value; `EXECUTION_PHASE_UNSPECIFIED` MUST never be produced.

#### Scenario: Every domain phase maps to a defined wire phase

- GIVEN each value of the domain `ExecutionPhase` enum
- WHEN it is converted to its wire counterpart
- THEN the result is a defined `ExecutionPhase` wire value other than `EXECUTION_PHASE_UNSPECIFIED`, for every domain value

### Requirement: Every Conversion Rejection Is Classified Permanent, Never Silent Or Panicking

Every rejection this boundary produces — invalid ULID text, invalid
`ObjectVersion` text, an unset required field, a missing or empty
`worker_capability` — MUST be raised as a classified `Permanent` error and
MUST NOT be a panic, an unguarded exception, or a silently substituted
default.

#### Scenario: Every rejection variant classifies as Permanent

- GIVEN each distinct rejection case this spec defines
- WHEN its classification is inspected
- THEN it classifies as `Permanent` in every case

#### Scenario: No conversion path panics on malformed input

- GIVEN any malformed wire input covered by this spec
- WHEN the corresponding conversion is exercised
- THEN it raises the classified error and never crashes the process

### Requirement: Missing allocation_contract Is Rejected

Converting a wire `ExecutionContext` MUST reject an unset `allocation_contract`, never defaulting to an unenforced or synthesized maximum duration. `18-worker-model.md:56` requires the Worker to enforce the maximum duration, and a Worker with no contract can enforce nothing.

#### Scenario: Missing allocation_contract fails conversion

- GIVEN a wire `ExecutionContext` whose `allocation_contract` is unset
- WHEN conversion is attempted
- THEN it raises a classified conversion error naming the missing field, and no default `AllocationContract` is fabricated

### Requirement: A Negative Duration Is Rejected In Both Directions

Converting a `google.protobuf.Duration` to a domain `timedelta` MUST reject a negative value; converting a domain `timedelta` to a wire `Duration` MUST reject a negative value. Both directions apply wherever a `Duration` crosses the boundary, including `AllocationContract.max_execution_duration` and `ExecutionReport.duration`.

#### Scenario: Negative wire Duration is rejected on conversion to domain

- GIVEN a wire `Duration` message representing a negative value
- WHEN it is converted to a domain `timedelta`
- THEN it raises a classified conversion error and no negative or zero-substituted duration is produced

#### Scenario: Negative domain timedelta is rejected on conversion to wire

- GIVEN a domain `timedelta` value that is negative
- WHEN it is converted to a wire `Duration`
- THEN it raises a classified conversion error rather than emitting a `Duration` the peer would reject

### Requirement: dependencies Converts Order-Preservingly Without A Fabricated Key

Converting the wire `repeated ResolvedModelRef` MUST produce an ordered domain sequence preserving wire order. Conversion MUST NOT synthesize a key — positional, derived from `object_id`, or otherwise — for any dependency, since neither the wire nor `18-worker-model.md` names a role, label, or slot for one.

#### Scenario: Dependencies preserve wire order

- GIVEN a wire `ExecutionContext` with multiple `dependencies` entries in a specific order
- WHEN converted to the domain `ExecutionContext`
- THEN the domain `dependencies` sequence preserves that exact order

#### Scenario: No key is fabricated for a dependency

- GIVEN a converted domain `ExecutionContext`
- WHEN its `dependencies` are inspected
- THEN each entry is a `ResolvedModelRef` value with no synthesized key, name, or role attached by the conversion itself

### Requirement: Four Domain-To-Wire Fields Transform Rather Than Drop

Distinct from the drop list below, four domain fields reach the wire but
under a changed shape or default, never silently as-is: `OutputChunk.sequence`
is range-validated against the wire's unsigned 64-bit representation and
rejected — never truncated — outside `[0, 2**64)`; `Progress.message`
folds `None` to wire `""` (proto3 has no absent scalar); `CheckpointCreated.checkpoint_id`
wraps verbatim into the wire's `ObjectId`, with no ULID validation performed
at this boundary; and `ExecutionReport.failure` folds into wire `summary`,
with `failure is None` folding to `summary == ""`.

#### Scenario: The four transforming fields never silently drop or truncate

- GIVEN a domain event or report carrying `OutputChunk.sequence`, `Progress.message`, `CheckpointCreated.checkpoint_id`, or `ExecutionReport.failure`
- WHEN it is converted to its wire counterpart
- THEN the value reaches the wire under its documented transform — never dropped, and never silently truncated in the `OutputChunk.sequence` case

### Requirement: The Domain-To-Wire Drop List Is Closed And Enumerated

Domain fields with no wire counterpart (`ExecutionReport.resource_usage`, `ExecutionReport.metrics`, `ExecutionReport.logs`; `Warning.code`; `EndOfStream.reason`; `ExecutionPulse.detail`) MUST be an explicit, enumerated, tested list. A domain field newly added with no wire home MUST NOT be silently dropped — it MUST be added to this list or given a wire mapping before the conversion is considered complete.

#### Scenario: The set of dropped fields matches the documented list exactly

- GIVEN the domain types converted to their wire counterparts
- WHEN the set of fields with no wire mapping is computed
- THEN it equals exactly the documented drop list, no more and no fewer
