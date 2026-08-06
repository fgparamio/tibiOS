# Runtime Primitives Specification

## Purpose

`runtime-primitives` holds the 12 fundamental identity/value types shared across every domain. It is the workspace's most stable, minimal crate and implements `02-project-structure.md`.

## Requirements

### Requirement: Exhaustive Dependency Set

`runtime-primitives` MUST depend on no other workspace crate. Its external (non-workspace) dependencies MUST be a subset of `{serde, ulid}`.

#### Scenario: No workspace dependencies

- GIVEN `runtime-primitives/Cargo.toml`
- WHEN `cargo metadata` is inspected
- THEN it lists zero workspace-crate dependencies

#### Scenario: External deps stay within the allowlist

- GIVEN `runtime-primitives/Cargo.toml`
- WHEN its `[dependencies]` are read
- THEN every entry is `serde`, `ulid`, or a transitive dependency of those crates

### Requirement: The 12 Fundamental Types

`runtime-primitives` MUST define exactly these newtypes: `ObjectId`, `NodeId`, `RuntimeId`, `WorkloadId`, `AllocationId`, `SessionId`, `TenantId`, `Lease`, `Timestamp`, `ContentHash`, `ObjectVersion`, `ErrorClass`, each newtype-wrapped over a ULID unless documented otherwise.

#### Scenario: All 12 types are public

- GIVEN `runtime-primitives/src/lib.rs`
- WHEN its public API is inspected
- THEN all 12 named types are exported

### Requirement: Zero Domain Logic

`runtime-primitives` MUST contain no domain/business logic — only type definitions, their trivial constructors, and trait impls needed for identity/serialization (e.g. `serde::Serialize`).

Adding a primitive type is an architectural change, not an implementation detail: precedent is that adding `RuntimeId` required reopening `02-project-structure.md`. Any future addition to this set MUST follow the same path.

#### Scenario: No behavioral methods beyond identity/serialization

- GIVEN `runtime-primitives/src/lib.rs`
- WHEN its type definitions are reviewed
- THEN no method implements scheduling, allocation, storage, or other domain behavior

### Requirement: No Public Traits In This Change

`runtime-primitives` MUST NOT define public trait definitions (Inbound Ports) as part of this change; trait/port design is an explicit follow-up change.

#### Scenario: No trait declarations beyond derives

- GIVEN `runtime-primitives/src/lib.rs`
- WHEN inspected
- THEN it contains no hand-written `trait` declarations

### Requirement: Ownership Documented

`runtime-primitives/src/lib.rs` MUST carry a crate-level doc comment citing `02-project-structure.md` as the architecture document it implements.

#### Scenario: Doc comment cites owning doc

- GIVEN `runtime-primitives/src/lib.rs`
- WHEN its crate doc comment is read
- THEN it references `02-project-structure.md`
