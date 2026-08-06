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

### Requirement: Identity Primitives Round-Trip Through Text Or Number

Every ULID-backed newtype produced by the `ulid_newtype!` macro (`ObjectId`, `NodeId`, `RuntimeId`, `WorkloadId`, `AllocationId`, `SessionId`, `TenantId`) MUST expose a fallible constructor that parses its wrapped `Ulid` from text and rejects a string that is not a valid ULID, and MUST expose an accessor that returns that text back out, so a wire-format converter can build the type from an incoming string and serialize it back to one without reaching into the type's private field. `ObjectVersion` (`u64`-backed, not ULID-backed) MUST separately expose a fallible constructor that parses its wrapped `u64` from text — mirroring `worker-wire-contract`'s wire representation, where `ObjectVersion`'s value travels as a proto `string` — and rejects text that is not a valid unsigned 64-bit integer, plus an accessor returning that number back out. No other member of the 12 Fundamental Types gains a new constructor or accessor by this requirement; `ContentHash` already satisfies the same shape (`new(impl Into<String>)` + `digest() -> &str`) and needs no change.

#### Scenario: Valid ULID text parses successfully

- GIVEN a syntactically valid 26-character ULID string
- WHEN it is passed to a ULID-backed newtype's fallible text constructor
- THEN construction succeeds and the resulting value's text accessor returns text equal to the input

#### Scenario: Invalid ULID text is rejected

- GIVEN a string that is not a valid ULID (wrong length, invalid character set, or empty)
- WHEN it is passed to a ULID-backed newtype's fallible text constructor
- THEN construction fails with an error, never panics, and never silently substitutes `Self::default()` or any other stand-in value

#### Scenario: ULID-backed accessor returns the original text

- GIVEN any ULID-backed newtype instance
- WHEN its text accessor is called
- THEN it returns the same 26-character ULID text that `Display` would render for that instance

#### Scenario: ObjectVersion constructs fallibly from numeric text

- GIVEN a string containing a valid unsigned 64-bit integer (e.g. `"42"`)
- WHEN it is passed to `ObjectVersion`'s fallible constructor
- THEN construction succeeds and the resulting value's numeric accessor returns `42`

#### Scenario: ObjectVersion rejects non-numeric text

- GIVEN a string that is not a valid unsigned 64-bit integer (empty, negative, non-digit characters, or a value overflowing `u64`)
- WHEN it is passed to `ObjectVersion`'s fallible constructor
- THEN construction fails with an error, never panics, and never silently substitutes `ObjectVersion::initial()` or any other stand-in value

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
