# Delta for Worker Wire Contract

## MODIFIED Requirements

### Requirement: ExecutionContext Reflects the Full Doc-Mandated Set

`ExecutionContext` MUST define fields projecting Workload, Allocation, Worker Capability, Security Context, Observability Context, and Execution Parameters per `18-worker-model.md`, regardless of which fields `tibios_ray.execution.context` currently implements. The Worker Capability field (`worker_capability`, proto field 8, message type `WorkerCapability { string value = 1; }`) MUST be additive: fields 1-7 MUST keep their existing tags and types unchanged, and none MAY be marked `reserved`. `worker_capability` MUST NOT be a bare `string` — it MUST be its own single-field message, consistent with every other typed `ExecutionContext` field.
(Previously: enumerated set had five members — Workload, Allocation, Security Context, Observability Context, Execution Parameters — with no Worker Capability field.)

#### Scenario: Proto is not limited to Ray's current subset

- GIVEN `ExecutionContext` in the `.proto`
- WHEN compared to `context.py` (capability, allocation_contract, dependencies only)
- THEN the proto additionally defines Security Context and Observability Context fields
- AND their absence in `tibios_ray` today does not shrink the proto's required field set

#### Scenario: Worker Capability closes a previously uncontracted gap

- GIVEN `context.py`'s `capability: str` field, invented locally today with no wire source
- WHEN `ExecutionContext.worker_capability` (field 8) is added
- THEN the wire contract defines the field `tibios_ray` already needed, without renaming Ray's concept

#### Scenario: Field 8 does not disturb fields 1-7

- GIVEN the pre-change `ExecutionContext` message (fields 1-7)
- WHEN `worker_capability` is added as field 8
- THEN fields 1-7 keep their original tags and types unchanged, and none is marked `reserved`

## Mapping Table Update (normative)

The Mapping Table row for `ExecutionContext` is modified, and one new row is added:

| Python (`tibios_ray.execution`) | Proto | Note |
|---|---|---|
| `ExecutionContext` | `ExecutionContext` | proto superset: adds `workload_id`, `allocation_id`, `security_context`, `observability_context`, `execution_parameters`, `worker_capability` — only `worker_capability` has a current Python counterpart; the rest remain Ray-side follow-ups. (Previously: row did not list `worker_capability`.) |
| `context.py`'s `capability: str` (uncontracted today) | `WorkerCapability` (`ExecutionContext.worker_capability`, field 8) | Wire-first: the contract now defines the field Ray already needed; Ray-side wiring to consume it is a tracked follow-up, not part of this change |
