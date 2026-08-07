# Delta for Worker Inbound Port

## ADDED Requirements

### Requirement: A Shared O1-O4 Conformance Harness Exercises Every WorkerService Implementation

The Worker domain's Inbound Port MUST be exercised by exactly one shared O1-O4 conformance harness — a single, reusable test suite expressing register-before-first-suspension (O1), deregister-on-every-completion-path (O2, with distinct completed/cancelled/duration-breached sub-cases), reject-unknown-workload for `cancel`/`pulse` (O3), and reject-duplicate-in-flight-`execute` (O4) — that runs, with the same assertion logic unmodified, against any `WorkerService` implementation supplied to it. Every concrete `WorkerService` implementation in the workspace MUST be run through this harness and pass all four obligations; no implementation may substitute a bespoke, implementation-specific O1-O4 test suite in place of the shared one. This closes the obligation deliberately deferred when the port was first built ("named here so the `local-infer` change knows to build it rather than rediscover the obligations").

The harness MUST live inside `runtime/src/worker/`, `#[cfg(test)]`-gated, not as a separate integration-test crate: `runtime` is a binary-only crate with no library target, so an integration test under `runtime/tests/` cannot reach any `pub(super)` Worker type (`InProcessWorker`, `LocalInferWorker`, `AnyWorker` are all `pub(super)`). The harness MUST take the shape of a `macro_rules!` macro that, given a name and a Worker-constructing factory, emits one `#[tokio::test]` wrapper per obligation assertion — so that conformance is all-or-nothing per invocation, and no Worker can adopt some obligations while silently skipping others. This macro MUST be invoked at least three times: once for `InProcessWorker`, once for `LocalInferWorker`, and once for each `AnyWorker` variant (wrapping `InProcessWorker` and wrapping `LocalInferWorker`) — the `AnyWorker` invocations are not redundant ceremony, since the dispatch layer is exactly where an eagerness regression would silently reintroduce an O1 violation without them.

#### Scenario: The harness runs unmodified against two structurally different Workers

- GIVEN the shared O1-O4 harness and two `WorkerService` implementations that differ in their internal concurrency model — one async-native (`InProcessWorker`), one blocking-thread-backed (`LocalInferWorker`)
- WHEN the harness is run against each, supplying only the implementation-specific construction
- THEN all four obligations (O1-O4) pass for both implementations, using the same shared assertion logic

#### Scenario: Adding a second Worker requires no duplicated assertion logic

- GIVEN a second `WorkerService` implementation is added to the workspace
- WHEN its O1-O4 obligations are verified
- THEN this is done by invoking the existing shared harness, not by writing a duplicate copy of the four obligation checks

#### Scenario: The harness lives inside the binary crate's source, not a separate integration-test crate

- GIVEN `runtime`'s crate layout (binary-only, no `src/lib.rs`)
- WHEN the conformance harness's location is inspected
- THEN it is a `#[cfg(test)]`-gated module inside `runtime/src/worker/`, not a file under `runtime/tests/`

#### Scenario: The harness is invoked against both AnyWorker variants, not only the two concrete Workers directly

- GIVEN the shared harness macro
- WHEN its invocations across the codebase are inspected
- THEN it is invoked once for `InProcessWorker`, once for `LocalInferWorker`, and once for each `AnyWorker` variant — at least three invocations in total, none of them skipped
