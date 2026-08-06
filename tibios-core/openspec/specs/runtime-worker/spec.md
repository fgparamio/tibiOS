# Worker Domain Specification

## Purpose

`runtime-worker` is the stub for the Worker domain, implementing `18-worker-model.md`.

## Requirements

### Requirement: Exhaustive Dependency Set

`runtime-worker` MUST depend on exactly `runtime-primitives`, `runtime-allocation`, and `runtime-object` among workspace crates, and on no other workspace crate.

#### Scenario: Declared dependencies match the allowed set

- GIVEN `runtime-worker/Cargo.toml`
- WHEN `cargo metadata` is inspected
- THEN its workspace-crate dependencies are exactly `runtime-primitives`, `runtime-allocation`, and `runtime-object`

### Requirement: Stub Crate, No Public Traits

`runtime-worker/src/lib.rs` MUST be a stub with a crate-level doc comment citing `18-worker-model.md`, and MUST NOT define public traits.

#### Scenario: Crate compiles with only a doc-commented stub

- GIVEN `runtime-worker/src/lib.rs`
- WHEN `cargo check -p runtime-worker` runs
- THEN it succeeds
- AND the file contains no public trait declarations

#### Scenario: Doc comment cites the owning doc

- GIVEN `runtime-worker/src/lib.rs`
- WHEN its crate doc comment is read
- THEN it references `18-worker-model.md`
