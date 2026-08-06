# Admission Domain Specification

## Purpose

`runtime-admission` is the stub for the Admission Control domain, implementing `20-admission-control.md`.

## Requirements

### Requirement: Exhaustive Dependency Set

`runtime-admission` MUST depend on exactly `runtime-primitives` and `runtime-state` among workspace crates. It MUST NEVER depend on `runtime-storage`, `runtime-network`, or `runtime-scheduler`, directly or otherwise added to its manifest.

#### Scenario: Declared dependencies match the allowed set

- GIVEN `runtime-admission/Cargo.toml`
- WHEN `cargo metadata` is inspected
- THEN its workspace-crate dependencies are exactly `runtime-primitives` and `runtime-state`

#### Scenario: Forbidden direct dependencies are absent

- GIVEN `runtime-admission/Cargo.toml`
- WHEN `cargo metadata` is inspected
- THEN it lists none of `runtime-storage`, `runtime-network`, `runtime-scheduler` as dependencies

### Requirement: Stub Crate, No Public Traits

`runtime-admission/src/lib.rs` MUST be a stub with a crate-level doc comment citing `20-admission-control.md`, and MUST NOT define public traits.

#### Scenario: Crate compiles with only a doc-commented stub

- GIVEN `runtime-admission/src/lib.rs`
- WHEN `cargo check -p runtime-admission` runs
- THEN it succeeds
- AND the file contains no public trait declarations

#### Scenario: Doc comment cites the owning doc

- GIVEN `runtime-admission/src/lib.rs`
- WHEN its crate doc comment is read
- THEN it references `20-admission-control.md`
