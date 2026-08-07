# Worker Runtime Specification

## Purpose

The Worker Runtime is the single component inside tibios-ray that drives the Worker Contract lifecycle for each execution and dispatches work to Capability Providers via the Capability Registry. It is the only place "Worker" may reappear as a concept after the gRPC boundary, and only as the thing it *drives* — never as the name of an internal unit. See `../tibios-core/docs/architecture/18-worker-model.md`.

## Requirements

### Requirement: Worker Runtime Owns the Execution Lifecycle

The Worker Runtime MUST drive the full Worker Contract lifecycle (Execution Context → Channel → Events → Report → Pulse, including cancellation) for every execution received from the gRPC Worker layer, per `18-worker-model.md`.

#### Scenario: Execution completes successfully

- GIVEN an Execution Context accepted by the Worker Runtime
- WHEN the dispatched Capability Provider finishes work
- THEN the Worker Runtime emits Events through the Channel during execution, emits a terminal `EndOfStream` event to signal the Channel is done, and returns the final Report directly from `execute()` — the Report is never itself sent through the Channel (`"Execution produces events. Completion produces a report."`, `18-worker-model.md`)

#### Scenario: Cancellation propagates to the active execution

- GIVEN an execution in progress, correlated by its `WorkloadId`
- WHEN a `Cancel` request for that `WorkloadId` is received (`Cancel(CancelRequest) returns (CancelAck)` — never `Pulse`)
- THEN the Worker Runtime propagates cancellation to the dispatched Capability Provider, emits final Events and a terminal `EndOfStream` on the Channel, and returns the Report per the Worker Contract — the `CancelAck` returned by `Cancel` means only "accepted", never "terminated"; completion is observed solely on the `SubmitJob` response stream, where the Report remains the final message in every outcome, including cancellation (D14)

#### Scenario: Pulse reports health without affecting execution state

- GIVEN an execution in progress
- WHEN a `Pulse` request for its `WorkloadId` is received
- THEN the gRPC transport reports a transport-observable phase (registered vs. task started) and health without altering execution lifecycle in any way — `Pulse` never triggers cancellation, completion, or any other state transition; the Worker Runtime itself publishes no phase transitions, so this is answered from the transport's in-flight registry, not from the Worker Runtime

### Requirement: Dispatch Only via Capability Registry

The Worker Runtime MUST resolve the target Capability Provider exclusively through the Capability Registry. It MUST NOT hold or import direct references to concrete Capability Provider implementations.

#### Scenario: Dispatch resolves through the registry

- GIVEN a requested capability (e.g. `chat.generate`)
- WHEN the Worker Runtime dispatches the execution
- THEN it queries the Capability Registry for a matching Capability Provider and invokes only the interface returned

#### Scenario: Unknown capability yields a Worker Contract error, not a crash

- GIVEN a requested capability with no registered Capability Provider
- WHEN the Worker Runtime attempts dispatch
- THEN it returns a Worker Contract–conformant error Report instead of raising an unhandled exception

### Requirement: "Worker" Naming Is Reserved to the Contract Entity

No class, module, protocol, or identifier inside tibios-ray, other than the entity implementing the gRPC Worker Contract itself, MAY be named "Worker", "Handler", or "Adapter" for a capability-specific unit; such units MUST be named "Capability Provider".

#### Scenario: Naming audit finds zero internal "Worker" usages

- GIVEN the tibios-ray Phase 1 source tree (`src/tibios_ray/runtime/`, `selection/`, `backends/`)
- WHEN searched for the identifier "Worker" outside the gRPC Worker Contract entity
- THEN zero matches are found
