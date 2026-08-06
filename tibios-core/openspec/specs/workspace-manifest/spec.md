# Workspace Manifest Specification

## Purpose

The root `Cargo.toml` is a virtual workspace manifest declaring all crates that make up TibiOS. It carries no business logic of its own — it exists to bind the members together and host shared lints/profile/deps.

## Requirements

### Requirement: Virtual Workspace With Exact Members

The root `Cargo.toml` MUST be a virtual manifest (`[workspace]`, no `[package]`) listing exactly 16 members: `runtime-primitives`, `runtime-object`, `runtime-scheduler`, `runtime-allocation`, `runtime-admission`, `runtime-worker`, `runtime-network`, `runtime-storage`, `runtime-security`, `runtime-observability`, `runtime-state`, `runtime-replication`, `runtime-deployment`, `runtime-api`, `runtime-federation`, `runtime`. It MUST target Rust edition 2024.

#### Scenario: Workspace member count and names match exactly

- GIVEN the root `Cargo.toml`
- WHEN `cargo metadata --workspace` is inspected
- THEN it lists exactly the 16 named crates above, no more and no fewer

#### Scenario: Edition is 2024

- GIVEN the root `Cargo.toml` (or `[workspace.package]`)
- WHEN the edition field is read
- THEN it is `"2024"`

### Requirement: No Business Logic At The Workspace Root

The root manifest MUST NOT define a `[package]` (no default binary/library crate at the root) and MUST NOT contain domain code.

#### Scenario: No default root crate

- GIVEN the root `Cargo.toml`
- WHEN parsed
- THEN it has no `[package]` table

### Requirement: Architecture Guard Enforces The Dependency Matrix

The workspace MUST include an automated test, hosted inside the `runtime` crate at `runtime/tests/architecture_guard.rs` (no additional crate created for this purpose), that parses `cargo metadata` and asserts each crate's actual intra-workspace dependency set equals the allowed set defined per-crate in this spec set. `runtime` is exempted from the narrow-dependency check (it may depend on all crates); every other crate's allowed set MUST be checked for exact equality, catching both forbidden additions and silently dropped required edges.

#### Scenario: Drift is caught

- GIVEN a crate's `Cargo.toml` gains a workspace dependency not present in its allowed set
- WHEN `cargo test --workspace` runs
- THEN `architecture_guard.rs` fails with a message naming the crate and the unexpected dependency

#### Scenario: Missing required edge is caught

- GIVEN a crate's `Cargo.toml` drops a workspace dependency required by its allowed set
- WHEN `cargo test --workspace` runs
- THEN `architecture_guard.rs` fails with a message naming the crate and the missing dependency

#### Scenario: Runtime is exempt from the narrow check

- GIVEN the `runtime` crate depends on all 15 other workspace crates
- WHEN `architecture_guard.rs` runs
- THEN no violation is reported for `runtime`'s dependency set
