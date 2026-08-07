# Delta for Composition Root

## MODIFIED Requirements

### Requirement: Runtime Wires One Real Execution End-To-End

`runtime`'s entry point MUST wire real execution end-to-end: it MUST construct a concrete `ExecutionChannel`, obtain a `WorkerService` implementation, submit one execution, drain the events emitted on the channel, and print the terminal `ExecutionReport`. With three structurally different concrete Worker implementations now present in the workspace, `main.rs` MUST select between them by calling an `any_worker(kind)` factory and naming only `AnyWorker` (via that factory's return) and a `WorkerKind` selection value — never a concrete Worker struct or any engine type. `WorkerKind` is a selection enum, not a worker type or a transport, and `02-project-structure.md:291` assigns naming an implementation selection to the Composition Root. When `WorkerKind::Ray` is selected, its endpoint address MUST be sourced from an environment variable, read only inside `main.rs`, never hard-coded — `main.rs` MUST NOT hand-wire `runtime-allocation`, `runtime-object`, or `runtime-scheduler`, and MUST NOT introduce a general-purpose config system for this single value.
(Previously: "two structurally different concrete Worker implementations"; no configuration-sourcing behavior existed since no Worker needed external configuration.)

#### Scenario: cargo run -p runtime prints a terminal report

- GIVEN the wired `runtime` binary
- WHEN `cargo run -p runtime` is executed
- THEN it submits one execution, drains its emitted events, and prints a terminal `ExecutionReport`
- AND the process exits successfully

#### Scenario: main.rs names AnyWorker, never a concrete Worker struct

- GIVEN `runtime/src/main.rs`
- WHEN its source is inspected
- THEN it references `AnyWorker` and `WorkerKind` (via `any_worker(WorkerKind::…)`) as the only Worker-related items — neither `InProcessWorker`, `LocalInferWorker`, `RayWorker`, nor any concrete engine type appears anywhere in the file

#### Scenario: Ray's endpoint comes from an environment variable, not a hard-coded value

- GIVEN `main.rs` with `WorkerKind::Ray` selected
- WHEN its source is inspected
- THEN the endpoint address is read from an environment variable rather than hard-coded as a string literal
