# Replication Domain Specification

## Purpose

`runtime-replication` is the stub for the Replication domain, implementing `24-replication.md`.

## Requirements

### Requirement: Exhaustive Dependency Set

`runtime-replication` MUST depend on exactly `runtime-primitives`, `runtime-object`, and `runtime-storage` among workspace crates, and on no other workspace crate.

#### Scenario: Declared dependencies match the allowed set

- GIVEN `runtime-replication/Cargo.toml`
- WHEN `cargo metadata` is inspected
- THEN its workspace-crate dependencies are exactly `runtime-primitives`, `runtime-object`, and `runtime-storage`

### Requirement: Stub Crate, No Public Traits

`runtime-replication/src/lib.rs` MUST be a stub with a crate-level doc comment citing `24-replication.md`, and MUST NOT define public traits.

#### Scenario: Crate compiles with only a doc-commented stub

- GIVEN `runtime-replication/src/lib.rs`
- WHEN `cargo check -p runtime-replication` runs
- THEN it succeeds
- AND the file contains no public trait declarations

#### Scenario: Doc comment cites the owning doc

- GIVEN `runtime-replication/src/lib.rs`
- WHEN its crate doc comment is read
- THEN it references `24-replication.md`
