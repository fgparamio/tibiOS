# Security & Observability Domains Specification

## Purpose

`runtime-security` and `runtime-observability` are stubs for the Security and Observability domains, implementing `08-security.md` and `09-observability.md` respectively. They are independent crates covered together because they share the same dependency shape.

## Requirements

### Requirement: Exhaustive Dependency Set (runtime-security)

`runtime-security` MUST depend on exactly `runtime-primitives` among workspace crates, and on no other workspace crate.

#### Scenario: Only primitives is a workspace dependency

- GIVEN `runtime-security/Cargo.toml`
- WHEN `cargo metadata` is inspected
- THEN its only workspace-crate dependency is `runtime-primitives`

### Requirement: Exhaustive Dependency Set (runtime-observability)

`runtime-observability` MUST depend on exactly `runtime-primitives` among workspace crates, and on no other workspace crate.

#### Scenario: Only primitives is a workspace dependency

- GIVEN `runtime-observability/Cargo.toml`
- WHEN `cargo metadata` is inspected
- THEN its only workspace-crate dependency is `runtime-primitives`

### Requirement: Stub Crates, No Public Traits

`runtime-security/src/lib.rs` MUST cite `08-security.md` and `runtime-observability/src/lib.rs` MUST cite `09-observability.md` in their crate-level doc comments. Neither crate MUST define public traits.

#### Scenario: Both crates compile with only a doc-commented stub

- GIVEN `runtime-security/src/lib.rs` and `runtime-observability/src/lib.rs`
- WHEN `cargo check -p runtime-security -p runtime-observability` runs
- THEN it succeeds
- AND neither file contains public trait declarations

#### Scenario: Doc comments cite the correct owning doc each

- GIVEN `runtime-security/src/lib.rs` and `runtime-observability/src/lib.rs`
- WHEN their crate doc comments are read
- THEN `runtime-security` references `08-security.md` and `runtime-observability` references `09-observability.md`
