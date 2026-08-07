# Worker Local Infer Adapter Specification

## Purpose

`worker-local-infer-adapter` is the second concrete, real implementation of the Worker domain's Inbound Port (`WorkerService`), and it covers the entire `runtime/src/worker/local_infer/` subtree: the synchronous engine port, the `DeterministicEngine` reference engine, `LocalInferWorker` itself, and the blocking boundary that connects them to the async executor. All of it is owned by `runtime` — the sole crate permitted an async-runtime dependency — as plain modules in the Composition Root. There is no separate crate and no new `runtime-worker` surface; `sdd-design` settled the proposal's open placement decision (D0) as **D0-b** for reasons recorded in `design.md` D4 (the future external inference dependency belongs where its consumer lives; Consumer-Owned Contracts puts an outbound port with its consuming domain; `runtime-worker`'s `adapters/` tree is structurally closed to it anyway).

This adapter is structurally different from `worker-inprocess-adapter`: instead of `.await`ing real asynchronous work directly, it runs a wholly synchronous, CPU-bound engine on a dedicated blocking thread (`tokio::task::spawn_blocking`) and writes every emitted event back across that boundary into a real, by-value `ExecutionChannel` via `Handle::block_on`. This proves the Golden Rule's async/sync boundary under genuine CPU-bound pressure, not just async pressure — the property `docs/architecture/05-async-concurrency.md:37` (amended by this change) now states as a hard requirement.

## Requirements

### Requirement: The Engine Port Is Wholly Synchronous, Std-Only, And Knows Nothing About The Worker Domain

`local_infer/engine/` MUST define an engine port (a trait) whose sole generation method is an ordinary synchronous function — not `async fn`, and not one returning a `Future`, an `impl Future`, or any other poll-driven type — callable from a plain thread with no async runtime present. This subtree MUST name no `tokio::` path and MUST import nothing from `runtime-worker`; it depends on nothing but `std`.

#### Scenario: The engine port's generation method is not async and returns no Future

- GIVEN the engine port trait defined in `local_infer/engine/`
- WHEN its generation method's signature is inspected
- THEN it is not declared `async fn` and does not return `Future`, `impl Future`, or an equivalent poll-driven type

#### Scenario: The engine port is callable with no async runtime present

- GIVEN a plain (non-`#[tokio::test]`) unit test
- WHEN it calls the engine port's generation method directly on a reference engine instance
- THEN the call runs to completion inside that test with no async runtime started

#### Scenario: A whole-subtree token scan finds no tokio:: path and no async/await keyword

- GIVEN every `.rs` file under `runtime/src/worker/local_infer/engine/`
- WHEN each non-comment line is scanned for the whole identifiers `tokio`, `async`, and `await`
- THEN none is found anywhere in the subtree

### Requirement: The Engine Produces Tokens And Stops When Told; All Policy Lives In The Adapter's Sink

The engine port's generation method MUST accept a `&mut dyn TokenSink` (not a generic type parameter, so the port stays dyn-compatible) and MUST treat that sink's returned verdict (continue or stop) as the only channel through which cancellation, deadlines, or channel closure reach it. The engine itself MUST carry no knowledge of `WorkloadId`, `ExecutionEvent`, `ExecutionChannel`, or cancellation — those concerns live exclusively in the adapter's `TokenSink` implementation, never in the engine.

#### Scenario: The engine stops immediately when the sink signals stop

- GIVEN a reference engine mid-generation, with tokens remaining before its natural limit
- WHEN its sink returns the stop verdict in response to a token
- THEN the engine produces no further token and returns its summary immediately

#### Scenario: The engine port trait names no Worker-domain type

- GIVEN the engine port trait and its supporting types (request, token, summary, error)
- WHEN their definitions are inspected
- THEN none names `WorkloadId`, `ExecutionEvent`, `ExecutionChannel`, or any other `runtime-worker` type

### Requirement: A Deterministic Reference Engine Proves The Port, Never Real Inference

`local_infer/engine/` MUST include exactly one reference implementation of the engine port (`DeterministicEngine`) that is deterministic — given the same request, it MUST produce the same sequence of output tokens on every run, with no dependency on wall-clock time, randomness, or environment state for its output content — and MUST perform no real inference: it MUST NOT load a model, perform a GPU or FFI call, or depend on `llama.cpp`, `llama_cpp`, `ggml`, or `candle`. It MUST NOT call `std::thread::sleep` or any equivalent wait; the CPU cost it stands in for MUST come from bounded, genuine computation (a spin loop), whose iteration count per token MUST be supplied by the caller rather than hardcoded. No engine-specific name (this reference engine's own name, or a future real backend's) MUST appear anywhere outside `local_infer/engine/` — including inside `local_infer/mod.rs` itself, which MUST obtain an engine only through a factory returning a type-erased handle (`impl TextGenerationEngine` or `Arc<dyn TextGenerationEngine>`), never by naming the concrete reference-engine type.

#### Scenario: The reference engine produces an identical output sequence across repeated runs

- GIVEN the reference engine constructed with the same request in two separate runs
- WHEN each run is driven to completion through the engine port
- THEN the sequence of output tokens produced is identical between the two runs

#### Scenario: The reference engine performs no real inference and never sleeps

- GIVEN the reference engine's implementation
- WHEN its source is inspected
- THEN it names neither `llama.cpp` nor `candle`, loads no model file, performs no GPU or FFI call, and calls no sleep or wait function

#### Scenario: The per-token spin cost is caller-configured, not hardcoded

- GIVEN two otherwise-identical requests differing only in a caller-supplied spin-iteration count
- WHEN each is driven to completion
- THEN the produced token content is unaffected by the spin count, while the count itself governs how much CPU work each token costs

#### Scenario: No engine-specific name appears outside the engine module, including in local_infer/mod.rs

- GIVEN the source tree under `runtime/src/worker/local_infer/` outside `local_infer/engine/`, and the rest of the workspace
- WHEN it is scanned for engine-specific names (the reference engine's own concrete name, `llama`, `llama_cpp`, `ggml`, `candle`)
- THEN none appears — `local_infer/mod.rs` obtains an engine only through a factory returning a type-erased handle

### Requirement: execute Registers Synchronously On The Async Side; The Registration Guard Never Crosses Into The Blocking Closure

`LocalInferWorker::execute`'s implementation MUST perform its O1/O4 registration synchronously, in the function body, before returning its future — identical in shape to `worker-inprocess-adapter`'s registration timing. The resulting registration guard MUST be held on the async side of the blocking boundary and MUST NOT be moved into the `spawn_blocking` closure; only a shared handle to the registry (not the guard itself) MUST cross into the closure. This is load-bearing, not stylistic: a `spawn_blocking` task cannot be aborted, so if the guard travelled with it, dropping `execute`'s returned future early would leave the registration alive until the blocking task finished on its own — violating O2 on the drop path.

#### Scenario: A duplicate in-flight execute is rejected before any blocking work is queued (O1/O4 timing)

- GIVEN a `workload_id` already registered by an in-flight `execute` call
- WHEN `execute` is called again with the same `workload_id`
- THEN it returns `Err(WorkerError::DuplicateWorkload)` synchronously, before any blocking task is queued

#### Scenario: Dropping execute's future deregisters immediately, even though the blocking task cannot be cancelled and may still be running

- GIVEN an in-flight local-infer execution whose blocking task is still running
- WHEN the `execute` future is dropped before that blocking task completes
- THEN the workload is deregistered immediately (a subsequent `pulse` for the same `workload_id` returns `Err(WorkerError::UnknownWorkload)`), independent of whether the blocking task is still executing to completion in the background

### Requirement: Engine Work Runs Inside spawn_blocking, Behind A Handle Captured On The Async Side

`execute`'s implementation MUST perform all engine work inside `tokio::task::spawn_blocking` and MUST capture `tokio::runtime::Handle::current()` on the calling (async) side, before entering that blocking closure — never from inside it. Every `ExecutionEvent` the engine's token sink produces MUST reach the channel via `handle.block_on(channel.emit(event))`, executed from within the blocking closure; this is the only place in the codebase `Handle::block_on` is legal, because a blocking-pool thread is not an asynchronous execution context. The by-value, `Send + 'static` `ExecutionChannel` parameter MUST be moved into the closure. The calling executor thread MUST remain free to make progress on other tasks for the entire duration of the blocking engine call.

#### Scenario: The executor keeps making progress while an execution runs (executor liveness)

- GIVEN a local-infer execution running with a large, deliberately slow per-token CPU cost, submitted on a runtime with exactly one worker thread alongside a separately spawned ticker task that repeatedly yields and increments a counter
- WHEN the execution runs to completion
- THEN the ticker's counter has advanced throughout the execution's duration, proving the single worker thread was never occupied running the engine inline

#### Scenario: Chunks emitted by the engine are received on a real channel

- GIVEN an execution running through `spawn_blocking`
- WHEN the engine produces its output chunks
- THEN each chunk is received on the channel's real receiving half, delivered via `Handle::block_on` from the blocking closure, not queued for later async delivery

#### Scenario: A bounded channel under backpressure completes without deadlock (boundary backpressure)

- GIVEN a bounded channel whose capacity is smaller than the number of chunks the engine will emit, with a concurrently spawned task draining it
- WHEN the execution runs to completion
- THEN every chunk is eventually delivered, `Handle::block_on(channel.emit(..))` parks the blocking thread against the full channel and resumes once drained, and `execute` returns a terminal `ExecutionReport` without panicking or hanging

### Requirement: A Panicking Engine Re-Panics On The Async Side, Never Swallowed Or Reclassified

If the engine (or the token sink built on it) panics while running inside the blocking closure, `execute`'s future MUST re-panic with the original payload once the blocking task's `JoinHandle` resolves — reproducing exactly what would have happened had the engine run inline. No `WorkerError` variant MUST be invented to represent an engine panic as an ordinary execution failure.

#### Scenario: An engine panic propagates to execute's caller unchanged

- GIVEN an engine implementation that panics during a call
- WHEN `execute` runs it and the panic occurs inside the blocking closure
- THEN `execute`'s future panics with the same payload once awaited, and no `Ok` or `Err(WorkerError)` value is produced for that call

### Requirement: Cancellation And The Duration Budget Cross The Blocking Boundary By Polling, Checked After Every Token And Before The First

Because the blocking thread cannot `.await` a cancellation signal and cannot itself be aborted, the adapter's token sink MUST poll for stop conditions rather than being signaled. After each token it successfully emits, the sink MUST check, in this order: (1) whether the channel has closed, (2) whether the execution should stop — true when `cancel` was accepted for this `workload_id`, and also true when the registration has been removed entirely (the future was dropped and nobody is waiting; a naive "is this workload cancelled" check that only handles the first case is insufficient), and (3) whether the deadline derived from `max_execution_duration` has passed. Each condition MUST select a distinct terminal outcome. The deadline MUST also be checked once before the first token is produced, and the instant used for that deadline MUST be captured before `spawn_blocking` is called, so that time spent queued on a saturated blocking pool counts against the budget.

#### Scenario: An explicit cancel stops the engine at the next token boundary

- GIVEN an in-flight local-infer execution
- WHEN `cancel` is accepted for its `workload_id`
- THEN the engine stops at the next token boundary and the execution reaches a `Cancelled` terminal phase

#### Scenario: An abandoned execution (future dropped, no cancel) also stops

- GIVEN an in-flight local-infer execution whose `execute` future is dropped without `cancel` ever being called
- WHEN the still-running blocking task next checks whether it should stop
- THEN it detects the abandonment (the registration is gone) and stops, exactly as if `cancel` had been called

#### Scenario: A channel closure is detected and reported distinctly from a cancellation

- GIVEN an in-flight local-infer execution whose channel's receiving half is dropped mid-run
- WHEN the next token is produced
- THEN the sink detects the closed channel before checking cancellation or the deadline, and the execution stops for that reason

#### Scenario: A zero-duration contract fails before the first token, even though the engine never gets a chance to overrun it

- GIVEN an execution with `max_execution_duration` set to zero
- WHEN it runs
- THEN it fails immediately with a `Failed` terminal phase, because the deadline check runs once before the first token is requested and the start instant was captured before the blocking task was ever queued

### Requirement: The Local Infer Worker Is Exposed Only Through A Factory Function Returning impl WorkerService

The local-infer worker's concrete type MUST NOT be a public export any caller names directly. `runtime` MUST expose it exclusively through a `local_infer_worker()` factory function whose return type is `impl WorkerService` — the same shape `in_process_worker()` already uses — so no binding site can write down the concrete type or the blocking mechanism it implies.

#### Scenario: The factory function's return type hides the concrete implementation

- GIVEN the module exposing the local-infer worker
- WHEN its public API is inspected
- THEN the only way to obtain a worker instance is a function returning `impl WorkerService`, and no public item exposes the concrete worker struct's name

### Requirement: The Local Infer Worker Upholds Obligations O1-O4 Under Real Concurrency, Verified Via The Shared Harness

The local-infer `WorkerService` implementation MUST uphold, through real (not simulated) concurrency, the same four obligations every `WorkerService` implementation upholds: O1 — register `workload_id` before `execute`'s first suspension point; O2 — deregister `workload_id` before `execute` returns, on every path (success, failure, cancellation); O3 — `cancel` and `pulse` return `Err(WorkerError::UnknownWorkload)` for a `workload_id` with no in-flight registration; O4 — a second `execute` call for an already in-flight `workload_id` returns `Err(WorkerError::DuplicateWorkload)` without starting a second execution. These four obligations MUST be verified by invoking the shared O1-O4 conformance harness (`worker-inbound-port` spec) against the local-infer worker, not by maintaining a bespoke, worker-specific O1-O4 test suite.

#### Scenario: A cancel issued immediately after execute is never lost (O1)

- GIVEN an execution just submitted via `execute`
- WHEN `cancel` is called for the same `workload_id` immediately, before the blocking task has had a chance to run
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
- WHEN the local-infer worker's obligations are verified
- THEN this is done by invoking the shared harness against it (directly, and again as one arm of `AnyWorker`), not by maintaining a separate, worker-specific copy of the four obligation checks
