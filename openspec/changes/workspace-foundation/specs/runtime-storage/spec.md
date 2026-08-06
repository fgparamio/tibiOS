# Storage Domain Specification

## Purpose

`runtime-storage` is the stub for the Runtime Storage Engine domain, implementing `21-runtime-storage-engine.md`.

## Requirements

### Requirement: Exhaustive Dependency Set

`runtime-storage` MUST depend on exactly `runtime-primitives` among workspace crates, and on no other workspace crate.

#### Scenario: Only primitives is a workspace dependency

- GIVEN `runtime-storage/Cargo.toml`
- WHEN `cargo metadata` is inspected
- THEN its only workspace-crate dependency is `runtime-primitives`

### Requirement: Stub Crate, No Public Traits

`runtime-storage/src/lib.rs` MUST be a stub with a crate-level doc comment citing `21-runtime-storage-engine.md`, and MUST NOT define public traits.

#### Scenario: Crate compiles with only a doc-commented stub

- GIVEN `runtime-storage/src/lib.rs`
- WHEN `cargo check -p runtime-storage` runs
- THEN it succeeds
- AND the file contains no public trait declarations

#### Scenario: Doc comment cites the owning doc

- GIVEN `runtime-storage/src/lib.rs`
- WHEN its crate doc comment is read
- THEN it references `21-runtime-storage-engine.md`
