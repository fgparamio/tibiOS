# Delta for Worker Runtime

## MODIFIED Requirements

### Requirement: Worker Runtime Owns the Execution Lifecycle

The Worker Runtime MUST drive the full Worker Contract lifecycle
(Execution Context → Channel → Events → Report → Pulse, including
cancellation) for every execution received from the gRPC Worker layer,
per `18-worker-model.md`.
(Previously: the cancellation scenario said a cancellation signal arrives
via Pulse. Against the frozen wire this is backwards — `Cancel(CancelRequest)
returns (CancelAck)` is the cancellation RPC; `Pulse(PulseRequest) returns
(ExecutionPulse)` is a Runtime-pulled health check, unrelated to
cancellation — `worker.proto:212-234`.)

#### Scenario: Execution completes successfully

- GIVEN an Execution Context accepted by the Worker Runtime
- WHEN the dispatched Capability Provider finishes work
- THEN the Worker Runtime emits Events through the Channel during execution, emits a terminal `EndOfStream` event to signal the Channel is done, and returns the final Report directly from `execute()` — the Report is never itself sent through the Channel (`"Execution produces events. Completion produces a report."`, `18-worker-model.md`)

#### Scenario: Cancellation propagates to the active execution

- GIVEN an execution in progress, correlated by its `WorkloadId`
- WHEN a `Cancel` request for that `WorkloadId` is received (`Cancel(CancelRequest) returns (CancelAck)` — never `Pulse`)
- THEN the Worker Runtime propagates cancellation to the dispatched Capability Provider, emits final Events and a terminal `EndOfStream` on the Channel, and returns the Report per the Worker Contract — the `CancelAck` returned by `Cancel` means only "accepted", never "terminated"; completion is observed solely on the `SubmitJob` response stream

#### Scenario: Pulse reports health without affecting execution state

- GIVEN an execution in progress
- WHEN a `Pulse` request for its `WorkloadId` is received
- THEN the gRPC transport reports a transport-observable phase (registered vs. task started) and health without altering execution lifecycle in any way — `Pulse` never triggers cancellation, completion, or any other state transition; the Worker Runtime itself publishes no phase transitions, so this is answered from the transport's in-flight registry, not from the Worker Runtime
