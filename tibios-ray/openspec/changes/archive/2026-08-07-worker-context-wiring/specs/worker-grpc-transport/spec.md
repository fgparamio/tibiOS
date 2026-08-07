# Worker gRPC Transport Specification

## Purpose

The `WorkerExecution` gRPC service surface tibios-ray exposes to
tibios-core, per `worker.proto`, plus the correlation discipline the wire
imposes: the only thing `Cancel`/`Pulse` ever receive is a `WorkloadId`,
so an in-flight registry keyed by it is the sole possible correlation
mechanism (inherited verbatim from tibios-core's `worker-inbound-port`
D11). Generated code and every `grpc`/`_pb2` import are isolated to one
package.

## Requirements

### Requirement: WorkerExecution Exposes Exactly Three RPCs

The `WorkerExecution` service MUST expose exactly `SubmitJob`, `Cancel`,
and `Pulse` — no fourth RPC.

#### Scenario: Service surface has exactly three RPCs

- GIVEN the generated `WorkerExecution` service stub
- WHEN its RPC methods are enumerated
- THEN exactly `SubmitJob`, `Cancel`, and `Pulse` are present

### Requirement: SubmitJob Streams Events Then Exactly One Terminal Report, Always Last

The `SubmitJob` response stream MUST carry zero or more `ExecutionEvent`-wrapped
messages followed by exactly one `ExecutionReport`-wrapped message as the
final message on the stream. This holds for cancelled executions too —
proto3 cannot enforce ordering structurally, so it is an explicit tested
requirement.

#### Scenario: Successful execution ends with the terminal report last

- GIVEN an accepted `SubmitJob` call
- WHEN the execution completes
- THEN the response stream's last message wraps the terminal `ExecutionReport`, and no message follows it

#### Scenario: Cancelled execution still ends with the terminal report last

- GIVEN an execution cancelled mid-flight via `Cancel`
- WHEN it reaches its final state
- THEN the response stream still emits a terminal report as the very last message — never omitted, never followed by further events

### Requirement: WorkloadId Is Registered Before The First Await (O1)

The `SubmitJob` handler MUST register the request's `WorkloadId` in the
in-flight registry synchronously, before its first `await`, so a `Cancel`
arriving immediately after is never lost.

#### Scenario: A Cancel issued immediately after SubmitJob is observed

- GIVEN a `SubmitJob` call for `WorkloadId` W, immediately followed by a `Cancel` call for W
- WHEN both are processed
- THEN the `Cancel` finds W already registered and is not rejected as unknown

### Requirement: WorkloadId Is Deregistered Before The Handler Returns (O2)

The `SubmitJob` handler MUST deregister its `WorkloadId` before returning
— on success, failure, and cancellation alike.

#### Scenario: Registry entry is removed after completion in every outcome

- GIVEN a `SubmitJob` call for `WorkloadId` W that completes successfully, fails, or is cancelled
- WHEN the handler returns
- THEN a subsequent `Pulse` for W is rejected as unknown, for all three outcomes

### Requirement: Cancel And Pulse For An Unknown WorkloadId Are Classified Errors (O3)

`Cancel` and `Pulse` for a `WorkloadId` with no in-flight execution MUST
raise a classified error and MUST NOT return a successful `CancelAck` or
`ExecutionPulse`.

#### Scenario: Cancel for an unregistered WorkloadId is rejected

- GIVEN a `WorkloadId` with no in-flight execution
- WHEN `Cancel` is called for it
- THEN it raises a classified error, never a `CancelAck`

#### Scenario: Pulse for an unregistered WorkloadId is rejected

- GIVEN a `WorkloadId` with no in-flight execution
- WHEN `Pulse` is called for it
- THEN it raises a classified error, never an `ExecutionPulse`

### Requirement: SubmitJob For An Already-Registered WorkloadId Is Rejected (O4)

`SubmitJob` for a `WorkloadId` already in the in-flight registry MUST be
rejected without starting a second execution, and MUST NOT affect the
first.

#### Scenario: Duplicate SubmitJob is rejected without disturbing the original

- GIVEN an in-flight execution registered under `WorkloadId` W
- WHEN a second `SubmitJob` arrives for W
- THEN it is rejected without starting a second execution, and the original execution proceeds unaffected

### Requirement: Generated Code Is Isolated To The Transport Package

No module outside the transport package MAY import `grpc` or any `_pb2`
symbol, checked recursively across the whole source tree.

#### Scenario: Recursive scan finds zero transport imports outside the package

- GIVEN the tibios-ray source tree outside `src/tibios_ray/transport/`
- WHEN scanned recursively for `grpc` or `_pb2` imports (plain imports and `importlib.import_module` string imports alike)
- THEN zero matches are found

### Requirement: Regenerating From ../proto Produces Byte-Identical Checked-In Code

Running the regeneration script against `../proto` MUST produce output
byte-identical to the checked-in generated code.

#### Scenario: Drift guard passes against the checked-in tree

- GIVEN the checked-in generated code and the current `../proto` contract
- WHEN the regeneration script is run and its output compared to the checked-in files
- THEN every regenerated file is byte-identical to its checked-in counterpart

### Requirement: Classified Errors Map To Fixed gRPC Status Codes

Every classified error this boundary raises MUST map to a fixed gRPC status code: a conversion rejection MUST map to `INVALID_ARGUMENT`; an unknown `WorkloadId` (O3) MUST map to `NOT_FOUND`; a duplicate `WorkloadId` (O4) MUST map to `ALREADY_EXISTS`. No classified error raised by this boundary MUST surface to the caller as `UNKNOWN`.

#### Scenario: Conversion rejection surfaces as INVALID_ARGUMENT

- GIVEN a `SubmitJob` call whose `ExecutionContext` fails conversion
- WHEN the RPC returns
- THEN its gRPC status is `INVALID_ARGUMENT`, never `UNKNOWN`

#### Scenario: Unknown WorkloadId surfaces as NOT_FOUND

- GIVEN a `Cancel` or `Pulse` call for an unregistered `WorkloadId`
- WHEN the RPC returns
- THEN its gRPC status is `NOT_FOUND`

#### Scenario: Duplicate SubmitJob surfaces as ALREADY_EXISTS

- GIVEN a `SubmitJob` call for a `WorkloadId` already registered
- WHEN the RPC returns
- THEN its gRPC status is `ALREADY_EXISTS`
