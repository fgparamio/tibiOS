# TibiOS Rust Engineering Philosophy

Version: 1.0

> **Archived.** This is the original philosophy document as first drafted, preserved for design-history traceability. It has been superseded by `docs/architecture/00-philosophy.md` (v2), which captures the matured model derived from the full architectural design process (Object Model, Resource Model, Allocation Model, Scheduling Engine, Cluster Snapshot, Worker, State Assembler, Admission Control, Runtime Storage Engine, Networking, and the Project Structure & Dependency Architecture). Do not treat this file as current guidance.

## Purpose

This document defines the engineering philosophy for every Rust crate in TibiOS.

These principles have priority over individual coding preferences.

When in doubt, prefer consistency over cleverness.

## Core Principles

### Correctness First

Correct software is always more important than fast software.

Never sacrifice correctness for micro-optimizations.

### Safety First

Rust's safety guarantees are one of the project's biggest assets.

Unsafe code must be considered an exception.

Safe Rust is always preferred.

### Performance by Design

Performance is achieved through good architecture, not premature optimization.

Measure before optimizing.

### Simplicity

The simplest solution that satisfies all requirements is usually the best solution.

Avoid unnecessary abstractions.

Avoid unnecessary generic programming.

Avoid unnecessary traits.

### Readability

Code is read far more often than it is written.

Every function should communicate its intent immediately.

Future contributors should understand the code without needing additional explanations.

### Explicit Over Implicit

Avoid hidden behavior.

Avoid magic.

Prefer explicit configuration.

Prefer explicit ownership.

Prefer explicit lifetimes whenever they improve readability.

### Composition Over Inheritance

Behavior should be composed through traits and small components.

Large inheritance-like hierarchies are discouraged.

### Zero-Cost Abstractions

Abstractions are encouraged only when they compile to efficient machine code.

Never introduce runtime overhead for cosmetic API improvements.

### Determinism

Distributed systems become easier to debug when behavior is deterministic.

Avoid hidden global state.

Avoid random behavior unless explicitly required.

Avoid time-dependent logic whenever possible.

### Fail Early

Errors should be detected as close as possible to their origin.

Never silently ignore failures.

Never swallow errors.

## Architecture Principles

Every module must have a single responsibility.

Modules communicate through explicit interfaces.

Dependencies always point inward.

Business logic must never depend directly on infrastructure.

The runtime must not depend on the AI layer.

The AI layer may depend on the runtime.

## Memory Philosophy

Ownership must be obvious.

Borrow whenever possible.

Clone only when necessary.

Heap allocations should be intentional.

Avoid unnecessary allocations inside hot paths.

## Concurrency Philosophy

Shared mutable state is discouraged.

Prefer message passing.

Prefer immutable data.

Synchronization primitives should be the last option.

## Public APIs

Public APIs are forever.

Adding APIs is easier than removing them.

Every public function must be documented.

Breaking changes require strong justification.

## Error Philosophy

Errors are part of the API.

Errors should be descriptive.

Errors should preserve context.

Never use panic! for recoverable situations.

Never use unwrap() outside tests or prototypes.

## Unsafe Code

Unsafe is allowed only when there is no safe alternative.

Every unsafe block must contain a SAFETY comment explaining:

- why it is safe
- which invariants must hold
- how those invariants are enforced

Unsafe code should be isolated.

Unsafe code must have dedicated tests.

## Testing Philosophy

Every bug becomes a test.

Critical algorithms require unit tests.

Public APIs require integration tests.

Distributed behavior requires end-to-end tests.

## Documentation

Documentation is part of the implementation.

Every public item should explain:

- what it does
- why it exists
- when it should be used

Examples are encouraged.

## Logging

Logs exist for operators.

Logs must be actionable.

Avoid noisy logs.

Never log secrets.

## Security

Assume all external input is malicious.

Validate everything.

Never trust network input.

Never trust file input.

Never trust serialization.

## Performance Rules

Benchmark before optimizing.

Avoid unnecessary allocations.

Avoid unnecessary copies.

Prefer iterators over indexed loops when readability is preserved.

Choose algorithms before micro-optimizations.

## Code Review Checklist

Before merging, ask:

- Is this simpler?
- Is this safer?
- Is this more readable?
- Is ownership obvious?
- Are errors handled correctly?
- Is the public API stable?
- Is the performance acceptable?
- Are tests included?
- Is documentation complete?

## Things We Avoid

Premature optimization.

Hidden mutable globals.

Long functions.

Large modules.

Deep nesting.

Overly generic APIs.

Complex macros without clear value.

Unnecessary unsafe code.

Magic constants.

Silent failures.

## Engineering Motto

Build software that future engineers will enjoy maintaining.

Correctness.

Safety.

Simplicity.

Performance.

In that order.
