# Runtime API Domain Specification

## Purpose

`runtime-api` is the stub for the Runtime API domain, implementing `26-runtime-api.md`.

## Requirements

### Requirement: Exhaustive Dependency Set

`runtime-api` MUST depend on exactly `runtime-primitives`, `runtime-admission`, `runtime-object`, `runtime-state`, `runtime-allocation`, `runtime-storage`, and `runtime-network` among workspace crates, and on no other workspace crate.

#### Scenario: Declared dependencies match the allowed set

- GIVEN `runtime-api/Cargo.toml`
- WHEN `cargo metadata` is inspected
- THEN its workspace-crate dependencies are exactly `runtime-primitives`, `runtime-admission`, `runtime-object`, `runtime-state`, `runtime-allocation`, `runtime-storage`, and `runtime-network`

### Requirement: Public Ports Only, Never Concrete Implementations

`runtime-api` MUST depend only on each domain's public Inbound Port contracts and shared types once those exist; it MUST NEVER reference a domain's concrete implementation modules. This constraint is not fully machine-checkable at crate granularity in this change — it is enforced by review now and will be strengthened once ports are designed in the trait-design follow-up change.

#### Scenario: Crate-level dependency edges match, port usage deferred

- GIVEN `runtime-api` currently has no public traits to depend on (per this change's scope)
- WHEN `runtime-api/src/lib.rs` is reviewed
- THEN it contains only a doc-commented stub, with no references to concrete implementation types of any dependency

### Requirement: Stub Crate, No Public Traits

`runtime-api/src/lib.rs` MUST be a stub with a crate-level doc comment citing `26-runtime-api.md`, and MUST NOT define public traits.

#### Scenario: Crate compiles with only a doc-commented stub

- GIVEN `runtime-api/src/lib.rs`
- WHEN `cargo check -p runtime-api` runs
- THEN it succeeds
- AND the file contains no public trait declarations

#### Scenario: Doc comment cites the owning doc

- GIVEN `runtime-api/src/lib.rs`
- WHEN its crate doc comment is read
- THEN it references `26-runtime-api.md`
