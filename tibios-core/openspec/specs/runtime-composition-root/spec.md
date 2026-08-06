# Composition Root Specification

## Purpose

`runtime` is the workspace's binary crate and Composition Root, implementing the Composition Root section of `02-project-structure.md`.

## Requirements

### Requirement: The Golden Rule — Sole Dependency Exception

`runtime` MAY depend on every other crate in the workspace. No crate MAY depend on `runtime`. This is the sole deliberate exception to the narrow-dependency principle enforced elsewhere in the workspace.

#### Scenario: Runtime may depend on all 15 domain crates

- GIVEN `runtime/Cargo.toml`
- WHEN `cargo metadata` is inspected
- THEN its workspace-crate dependencies may include any or all of the other 15 crates without triggering an architecture guard violation

#### Scenario: No crate depends on runtime

- GIVEN every crate's `Cargo.toml` other than `runtime`
- WHEN `cargo metadata` is inspected
- THEN none of them list `runtime` as a dependency

### Requirement: Hosts The Architecture Guard

`runtime` MUST host the dependency-graph enforcement test at `runtime/tests/architecture_guard.rs`. No separate crate is created for this purpose; `runtime` already legitimately depends on every crate and can freely parse `cargo metadata` for all of them.

#### Scenario: Guard test lives inside the runtime crate

- GIVEN the workspace file tree
- WHEN `runtime/tests/architecture_guard.rs` is located
- THEN it exists inside the `runtime` package's `tests/` directory, not in a standalone crate

### Requirement: Runtime Wires One Real Execution End-To-End

`runtime`'s entry point MUST replace the stub with real wiring: it MUST construct a concrete `ExecutionChannel`, obtain a `WorkerService` implementation exclusively through a factory function returning `impl WorkerService`, submit one execution, drain the events emitted on the channel, and print the terminal `ExecutionReport`. It MUST NOT name any concrete `WorkerService` or transport type at the binding site — only the factory's `impl WorkerService` return type crosses into `main.rs`. It MUST NOT hand-wire `runtime-allocation`, `runtime-object`, or `runtime-scheduler` — those stay out of scope.

#### Scenario: cargo run -p runtime prints a terminal report

- GIVEN the wired `runtime` binary
- WHEN `cargo run -p runtime` is executed
- THEN it submits one execution, drains its emitted events, and prints a terminal `ExecutionReport`
- AND the process exits successfully

#### Scenario: main.rs never names a concrete worker or channel type

- GIVEN `runtime/src/main.rs`
- WHEN its source is inspected
- THEN the only worker-related type it references is a factory function's `impl WorkerService` return — no concrete struct name from the in-process adapter appears at the binding site

### Requirement: Runtime Is The Sole Crate Permitted An Async Runtime Dependency

`runtime` MAY depend on `tokio`. No other workspace crate, including `runtime-worker`, MAY gain a new dependency as part of this change. `runtime/tests/architecture_guard.rs`'s `EXTERNAL_ALLOWED` table MUST record this as `("runtime", &["tokio"])`, and no other row in that table MAY list `tokio`.

#### Scenario: tokio is allowlisted for runtime alone

- GIVEN `EXTERNAL_ALLOWED` in `runtime/tests/architecture_guard.rs`
- WHEN the table is inspected
- THEN the `runtime` row includes `"tokio"` and no other row does

#### Scenario: runtime-worker gains zero dependencies

- GIVEN `crates/runtime-worker/Cargo.toml` before and after this change
- WHEN its dependency list is diffed
- THEN it is unchanged
