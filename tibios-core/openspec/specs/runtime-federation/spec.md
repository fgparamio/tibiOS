# Federation Domain Specification

## Purpose

`runtime-federation` is the stub for the Federation domain, implementing `31-federation.md`.

## Requirements

### Requirement: Exhaustive Dependency Set

`runtime-federation` MUST depend on exactly `runtime-primitives`, `runtime-network`, `runtime-replication`, and `runtime-api` among workspace crates, and on no other workspace crate.

#### Scenario: Declared dependencies match the allowed set

- GIVEN `runtime-federation/Cargo.toml`
- WHEN `cargo metadata` is inspected
- THEN its workspace-crate dependencies are exactly `runtime-primitives`, `runtime-network`, `runtime-replication`, and `runtime-api`

### Requirement: Stub Crate, No Public Traits

`runtime-federation/src/lib.rs` MUST be a stub with a crate-level doc comment citing `31-federation.md`, and MUST NOT define public traits.

#### Scenario: Crate compiles with only a doc-commented stub

- GIVEN `runtime-federation/src/lib.rs`
- WHEN `cargo check -p runtime-federation` runs
- THEN it succeeds
- AND the file contains no public trait declarations

#### Scenario: Doc comment cites the owning doc

- GIVEN `runtime-federation/src/lib.rs`
- WHEN its crate doc comment is read
- THEN it references `31-federation.md`
