# Worker Wire Contract Specification

## Purpose

Defines the proto3 wire projection of the Worker Contract (`18-worker-model.md`): RPC shape, message set, and the lossless bidirectional mapping to `tibios_ray.execution` Python types. The `.proto` is normative over any single-language implementation, including Ray's current one.

## Requirements

### Requirement: RPC Interface Is Closed to Three Methods

The service MUST expose exactly three RPCs: `SubmitJob` (unary request, server-streaming response), `Cancel`, `Pulse`. No other RPC MAY exist; reports MUST NOT ride a fourth RPC.

#### Scenario: Service surface has three methods

- GIVEN the compiled `.proto` service
- WHEN its RPCs are enumerated
- THEN exactly `SubmitJob`, `Cancel`, `Pulse` exist
- AND `SubmitJob` alone returns a stream

### Requirement: WorkloadId Is the Sole Correlation Key

`Cancel` and `Pulse` requests MUST carry only a `WorkloadId`. No message in the contract MAY encode a compound ID, attempt number, or retry count.

#### Scenario: Cancel and Pulse carry no retry metadata

- GIVEN the `Cancel` and `Pulse` request messages
- WHEN their fields are enumerated
- THEN each has exactly one field, a `WorkloadId`
- AND no attempt/retry/compound-key field exists anywhere in the contract

### Requirement: ExecutionEvent Is a Closed Six-Arm Union

`ExecutionEvent` MUST be a oneof with exactly six arms: `OutputChunk`, `Progress`, `Warning`, `CheckpointCreated`, `MetricsSnapshot`, `EndOfStream`. No implementation MAY add a seventh arm.

#### Scenario: Oneof arm count is fixed at six

- GIVEN the `ExecutionEvent` message
- WHEN its oneof arms are counted
- THEN exactly 6 exist, matching the names above
- AND neither `ExecutionReport` nor `ExecutionPulse` is among them

### Requirement: Response Stream Carries Both Events and a Terminal Report

The `SubmitJob` response stream MUST be able to carry both `ExecutionEvent` messages and a terminal `ExecutionReport`, and consumers MUST distinguish which arrived on each item unambiguously. (Provisional: exact envelope shape/name is decided by `sdd-design`; this requirement holds under any resolution.)

#### Scenario: Consumer discriminates event vs. report

- GIVEN a `SubmitJob` response stream
- WHEN a stream item arrives
- THEN the consumer determines without ambiguity whether it is an `ExecutionEvent` or the terminal `ExecutionReport`
- AND the report, when present, terminates the stream

### Requirement: ExecutionContext Reflects the Full Doc-Mandated Set

`ExecutionContext` MUST define fields projecting Workload, Allocation, Security Context, Observability Context, and Execution Parameters per `18-worker-model.md`, regardless of which fields `tibios_ray.execution.context` currently implements.

#### Scenario: Proto is not limited to Ray's current subset

- GIVEN `ExecutionContext` in the `.proto`
- WHEN compared to `context.py` (capability, allocation_contract, dependencies only)
- THEN the proto additionally defines Security Context and Observability Context fields
- AND their absence in `tibios_ray` today does not shrink the proto's required field set

### Requirement: AllocationId Is a Distinct Primitive, Never ObjectId

`identity.proto` MUST define a distinct `AllocationId` message, separate from `ObjectId`. `ExecutionContext.allocation_id` MUST be typed `AllocationId`, never `ObjectId`. The two MUST NOT be conflated: `02-project-structure.md:116` and `15-allocation-model.md:41` both name `AllocationId` as its own Runtime Primitive — an Allocation carries mutable Runtime State and, per `13-object-model.md`, cannot be content-addressed, which is exactly why it cannot reuse `ObjectId`.

#### Scenario: AllocationId exists as its own message

- GIVEN `identity.proto`
- WHEN its messages are enumerated
- THEN a distinct `AllocationId` message exists, separate from `ObjectId`

#### Scenario: ExecutionContext.allocation_id is typed AllocationId

- GIVEN `ExecutionContext` in `worker.proto`
- WHEN the type of its `allocation_id` field is read
- THEN it is `tibios.primitives.v1.AllocationId`, never `tibios.primitives.v1.ObjectId`

### Requirement: Bidirectional, Lossless Type Mapping

Every public type in `tibios_ray.execution.__all__` MUST map to exactly one proto message or oneof arm, except `ExecutionChannel` and `CancellationToken` (process-local, no wire form). Every proto message MUST map to exactly one such Python type, or be recorded as a normative addition not yet implemented on the Ray side.

#### Scenario: Every Python type resolves in the table

- GIVEN the mapping table below
- WHEN each `tibios_ray.execution.__all__` entry is looked up
- THEN it appears exactly once, as a proto counterpart or a declared exception
- AND none is missing or duplicated

#### Scenario: Proto-only additions are recorded, not silent

- GIVEN a proto message with no current Python counterpart (`WorkloadId`; `AllocationId`; Security/Observability Context fields; `ExecutionPhase.CANCELLED`)
- WHEN the mapping table is reviewed
- THEN the gap is explicitly recorded as a Ray-side follow-up

### Requirement: Every Message Cites the Architecture Document That Defines It

Every proto message and enum MUST carry a comment citing the architecture document section that actually defines the concept it projects. In this change there are exactly two valid citation targets, chosen by what the message *is*, not by which `.proto` file it lives in: Runtime Primitives (identity wrappers such as `ObjectId`, `ObjectVersion`, `ContentHash`, `AllocationId`) MUST cite `02-project-structure.md` (the section enumerating Runtime Primitives), because that is the document that names them; Worker Contract messages (everything in `worker.proto`, plus `WorkloadId`, whose role as the sole correlation key is itself Worker Contract language) MUST cite `18-worker-model.md`. No message MAY cite a document that does not name or define it — a citation to `18-worker-model.md` for a message that document never mentions does not satisfy this requirement.

#### Scenario: Citation is present and checkable

- GIVEN any message in the `.proto`
- WHEN its leading comment is read
- THEN it names a section of `02-project-structure.md` (if the message is a Runtime Primitive) or `18-worker-model.md` (if the message is Worker Contract language)
- AND the cited document actually names or defines the concept the message projects

## Mapping Table (normative)

| Python (`tibios_ray.execution`) | Proto | Note |
|---|---|---|
| `ObjectId`, `ContentHash` | same names | identity wrappers |
| `ObjectVersion` | `ObjectVersion` | proto `value` is `string`; Python `ObjectVersion` is `int` — an intentional widening (no architecture doc mandates the wire scalar type), not a bug |
| `ResolvedModelRef` | `ResolvedModelRef` | |
| `AllocationContract` | `AllocationContract` | |
| `ExecutionContext` | `ExecutionContext` | proto superset: adds `workload_id`, `allocation_id`, `security_context`, `observability_context`, `execution_parameters` — none present in `context.py` today; each is a Ray-side follow-up, not silently added |
| `OutputChunk`, `Progress`, `Warning`, `CheckpointCreated`, `MetricsSnapshot`, `EndOfStream` | `ExecutionEvent` oneof arms | 1:1, exactly 6 |
| `ExecutionReport` | `ExecutionReport` | |
| `ExecutionPulse` | `ExecutionPulse` | |
| `ExecutionPhase` | `ExecutionPhase` enum | proto adds `EXECUTION_PHASE_CANCELLED` (plus the mandatory proto3 `_UNSPECIFIED` zero value); `tibios_ray.execution.report.ExecutionPhase` has no `CANCELLED` counterpart today — Ray-side follow-up, justified by design.md D4 (a cancelled execution still produces a terminal Report) |
| `ExecutionChannel` | — (exception) | IS the response stream |
| `CancellationToken` | — (exception) | IS the `Cancel` RPC |
| — | `WorkloadId` | proto-only; no Python type yet — Ray-side follow-up |
| — | `AllocationId` | proto-only; a distinct Runtime Primitive (`02-project-structure.md:116`, `15-allocation-model.md:41`), never `ObjectId` — no Python type yet — Ray-side follow-up |
| — | `SecurityContext` | proto-only; no Python type yet — Ray-side follow-up (design.md D1 Consequences) |
| — | `ObservabilityContext` | proto-only; `ExecutionReport.trace_id` exists on the Python side today, but no `ExecutionContext`-carried counterpart — Ray-side follow-up (design.md D1 Consequences) |
| — | `CancelAck` | proto-only; named ack replacing an implicit `Empty`-shaped return — Ray-side follow-up |

## Notes

Resolved by `sdd-design` (`design.md`) and settled, not reopened here:
- Envelope: `ExecutionResponse { oneof payload { ExecutionEvent event = 1; ExecutionReport report = 2; } }` — exactly one `report`, always last on the stream, present even for cancelled executions (design.md D4).
- Trust/Session Context (`22-networking.md`) does NOT feed the Security Context field; a Worker is not a Runtime peer. `SecurityContext` is a narrow, execution-scoped, supplied-only authorization envelope (design.md D1).
- `.proto` file organization: two files split by ownership — `tibios/primitives/v1/identity.proto` (identity wrappers, no service) and `tibios/worker/v1/worker.proto` (the `WorkerExecution` service and all Worker-owned messages), exactly one intra-repo import edge (design.md D2).

Still open, no bearing on this spec: Rust codegen crate/module placement — resolved in `design.md` D3 (private `adapters/` module inside `runtime-worker`), but implemented only in the `worker-grpc-adapter` follow-up change.

Settled since the proposal and NOT reopened here: 3 RPCs, `WorkloadId`-only correlation, the 6-arm closed union.
