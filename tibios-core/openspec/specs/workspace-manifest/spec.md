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

### Requirement: The External-Dependency Allowlist Admits An Optional Inference-Engine Bindings Crate, Governed Like Any Other External Dependency

`EXTERNAL_ALLOWED` (`runtime/tests/architecture_guard.rs`) has joint provenance, matching that file's own header doc: `runtime-composition-root/spec.md` establishes the table's base structure and its `("runtime", &["tokio"])` row; this `workspace-manifest` requirement governs how the table's `runtime` row is extended for further external dependencies, this one included. Neither spec owns the table exclusively.

`runtime`'s row in `EXTERNAL_ALLOWED` (`runtime/tests/architecture_guard.rs`) MUST grow from `&["tokio"]` to also list the allowlisted llama.cpp bindings crate, even though that dependency is declared `optional = true` in `runtime/Cargo.toml`. `optional = true` MUST NOT be treated as exempting a dependency from the allowlist: `every_crate_declares_exactly_its_allowed_external_dependencies` reads `package.dependencies` from `cargo metadata`, filtered only on `DependencyKind::Normal | DependencyKind::Build` — a filter optional dependencies still pass, regardless of whether the `llamacpp` feature happens to be enabled for the `cargo metadata` invocation being measured. A new table-only test, `INFERENCE_ENGINE_CRATES`, MUST assert the bindings crate is allowlisted for exactly `runtime`, mirroring `transport_dependencies_are_allowlisted_for_exactly_one_crate` and `async_runtime_is_allowlisted_for_exactly_one_crate`.

#### Scenario: The bindings crate is present in cargo metadata regardless of feature activation

- GIVEN `runtime/Cargo.toml` declares the bindings crate as `optional = true` under `[dependencies]`
- WHEN `cargo metadata` is inspected, whether or not the `llamacpp` feature is enabled for that invocation
- THEN the bindings crate still appears in `runtime`'s `Normal`-kind dependency set, and `every_crate_declares_exactly_its_allowed_external_dependencies` requires it to be present in `EXTERNAL_ALLOWED`'s `runtime` row for the guard to pass

#### Scenario: A table-only test pins the bindings crate to runtime alone

- GIVEN `INFERENCE_ENGINE_CRATES` and `EXTERNAL_ALLOWED` as defined in `runtime/tests/architecture_guard.rs`
- WHEN the guard scans `EXTERNAL_ALLOWED`'s rows for the bindings crate
- THEN exactly one row contains it, `runtime`, mirroring `transport_dependencies_are_allowlisted_for_exactly_one_crate` and `async_runtime_is_allowlisted_for_exactly_one_crate`

#### Scenario: Workspace member count is unaffected

- GIVEN `EXPECTED_MEMBERS` before and after this change
- WHEN `cargo metadata --workspace` is inspected
- THEN it still lists exactly the same 16 members — no new workspace crate is added

### Requirement: A Clean Clone With The Feature Never Enabled Compiles No Non-tokio External Dependency Into runtime

With the `llamacpp` feature never enabled (the default), `runtime`'s actually-compiled dependency graph MUST contain no external (non-workspace) crate beyond `tokio` — the optional bindings crate MUST be declared and allowlisted, but MUST NOT be compiled in.

#### Scenario: A default build compiles zero non-tokio external dependencies into runtime

- GIVEN a clean clone of the workspace with the `llamacpp` feature never enabled
- WHEN `cargo build -p runtime` (or `cargo build --workspace`) is run
- THEN the resulting build compiles no external crate into `runtime` beyond `tokio` — no native toolchain (clang, bindgen, cmake) is invoked, and no bindings-crate object code is produced
