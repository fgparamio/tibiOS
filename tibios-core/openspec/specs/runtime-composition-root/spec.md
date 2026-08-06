# Composition Root Specification

## Purpose

`runtime` is the workspace's binary crate and Composition Root, implementing the Composition Root section of `02-project-structure.md`.

## Requirements

### Requirement: The Golden Rule — Sole Dependency Exception

`runtime` MAY depend on every other crate in the workspace. No crate MAY depend on `runtime`. This is the sole deliberate exception to the narrow-dependency principle enforced elsewhere in the workspace.

#### Scenario: Runtime may depend on all 15 domain crates

- GIVEN `runtime/Cargo.toml`
- WHEN `cargo metadata` is inspected
- THEN its workspace-crate dependencies may include any or all of the other 15 crates without triggering an architecture guard violation

#### Scenario: No crate depends on runtime

- GIVEN every crate's `Cargo.toml` other than `runtime`
- WHEN `cargo metadata` is inspected
- THEN none of them list `runtime` as a dependency

### Requirement: Hosts The Architecture Guard

`runtime` MUST host the dependency-graph enforcement test at `runtime/tests/architecture_guard.rs`. No separate crate is created for this purpose; `runtime` already legitimately depends on every crate and can freely parse `cargo metadata` for all of them.

#### Scenario: Guard test lives inside the runtime crate

- GIVEN the workspace file tree
- WHEN `runtime/tests/architecture_guard.rs` is located
- THEN it exists inside the `runtime` package's `tests/` directory, not in a standalone crate

### Requirement: No Public Traits In This Change

`runtime/src/main.rs` (or `lib.rs`, if split) MUST be a stub — a doc comment citing `02-project-structure.md`'s Composition Root section — and MUST NOT define public traits or wire domain behavior together yet.

#### Scenario: Crate compiles with only a doc-commented stub

- GIVEN `runtime`'s entry point
- WHEN `cargo check -p runtime` runs
- THEN it succeeds
- AND the file contains no public trait declarations and no cross-domain wiring logic

#### Scenario: Doc comment cites the owning doc section

- GIVEN `runtime`'s entry point
- WHEN its doc comment is read
- THEN it references `02-project-structure.md`'s Composition Root section
