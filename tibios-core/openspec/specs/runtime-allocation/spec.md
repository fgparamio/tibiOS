# Allocation Domain Specification

## Purpose

`runtime-allocation` is the stub for the Allocation domain, implementing `15-allocation-model.md`.

## Requirements

### Requirement: Exhaustive Dependency Set

`runtime-allocation` MUST depend on exactly `runtime-primitives`, `runtime-scheduler`, and `runtime-object` among workspace crates, and on no other workspace crate.

#### Scenario: Declared dependencies match the allowed set

- GIVEN `runtime-allocation/Cargo.toml`
- WHEN `cargo metadata` is inspected
- THEN its workspace-crate dependencies are exactly `runtime-primitives`, `runtime-scheduler`, and `runtime-object`

### Requirement: Stub Crate, No Public Traits

`runtime-allocation/src/lib.rs` MUST be a stub with a crate-level doc comment citing `15-allocation-model.md`, and MUST NOT define public traits.

#### Scenario: Crate compiles with only a doc-commented stub

- GIVEN `runtime-allocation/src/lib.rs`
- WHEN `cargo check -p runtime-allocation` runs
- THEN it succeeds
- AND the file contains no public trait declarations

#### Scenario: Doc comment cites the owning doc

- GIVEN `runtime-allocation/src/lib.rs`
- WHEN its crate doc comment is read
- THEN it references `15-allocation-model.md`

### Requirement: AllocationContract Is A Public Data Contract, Intentionally Partial

`runtime-allocation` MUST define a public `AllocationContract` struct, and it is the only crate that MUST define it (`02-project-structure.md`'s Ownership Boundaries table: `Allocation → AllocationContract → Worker`; the producer owns the contract, consumers never redefine it). Its field set MUST match exactly what the frozen wire contract already carries in `AllocationContract` (`worker.proto`): `max_execution_duration`. `AllocationContract` MUST NOT define behavior — no methods beyond trivial constructors/accessors — and MUST NOT be declared as, or alongside, a public trait. Its doc comment MUST state that the struct is intentionally partial, pending `15-allocation-model.md`'s own future change to add the remaining documented facets (exclusive/shared, renewable lease, preemptible, migration allowed, checkpoint required).

#### Scenario: AllocationContract is public and defined only in runtime-allocation

- GIVEN the workspace's crates
- WHEN `AllocationContract` is searched for as a public type definition
- THEN it is found exactly once, in `runtime-allocation`, and nowhere else

#### Scenario: AllocationContract's field set matches the frozen wire contract exactly

- GIVEN the `AllocationContract` struct definition
- WHEN its fields are enumerated
- THEN there is exactly one field, `max_execution_duration`, matching `worker.proto`'s `AllocationContract` message

#### Scenario: AllocationContract defines no behavior and no trait

- GIVEN `runtime-allocation/src/lib.rs`
- WHEN its `AllocationContract` definition and surrounding code are inspected
- THEN no domain-behavior method is attached to it beyond trivial constructors/accessors
- AND no public trait is declared alongside it

#### Scenario: AllocationContract's doc comment documents partiality

- GIVEN the `AllocationContract` struct's doc comment
- WHEN it is read
- THEN it states the struct is intentionally partial and cites `15-allocation-model.md` as the owner of its eventual full shape

### Requirement: External Allowlist Stays Empty

`runtime-allocation`'s external (non-workspace) dependencies MUST remain the empty set; adding `AllocationContract` MUST NOT introduce a new external dependency.

#### Scenario: No external dependency is added

- GIVEN `runtime-allocation/Cargo.toml`
- WHEN its `[dependencies]` are read
- THEN no non-workspace entry is present
