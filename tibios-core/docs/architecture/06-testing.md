# TibiOS Testing Guidelines

Version: 1.1

## Purpose

Testing is an engineering discipline. Tests protect behavior, enable refactoring, and document expected behavior. Every bug fixed becomes a permanent regression test.

## Core Principles

A passing test increases confidence. A failing test provides information. A flaky test provides neither — flaky tests are unacceptable.

## Testing Pyramid

Prefer many unit tests, some integration tests, few end-to-end tests. Avoid relying exclusively on end-to-end testing.

## Test Types

Every crate may contain unit tests, integration tests, property tests, benchmarks, and end-to-end tests when applicable. Each type has a different purpose.

## Unit Tests

Verify individual behavior. Requirements: fast, deterministic, independent, isolated. Should run in milliseconds.

## Integration Tests

Verify collaboration between modules, using the public API. Never test private implementation details.

## End-to-End Tests

Verify complete workflows. Slower — focus on critical user scenarios. Do not duplicate unit tests.

## Test Independence & Determinism

Every test must be runnable independently, never depending on execution order. Tests must always produce the same result — avoid current time, randomness, network access, and external services unless explicitly required.

## Mocking

Mock behavior, not implementation. Prefer real implementations whenever practical. Use mocks only at system boundaries.

> For the network layer specifically, prefer libp2p's `MemoryTransport` over mocking — deterministic, fast, no ports, no flakiness.

## Temporary Files / Network Tests

Use temporary directories; never write into the repository or depend on developer-specific paths. Network tests should use local test infrastructure, never depend on Internet connectivity.

## Time

Never sleep to wait for behavior — await events, poll with timeouts, or synchronize explicitly. Sleeping creates flaky tests.

## Assertions

One test should verify one behavior. Multiple assertions are acceptable when validating one logical outcome.

## Test Names

Describe expected behavior: `creates_cluster_with_default_configuration`, `rejects_invalid_node_identifier`, `persists_object_after_restart` — not `test1`, `basic`, `works`.

## Fixtures

Keep fixtures small — only include data required for the test. Avoid giant fixture files.

## Property Testing

Use `proptest` for algorithms: serialization, parsers, schedulers, hashing, routing. Verify invariants rather than individual examples.

> This is the chosen approach for the Scheduling Engine specifically, since it's designed as a pure function (`16-scheduling-engine.md`) — property tests can assert invariants like "never routes to an island with insufficient resources" without any real cluster state.

## Regression Tests

Every production bug must become a regression test. Never fix the same bug twice.

## Performance Tests / Benchmarks

Performance expectations belong in benchmarks, never in unit-test timing assertions. Benchmarks measure performance; they do not verify correctness — keep both concerns separate.

## Concurrency Tests

Concurrency requires dedicated testing: cancellation, races, shutdown, retries, deadlock prevention, backpressure.

## Distributed Tests

Distributed systems require fault injection: node crashes, partitions, message duplication, delays, timeouts, partial failures. Never test only the happy path.

## Chaos Tests

Distributed, mature systems (CockroachDB, TiKV) treat chaos testing as a discipline distinct from day-to-day unit tests — TibiOS follows the same practice, at two levels:

**Deterministic chaos in CI** — can start early, once the distributed runtime exists. Use `turmoil` (the Tokio team's own deterministic network simulation framework — inject partitions, latency, message loss/duplication inside a normal Rust test, reproducible by seed) and `fail-rs` (failpoints, the same technique TiKV uses to inject failures at specific code points).

**Chaos engineering** — black-box, against real binaries, Jepsen-style. This is a maturity-phase practice, exercised post-MVP, not a day-to-day development gate.

Both levels exercise: shutting down a node mid-task, network partitions, random latency, message duplication, out-of-order delivery, controlled data corruption, simulated memory/disk exhaustion. The goal is verifying the Runtime behaves correctly under real failure conditions — as important as unit tests for a platform designed to be distributed from inception.

## Coverage

Coverage is a metric, not a goal. 100% coverage does not imply correctness. Meaningful tests matter more than percentages.

## Documentation Tests

Examples in Rustdoc should compile and, whenever practical, execute successfully. Documentation is executable.

## Continuous Integration

Every Pull Request must execute `cargo fmt --check`, `cargo clippy -- -D warnings`, and `cargo test`. PRs failing any check cannot be merged.

## Performance of the Test Suite

Developers should be able to run the full unit test suite frequently. If tests become slow, identify the cause — do not normalize slow feedback.

## Logging During Tests

Tests should not depend on log output. Logs may assist debugging but should never determine success.

## Randomness

When randomness is required, use fixed seeds. Reproducibility is mandatory.

## Anti-Patterns

Avoid: sleeping to wait, shared mutable fixtures, network dependency, test ordering, hidden global state, assertions on implementation details, enormous fixture files, duplicated tests.

## Review Checklist

Before merging ask:

- Is the behavior clearly verified?
- Is the test deterministic?
- Is it independent?
- Does it test behavior rather than implementation?
- Will it still pass after internal refactoring?
- Does it improve confidence?

## TibiOS Rules

Every scheduler bug becomes a scheduler test. Every storage bug becomes a storage test. Every networking bug becomes a networking test. Every distributed failure becomes a reproducible scenario.

No production issue is considered resolved until a regression test exists.

## Motto

Tests protect the future. Write them as if someone will refactor your code in five years.
