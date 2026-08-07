# Worker gRPC Client Adapter Specification

## Purpose

`worker-grpc-client-adapter` is `RayWorker`, the third concrete `WorkerService` implementation, living inside `runtime-worker`'s existing private `adapters::grpc` tree. It calls `tibios-ray` over gRPC (`SubmitJob`/`Cancel`/`Pulse`), reusing `worker-wire-adapter`'s conversions exclusively — it has no path to hand-roll its own wire↔domain translation.

## Requirements

### Requirement: RayWorker Is Exposed Only Through A Factory Function Returning impl WorkerService

`RayWorker`'s concrete type MUST NOT be a public export any caller names directly. `runtime-worker` MUST expose it exclusively through a factory function (taking at minimum an endpoint address) whose return type is `impl WorkerService`, mirroring the factory shape `worker-inprocess-adapter` and `worker-local-infer-adapter` already establish.

#### Scenario: The factory function's return type hides the concrete implementation

- GIVEN the module exposing `RayWorker`
- WHEN its public API is inspected
- THEN the only way to obtain an instance is a function returning `impl WorkerService`
- AND no public item exposes the concrete `RayWorker` struct's name

### Requirement: RayWorker Upholds Obligations O1-O4 Under Real Concurrency, Verified Via The Shared Harness Against An In-Process Fake Server

`RayWorker` MUST uphold O1-O4 (`worker-inbound-port` spec) when driven against an in-process fake `tibios.worker.v1.WorkerExecution` server — no live `tibios-ray` process required in CI. These obligations MUST be verified by invoking the shared O1-O4 conformance harness, not a bespoke `RayWorker`-specific suite.

#### Scenario: RayWorker passes all four obligations against the fake server

- GIVEN the shared O1-O4 harness and a `RayWorker` instance connected to an in-process fake `WorkerExecution` server
- WHEN the harness runs
- THEN all four obligations pass, using the same shared assertion logic as every other `WorkerService` implementation

### Requirement: Transport Failures Are Normalized Into WorkerError, Never Leaked As tonic::Status

Every transport-level failure `RayWorker` observes (connection refused, deadline exceeded, any `tonic::Status`) MUST be converted into `WorkerError`'s transport-failure variant before crossing `RayWorker`'s `WorkerService` boundary. No `tonic::Status`, `tonic::transport::Error`, or other transport-specific type MUST ever be constructible from, or reachable through, a value `RayWorker` returns.

#### Scenario: A connection failure surfaces as WorkerError, not tonic::Status

- GIVEN a `RayWorker` instance pointed at an unreachable endpoint
- WHEN `execute`, `cancel`, or `pulse` is called
- THEN it returns `Err(WorkerError::..)` and the returned value contains no `tonic::` type

### Requirement: SubmitJob's Streaming Response Frames Route To ExecutionChannel Or The Terminal Report

`RayWorker` MUST route each `ResponseFrame` received from `SubmitJob`'s server stream to `ExecutionChannel::emit` when it carries an event, and MUST treat a frame carrying a report as the terminal signal ending the stream — never emitting a report through the channel or an event as the terminal value.

#### Scenario: Event frames are emitted, the report frame ends the stream

- GIVEN a fake server that sends two event frames followed by one report frame
- WHEN `RayWorker::execute` runs against it
- THEN both events are published via `ExecutionChannel::emit`, in order, and the report becomes `execute`'s returned `ExecutionReport`
