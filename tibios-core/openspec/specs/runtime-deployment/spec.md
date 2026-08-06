# Deployment Domain Specification

## Purpose

`runtime-deployment` is the stub for the Deployment domain, implementing `29-deployment.md`.

## Requirements

### Requirement: Exhaustive Dependency Set — Primitives Only

`runtime-deployment` MUST depend on exactly `runtime-primitives` among workspace crates, and on no other workspace crate. This isolation is deliberate and load-bearing: the Composition Root (`runtime`) is what connects Deployment to every other domain; Deployment itself MUST NEVER reach into another domain directly.

#### Scenario: Only primitives is a workspace dependency

- GIVEN `runtime-deployment/Cargo.toml`
- WHEN `cargo metadata` is inspected
- THEN its only workspace-crate dependency is `runtime-primitives`

#### Scenario: Adding a direct domain dependency is rejected

- GIVEN a developer adds `runtime-worker` (or any domain crate other than `runtime-primitives`) to `runtime-deployment/Cargo.toml`
- WHEN the architecture guard runs
- THEN it fails, naming `runtime-deployment` and the unexpected dependency

### Requirement: Stub Crate, No Public Traits

`runtime-deployment/src/lib.rs` MUST be a stub with a crate-level doc comment citing `29-deployment.md`, and MUST NOT define public traits.

#### Scenario: Crate compiles with only a doc-commented stub

- GIVEN `runtime-deployment/src/lib.rs`
- WHEN `cargo check -p runtime-deployment` runs
- THEN it succeeds
- AND the file contains no public trait declarations

#### Scenario: Doc comment cites the owning doc

- GIVEN `runtime-deployment/src/lib.rs`
- WHEN its crate doc comment is read
- THEN it references `29-deployment.md`
