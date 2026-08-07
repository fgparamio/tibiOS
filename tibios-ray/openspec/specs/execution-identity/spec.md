# Execution Identity Specification

## Purpose

Identity and carried-context vocabulary for one execution, per
`18-worker-model.md`'s Execution Context. `WorkloadId`/`AllocationId` are
proof-carrying identity types, per design decision D3 already established
for `ObjectId`/`ObjectVersion`/`ContentHash` (`execution/ids.py`). `SecurityContext`,
`ObservabilityContext`, and `execution_parameters` are carried by the
Execution Context but MUST NOT be interpreted by a Worker to make
authorization or dispatch decisions (`18-worker-model.md:136`): a Worker
that rejects or routes work based on their content has made an
authorization decision, which is forbidden.

## Requirements

### Requirement: WorkloadId And AllocationId Are Proof-Carrying Identity Types

`WorkloadId` and `AllocationId` MUST be frozen, slotted dataclasses wrapping
a `str` value — never `NewType[str]` aliases — per D3: a `NewType` is a
no-op at runtime, so a plain string could impersonate an identifier.

#### Scenario: WorkloadId and AllocationId are type-distinct from raw strings

- GIVEN a raw string value
- WHEN it is compared to or substituted for a `WorkloadId` or `AllocationId`
- THEN the type checker rejects the substitution and no implicit conversion occurs

#### Scenario: Equal values produce equal identities

- GIVEN two `WorkloadId` instances constructed from the same string value
- WHEN they are compared for equality
- THEN they are equal, per dataclass value semantics

### Requirement: SecurityContext Is Carried, Never Interpreted

`SecurityContext(tenant_id, principal_id, grant_scope)` MUST be threaded
through the Execution Context unchanged. The Worker Runtime and every
Capability Provider MUST NOT branch dispatch, acceptance, or rejection
decisions on any `SecurityContext` field.

#### Scenario: Dispatch outcome is independent of SecurityContext content

- GIVEN two Execution Contexts requesting the same capability but carrying different `SecurityContext` values (including an empty `tenant_id` or `grant_scope`)
- WHEN the Worker Runtime dispatches each
- THEN both are dispatched identically to the same Capability Provider — no rejection or routing difference is caused by `SecurityContext` content

### Requirement: ObservabilityContext Is Carried, Never Interpreted

`ObservabilityContext(trace_id, span_id)` MUST be threaded through
unchanged and MAY be propagated into observability outputs (e.g. an
`ExecutionReport.trace_id`), but MUST NOT influence dispatch or
control-flow decisions.

#### Scenario: Observability values pass through without altering execution

- GIVEN two Execution Contexts identical except for `ObservabilityContext`
- WHEN each is executed
- THEN both follow the same execution path; only the propagated trace/span identifiers differ in the output

### Requirement: execution_parameters Is Carried Opaque Data

`execution_parameters: Mapping[str, str]` MUST be passed to the dispatched
Capability Provider unchanged. The Worker Runtime MUST NOT parse, validate,
or dispatch on its keys or values — dispatch is by requested capability
only.

#### Scenario: Dispatch target is unaffected by execution_parameters content

- GIVEN two Execution Contexts requesting the same capability with different `execution_parameters` maps (including an empty map)
- WHEN the Worker Runtime dispatches each
- THEN both resolve to the same Capability Provider; only the map contents reaching the provider differ

### Requirement: AllocationContract Carries Exactly max_execution_duration

`AllocationContract` MUST carry exactly one field, `max_execution_duration: timedelta`. tibios-ray MUST NOT redefine `AllocationContract`'s shape: per `02-project-structure.md`'s Ownership Boundaries table (`Allocation → AllocationContract → Worker`), the producer owns the contract, and a consumer MUST NOT invent fields it cannot reconstruct from what the producer actually sends. This mirrors `runtime-allocation`'s own shape, documented there as "intentionally partial, pending `15-allocation-model.md`'s own future change to add the remaining documented facets (exclusive/shared, renewable lease, preemptible, migration allowed, checkpoint required)."

#### Scenario: AllocationContract has no fields beyond max_execution_duration

- GIVEN the `AllocationContract` domain type
- WHEN its fields are enumerated
- THEN `max_execution_duration` is the only field present
