# Scheduling Domain Specification

## Purpose

`runtime-scheduler` is the stub for the Scheduling domain, implementing `14-resource-model.md` and `16-scheduling-engine.md`.

## Requirements

### Requirement: Exhaustive Dependency Set

`runtime-scheduler` MUST depend on exactly `runtime-primitives` and `runtime-object` among workspace crates, and on no other workspace crate.

#### Scenario: Declared dependencies match the allowed set

- GIVEN `runtime-scheduler/Cargo.toml`
- WHEN `cargo metadata` is inspected
- THEN its workspace-crate dependencies are exactly `runtime-primitives` and `runtime-object`

### Requirement: Stub Crate, No Public Traits

`runtime-scheduler/src/lib.rs` MUST be a stub with a crate-level doc comment citing `14-resource-model.md` and `16-scheduling-engine.md`, and MUST NOT define public traits.

#### Scenario: Crate compiles with only a doc-commented stub

- GIVEN `runtime-scheduler/src/lib.rs`
- WHEN `cargo check -p runtime-scheduler` runs
- THEN it succeeds
- AND the file contains no public trait declarations

#### Scenario: Doc comment cites both owning docs

- GIVEN `runtime-scheduler/src/lib.rs`
- WHEN its crate doc comment is read
- THEN it references both `14-resource-model.md` and `16-scheduling-engine.md`
