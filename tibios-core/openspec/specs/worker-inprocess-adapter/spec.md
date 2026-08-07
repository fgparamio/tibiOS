# Worker In-Process Adapter Specification

## Purpose

`worker-inprocess-adapter` is the first concrete, real implementation of the Worker domain's Inbound Port (`WorkerService`) and its Outbound `ExecutionChannel`, owned by `runtime` — never `runtime-worker`, which the `worker-inbound-port` spec forbids from naming any `tokio::` path. It proves the port by running it: real awaits, a real `tokio::sync::mpsc` channel, and the obligations (O1-O4) upheld under real concurrency, not simulated by a test double.

## Requirements

### Requirement: The In-Process Worker Performs Real Async Work Through A Real Channel

The in-process `WorkerService` implementation MUST perform real asynchronous work when executing — it MUST `.await` at least one suspension point per execution — and MUST publish emitted `ExecutionEvent`s through a real `tokio::sync::mpsc`-backed `ExecutionChannel`, never an in-memory test double or a channel that resolves synchronously. It MUST NOT special-case its behavior for a test harness.

#### Scenario: An execution's events cross a real mpsc channel

- GIVEN one submitted execution
- WHEN the in-process `WorkerService` runs it using the mpsc-backed `ExecutionChannel`
- THEN the events published during `execute` are received on the channel's `Receiver` half, having crossed a real `tokio::sync::mpsc` boundary
- AND the `execute` call suspends at least once before returning

### Requirement: The In-Process Worker Is Exposed Only Through A Factory Function Returning impl WorkerService

The in-process worker's concrete type MUST NOT be a public export any caller names directly. `runtime` MUST expose it exclusively through a factory function whose return type is `impl WorkerService`, so no binding site can write down the concrete type or the transport it implies — the same shape a future gRPC worker is forced to reuse.

#### Scenario: The factory function's return type hides the concrete implementation

- GIVEN the module exposing the in-process worker
- WHEN its public API is inspected
- THEN the only way to obtain a worker instance is a function returning `impl WorkerService`
- AND no public item exposes the concrete worker struct's name

### Requirement: The In-Process Worker Upholds Obligations O1-O4 Under Real Concurrency

The in-process `WorkerService` MUST uphold, through real (not simulated) concurrency: O1 — register `workload_id` before `execute`'s first suspension point; O2 — deregister `workload_id` before `execute` returns, on every path (success, failure, cancellation); O3 — `cancel` and `pulse` return `Err(WorkerError::UnknownWorkload)` for a `workload_id` with no in-flight registration; O4 — a second `execute` call for an already in-flight `workload_id` returns `Err(WorkerError::DuplicateWorkload)` without starting a second execution. These four obligations MUST be verified by running the in-process worker through the shared O1-O4 conformance harness (`worker-inbound-port` spec), not by maintaining a bespoke, worker-specific test suite. The in-process worker's existing test suite MUST NOT be deleted: it stays in place as supplementary coverage, asserting behavioral detail (phase transitions, event-sequence content) the shared harness deliberately does not assert, even where a given test's obligation-level assertion now overlaps with something the harness also checks.

(Previously: O1-O4 were verified only by this worker's own dedicated test suite; no shared harness existed, so nothing generalized the assertions across implementations.)

#### Scenario: A cancel issued immediately after execute is never lost (O1)

- GIVEN an execution just submitted via `execute`
- WHEN `cancel` is called for the same `workload_id` immediately, before `execute` has yielded control back
- THEN the cancellation request is accepted (`Ok(CancelAck)`), never lost to a registration race

#### Scenario: Deregistration happens on every completion path (O2)

- GIVEN an execution that completes, one that fails, and one that is cancelled
- WHEN each finishes and `execute` returns
- THEN `pulse` for that `workload_id` afterward returns `Err(WorkerError::UnknownWorkload)` in all three cases

#### Scenario: Unknown workloads are rejected by cancel and pulse (O3)

- GIVEN a `workload_id` with no in-flight registration
- WHEN `cancel` or `pulse` is called with it
- THEN both return `Err(WorkerError::UnknownWorkload)`

#### Scenario: A duplicate in-flight execute is rejected without starting a second run (O4)

- GIVEN a `workload_id` already registered by an in-flight `execute` call
- WHEN `execute` is called again with the same `workload_id`
- THEN it returns `Err(WorkerError::DuplicateWorkload)` immediately, and no second execution starts

#### Scenario: O1-O4 are verified via the shared harness, not a bespoke suite

- GIVEN the shared O1-O4 conformance harness
- WHEN the in-process worker's obligations are verified
- THEN this is done by invoking the shared harness against it, not by maintaining a separate, worker-specific copy of the four obligation checks

#### Scenario: The in-process worker's existing tests remain as supplementary coverage, not deleted or duplicated

- GIVEN the in-process worker's pre-existing test suite and the shared harness now also exercising it
- WHEN both are run after this change
- THEN every pre-existing test still exists and still passes, asserting phase-transition and event-sequence detail the harness does not, even for the tests whose obligation-level assertion now overlaps with the harness's own coverage
