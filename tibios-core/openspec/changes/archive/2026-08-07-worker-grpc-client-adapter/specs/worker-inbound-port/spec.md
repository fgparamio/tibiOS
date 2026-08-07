# Delta for Worker Inbound Port

## ADDED Requirements

### Requirement: WorkerError Normalizes Transport Failures Without Naming A Transport Type

`WorkerError` MUST include a variant representing a transport-level failure (connection refused, deadline exceeded, or any other transport-originated failure), carrying only domain-safe data (a status-kind classification plus a message string) — never a `tonic::Status` or any other transport-specific type as a field. This variant MUST implement `Classify` per `04-error-handling.md`, distinguishing `Transient` transport conditions (e.g. connection refused, deadline exceeded) from `Permanent` ones (e.g. an invalid-argument-shaped rejection) rather than classifying every transport failure the same way.

#### Scenario: A transport failure classifies by its underlying condition, not uniformly

- GIVEN two distinct transport-failure conditions, one representing a temporary network hiccup and one representing a rejected request that will never succeed
- WHEN each is converted into `WorkerError`'s transport variant and classified
- THEN the temporary condition classifies `Transient` and the permanently-rejected one classifies `Permanent`

#### Scenario: The transport-failure variant carries no transport type

- GIVEN `WorkerError`'s transport-failure variant definition
- WHEN its fields are inspected
- THEN none is a `tonic::`, `prost::`, or `tokio::` typed field

### Requirement: Worker Substitutability

Any `WorkerService` implementation MUST be observationally substitutable: a caller MUST NOT need to distinguish `InProcessWorker`, `LocalInferWorker`, or `RayWorker` by streaming event ordering, terminal-state semantics, cancellation behavior, or the shape of error classification `WorkerError` exposes. Transport-specific failures MUST be normalized into `WorkerError` without exposing a transport-specific type or protocol — the corollary of the existing no-`tonic::`-leak rule (`worker-inbound-port/spec.md`, "The Domain Surface Names No Transport Type And No Tokio Type"), now tested by a Worker with a genuinely distinct failure source.

#### Scenario: Equivalent scenarios produce equivalent observable outcomes across implementations

- GIVEN the same logical scenario (a successful execution, a rejected duplicate, an unknown-workload query) run against two different `WorkerService` implementations
- WHEN each implementation's observable output is compared (event ordering, terminal phase, error variant)
- THEN neither exposes an implementation-specific detail the other lacks — the outward contract is identical

## MODIFIED Requirements

### Requirement: A Shared O1-O4 Conformance Harness Exercises Every WorkerService Implementation

The Worker domain's Inbound Port MUST be exercised by exactly one shared O1-O4 conformance harness — a single, reusable test suite expressing register-before-first-suspension (O1), deregister-on-every-completion-path (O2, with distinct completed/cancelled/duration-breached sub-cases), reject-unknown-workload for `cancel`/`pulse` (O3), and reject-duplicate-in-flight-`execute` (O4) — that runs, with the same assertion logic unmodified, against any `WorkerService` implementation supplied to it. Every concrete `WorkerService` implementation in the workspace MUST be run through this harness and pass all four obligations; no implementation may substitute a bespoke, implementation-specific O1-O4 test suite in place of the shared one.

The harness MUST live inside `runtime/src/worker/`, `#[cfg(test)]`-gated, not as a separate integration-test crate: `runtime` is a binary-only crate with no library target, so an integration test under `runtime/tests/` cannot reach any `pub(super)` Worker type. The harness MUST take the shape of a `macro_rules!` macro that, given a name and a Worker-constructing factory, emits one `#[tokio::test]` wrapper per obligation assertion. This macro MUST be invoked at least five times: once for `InProcessWorker`, once for `LocalInferWorker`, once for `RayWorker`, and once for each `AnyWorker` variant (wrapping each of the three) — the `AnyWorker` invocations are not redundant ceremony, since the dispatch layer is exactly where an eagerness regression would silently reintroduce an O1 violation without them.
(Previously: invoked at least three times, covering only `InProcessWorker`, `LocalInferWorker`, and their two `AnyWorker` variants — `RayWorker` and `AnyWorker::Ray` did not yet exist.)

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

#### Scenario: The harness is invoked against all three concrete Workers and all three AnyWorker variants

- GIVEN the shared harness macro
- WHEN its invocations across the codebase are inspected
- THEN it is invoked once for `InProcessWorker`, once for `LocalInferWorker`, once for `RayWorker`, and once for each of the three `AnyWorker` variants — at least five invocations in total, none of them skipped
