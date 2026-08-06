# Delta for Composition Root

## REMOVED Requirements

### Requirement: No Public Traits In This Change

(Reason: retired by `worker-composition-root` — `main.rs` now performs real cross-domain wiring by design; superseded by "Runtime Wires One Real Execution End-To-End" below.)

## ADDED Requirements

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
