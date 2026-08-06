# Worker Runtime Specification

## Purpose

The Worker Runtime is the single component inside tibios-ray that drives the Worker Contract lifecycle for each execution and dispatches work to Capability Providers via the Capability Registry. It is the only place "Worker" may reappear as a concept after the gRPC boundary, and only as the thing it *drives* — never as the name of an internal unit. See `../tibios-core/docs/architecture/18-worker-model.md`.

## Requirements

### Requirement: Worker Runtime Owns the Execution Lifecycle

The Worker Runtime MUST drive the full Worker Contract lifecycle (Execution Context → Channel → Events → Report → Pulse, including cancellation) for every execution received from the gRPC Worker layer, per `18-worker-model.md`.

#### Scenario: Execution completes successfully

- GIVEN an Execution Context accepted by the Worker Runtime
- WHEN the dispatched Capability Provider finishes work
- THEN the Worker Runtime emits Events and a final Report through the Channel

#### Scenario: Cancellation propagates to the active execution

- GIVEN an execution in progress
- WHEN a cancellation signal (Pulse) is received
- THEN the Worker Runtime propagates cancellation to the dispatched Capability Provider and closes the Channel per the Worker Contract

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
