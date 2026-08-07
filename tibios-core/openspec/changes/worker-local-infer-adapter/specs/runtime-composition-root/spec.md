# Delta for Composition Root

> `sdd-design` settled the proposal's open D0 placement decision as D0-b: the entire local-infer engine subtree lives inside `runtime/src/worker/local_infer/`, in the Composition Root itself — not in a new crate, and not inside `runtime-worker`. There is therefore no new workspace crate, no new workspace member, and no change to the architecture guard's `EXPECTED_MEMBERS`, `ALLOWED`, or `EXTERNAL_ALLOWED` tables — the workspace stays at 16 members and `runtime` keeps its existing `&["tokio"]` external-dependency allowance. What replaces the crate-boundary proof that the engine subtree is tokio-free is source-token containment scanning, added to the guard below (design D12) without touching any existing table.

## MODIFIED Requirements

### Requirement: Runtime Wires One Real Execution End-To-End

`runtime`'s entry point MUST wire real execution end-to-end: it MUST construct a concrete `ExecutionChannel`, obtain a `WorkerService` implementation, submit one execution, drain the events emitted on the channel, and print the terminal `ExecutionReport`. With two structurally different concrete Worker implementations now present in the workspace, `main.rs` MUST select between them by calling an `any_worker(kind)` factory and naming only `AnyWorker` (via that factory's return) and a `WorkerKind` selection value — never a concrete Worker struct or any engine type. `WorkerKind` is a selection enum, not a worker type or a transport, and `02-project-structure.md:291` assigns naming an implementation selection to the Composition Root. It MUST NOT hand-wire `runtime-allocation`, `runtime-object`, or `runtime-scheduler` — those stay out of scope.
(Previously: with only one Worker implementation, `main.rs` bound it directly through `in_process_worker()`'s `impl WorkerService` return, and no `AnyWorker` or `WorkerKind` type existed.)

#### Scenario: cargo run -p runtime prints a terminal report

- GIVEN the wired `runtime` binary
- WHEN `cargo run -p runtime` is executed
- THEN it submits one execution, drains its emitted events, and prints a terminal `ExecutionReport`
- AND the process exits successfully

#### Scenario: main.rs names AnyWorker, never a concrete Worker struct

- GIVEN `runtime/src/main.rs`
- WHEN its source is inspected
- THEN it references `AnyWorker` and `WorkerKind` (via `any_worker(WorkerKind::…)`) as the only Worker-related items — neither `InProcessWorker`, `LocalInferWorker`, nor any concrete engine type appears anywhere in the file

## ADDED Requirements

### Requirement: AnyWorker Dispatches Eagerly To Each Concrete Worker, Never Through A Lazily-Evaluated Wrapper

`runtime`'s worker module MUST provide an `AnyWorker` enum with one variant per concrete `WorkerService` implementation in the workspace, implementing `WorkerService` itself via a `match` in each method that runs synchronously, in the method call itself, before any `async` block is entered — never `Box<dyn WorkerService>` (not object-safe) and never a lazily-evaluated wrapper such as an `async move { match .. }` block or an `Either`-based combinator that defers the match to first poll. This distinction is load-bearing, not stylistic: every concrete Worker performs its O1 registration synchronously inside `execute`'s own function body, not inside the future it returns; a dispatch layer that defers the match to first poll would defer that registration too, and a `cancel` issued between the outer `execute` call and the dispatch's first suspension point would then be wrongly answered `UnknownWorkload` — silently breaking an obligation the wrapped Worker itself upholds. Each matched arm's future MUST be produced via `Box::pin` (a single allocation per call, dependency-free), not `Either` or a hand-rolled combinator. `AnyWorker` MAY name the concrete Worker structs internally, inside the module that owns it; only `main.rs` is barred from naming them.

#### Scenario: AnyWorker forwards each capability to the wrapped Worker's own implementation

- GIVEN an `AnyWorker` value constructed with each of its available variants in turn
- WHEN `execute`, `cancel`, and `pulse` are called on it
- THEN the call is forwarded to the wrapped concrete Worker's own implementation, and the observable behavior matches calling that concrete Worker directly

#### Scenario: AnyWorker is not built on Box<dyn WorkerService>

- GIVEN `AnyWorker`'s definition
- WHEN its shape is inspected
- THEN it is an enum with a `match`-based `WorkerService` implementation, not a wrapper around `Box<dyn WorkerService>`

#### Scenario: A cancel issued between AnyWorker's execute call and its first suspension point is never lost

- GIVEN an `AnyWorker` value wrapping a concrete Worker, called via `execute`
- WHEN `cancel` is issued for the same `workload_id` immediately — before the dispatched future has reached its first suspension point
- THEN the cancellation is accepted (`Ok(CancelAck)`), proving registration happened in the eager match itself and not inside a deferred `async` block

#### Scenario: AnyWorker's dispatch is not built on a lazily-evaluated combinator

- GIVEN `AnyWorker`'s `execute`, `cancel`, and `pulse` implementations
- WHEN their source is inspected
- THEN each matches on `self` and calls the wrapped Worker's method directly, producing a `Pin<Box<dyn Future<..>>>` per arm, with no `async move` block wrapping the match and no `Either`-style combinator

### Requirement: The Architecture Guard Contains The Local-Infer Engine Subtree By Source-Token Scanning, With Zero Guard-Table Edits

Because the local-infer engine subtree is a module, not a separate crate, no `EXTERNAL_ALLOWED` row can prove it is free of an async runtime. The architecture guard (`runtime/tests/architecture_guard.rs`) MUST instead prove this by whole-identifier source scanning, skipping comment lines (the guard's existing convention), and MUST do so without adding, removing, or editing any entry in `EXPECTED_MEMBERS`, `ALLOWED`, or `EXTERNAL_ALLOWED`. Specifically, the guard MUST contain three scans: (1) the identifier `tokio` never appears anywhere under `runtime/src/worker/local_infer/engine/`; (2) the identifiers `async` and `await` never appear anywhere in that same subtree; (3) the identifiers `llama`, `llama_cpp`, `ggml`, and `candle` never appear anywhere under `crates/runtime-worker/src/` or `runtime/src/`, excluding `runtime/src/worker/local_infer/engine/` itself.

#### Scenario: The tokio-free scan passes over the engine subtree

- GIVEN every `.rs` file under `runtime/src/worker/local_infer/engine/`
- WHEN the guard's scan runs
- THEN it finds no occurrence of the whole identifier `tokio` outside comment lines

#### Scenario: The no-async-surface scan passes over the engine subtree

- GIVEN the same subtree
- WHEN the guard's scan runs
- THEN it finds no occurrence of the whole identifiers `async` or `await` outside comment lines

#### Scenario: The engine-name containment scan passes everywhere outside the engine subtree

- GIVEN every `.rs` file under `crates/runtime-worker/src/` and `runtime/src/`, excluding `runtime/src/worker/local_infer/engine/`
- WHEN the guard's scan runs
- THEN it finds no occurrence of the whole identifiers `llama`, `llama_cpp`, `ggml`, or `candle` outside comment lines

#### Scenario: No existing guard table changes shape

- GIVEN `EXPECTED_MEMBERS`, `ALLOWED`, and `EXTERNAL_ALLOWED` as they exist before this change
- WHEN the three new scans are added
- THEN none of the three tables gains, loses, or modifies an entry — the workspace member count and every crate's allowed external dependencies are unchanged
