# Delta for Workspace Manifest

> This change grows `runtime`'s row in `runtime/tests/architecture_guard.rs`'s `EXTERNAL_ALLOWED` table beyond `&["tokio"]` to include the allowlisted llama.cpp bindings crate (naming deferred to `sdd-design`; referred to here as "the bindings crate" — see `local-infer-llamacpp-engine/proposal.md` D3), and adds a new table-only guard test, `INFERENCE_ENGINE_CRATES` (mirroring `TRANSPORT_CRATES` / `ASYNC_RUNTIME_CRATES`), asserting the bindings crate is allowlisted for exactly `runtime`. The dependency is `optional = true`, which does **not** exempt it from the allowlist: `every_crate_declares_exactly_its_allowed_external_dependencies` reads `cargo metadata`, filtered only on `DependencyKind::Normal | Build` — optional dependencies are present in that output regardless of feature activation, so the row edit is mandatory, not cosmetic. `EXPECTED_MEMBERS` is untouched — this change adds no workspace crate; the workspace stays at exactly 16 members. This is the workspace's first optional dependency and first non-pure-Rust (FFI-backed) dependency.

## ADDED Requirements

### Requirement: The External-Dependency Allowlist Admits An Optional Inference-Engine Bindings Crate, Governed Like Any Other External Dependency

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
