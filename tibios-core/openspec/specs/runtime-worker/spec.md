# Worker Domain Specification

## Purpose

`runtime-worker` is the stub for the Worker domain, implementing `18-worker-model.md`.

## Requirements

### Requirement: Exhaustive Dependency Set

`runtime-worker` MUST depend on exactly `runtime-primitives`, `runtime-allocation`, and `runtime-object` among workspace crates, and on no other workspace crate. Its external (non-workspace, normal) dependencies MUST be a subset of `{tonic, prost}`, and its build-dependencies MUST be a subset of `{tonic-build}`.

#### Scenario: Declared dependencies match the allowed set

- GIVEN `runtime-worker/Cargo.toml`
- WHEN `cargo metadata` is inspected
- THEN its workspace-crate dependencies are exactly `runtime-primitives`, `runtime-allocation`, and `runtime-object`

#### Scenario: External deps stay within the allowlist

- GIVEN `runtime-worker/Cargo.toml`
- WHEN its `[dependencies]` are read
- THEN every non-workspace entry is `tonic`, `prost`, or a transitive dependency of those crates

#### Scenario: Build-dependency stays within the allowlist

- GIVEN `runtime-worker/Cargo.toml`
- WHEN its `[build-dependencies]` are read
- THEN every entry is `tonic-build` or a transitive dependency of it

### Requirement: Crate Doc Comment Cites the Owning Document

`runtime-worker/src/lib.rs` MUST carry a crate-level doc comment citing `18-worker-model.md`.

#### Scenario: Doc comment cites the owning doc

- GIVEN `runtime-worker/src/lib.rs`
- WHEN its crate doc comment is read
- THEN it references `18-worker-model.md`

### Requirement: Generated Transport Code Stays Private

`runtime-worker` MUST confine all `prost`/`tonic` generated code (including anything produced by `include_proto!`) to a non-`pub` module tree rooted at `src/adapters/`, MUST NOT re-export any part of that tree via `pub use`, MUST set the `private_interfaces` lint to `deny` (not the default `warn`), and MUST NOT expose any `tonic::` or `prost::` path in its public API.

#### Scenario: Generated code module is not public

- GIVEN `runtime-worker/src/adapters/mod.rs` and every descendant module housing generated code
- WHEN the module declarations from `lib.rs` down to the generated module are inspected
- THEN none carries the `pub` keyword

#### Scenario: No re-export escapes the private module

- GIVEN every source file in `runtime-worker`
- WHEN the crate is searched for `pub use` statements
- THEN none names `adapters`, any of its submodules, or any item defined inside them

#### Scenario: private_interfaces lint is denied

- GIVEN `runtime-worker`'s lint configuration (crate attribute or `Cargo.toml` lints table)
- WHEN the level set for `private_interfaces` is read
- THEN it is `deny`

#### Scenario: Public API carries no tonic/prost path

- GIVEN every item reachable from outside `runtime-worker` (its public API)
- WHEN each signature, field type, and trait bound is inspected
- THEN no `tonic::` or `prost::` path appears anywhere in it
