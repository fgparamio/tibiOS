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
