# Delta for runtime-storage

## MODIFIED Requirements

### Requirement: runtime-storage Exposes A Data Family, Still No Public Traits

`runtime-storage/src/lib.rs` MUST carry a crate-level doc comment citing `21-runtime-storage-engine.md` and MUST NOT define public traits — `StreamId` and `Sequence` are plain data types; `append`/`replay` and any backend are deferred. The crate MUST compile.
(Previously: a bare stub with no public items beyond the doc comment.)

#### Scenario: Crate compiles with its data family, no public trait declarations

- GIVEN `runtime-storage/src/lib.rs` and its stream-primitives types
- WHEN `cargo check -p runtime-storage` runs
- THEN it succeeds
- AND the crate declares no public trait

#### Scenario: Doc comment cites the owning doc

- GIVEN `runtime-storage/src/lib.rs`
- WHEN its crate doc comment is read
- THEN it references `21-runtime-storage-engine.md`

## ADDED Requirements

### Requirement: StreamId Identifies A Per-Aggregate Consistency-Domain Stream

`StreamId` MUST be a public type identifying exactly one per-aggregate consistency-domain stream (`21-runtime-storage-engine.md:45`), MUST be constructible, and MUST implement equality comparison. Its internal representation is a design-phase decision, not fixed here.

#### Scenario: StreamId is constructible

- GIVEN a value identifying a stream
- WHEN a `StreamId` is constructed from it
- THEN construction succeeds

#### Scenario: Two StreamIds naming the same stream are equal

- GIVEN two `StreamId` values constructed to name the same stream
- WHEN they are compared for equality
- THEN they are equal

#### Scenario: Two StreamIds naming different streams are not equal

- GIVEN two `StreamId` values constructed to name different streams
- WHEN they are compared for equality
- THEN they are not equal

### Requirement: Sequence Represents A Per-Stream Monotonic Ordinal

`Sequence` MUST be a public type representing a per-stream monotonic ordinal — ordering is guaranteed only within a consistency domain (`21-runtime-storage-engine.md:69`). `Sequence` MUST be constructible and MUST implement ordering comparison. Backing representation and gap policy are explicit design-phase decisions, not fixed here.

#### Scenario: Sequence is constructible

- GIVEN a value representing a position in a stream
- WHEN a `Sequence` is constructed from it
- THEN construction succeeds

#### Scenario: A later Sequence compares greater than an earlier one within the same stream

- GIVEN two `Sequence` values within the same stream, one earlier and one later
- WHEN they are compared
- THEN the later value is greater

### Requirement: The Log Is The Only Authoritative Source (Log-Is-Authority)

Any materialized "current state" view MUST always be a rebuildable projection of the append-only log; the log MUST remain the only authoritative source, per `13-object-model.md:170`, `21-runtime-storage-engine.md:49-51`, and `23-object-store.md:180`. Enforcement here is structural-for-now: this slice defines no "current state" type, so nothing can violate the invariant yet — it becomes testable once append/replay ports and a backend exist (Slices 2-3).

#### Scenario: No current-state type exists to violate the invariant

- GIVEN `runtime-storage`'s public API in this slice
- WHEN its types are enumerated
- THEN none represents a materialized "current state"

### Requirement: runtime-storage Remains Domain-Agnostic

`runtime-storage` MUST NOT define any public type referencing `runtime-object` or assuming any Object Lifecycle concept, and MUST NOT define any public type carrying an opaque or domain-specific payload in this slice. This crate guarantees durability, ordering, and replay of whatever fact it is given; meaning is decided by consumers such as `runtime-object` (`21-runtime-storage-engine.md:13,19`, `23-object-store.md:174-176`). The dependency arrow is `runtime-object → runtime-storage`, never reversed.

#### Scenario: No public type references runtime-object or carries a payload

- GIVEN `runtime-storage`'s public API and `Cargo.toml`
- WHEN its dependency set and public types are inspected
- THEN `runtime-object` is not a dependency, and no public type references it
- AND no public type carries an opaque or domain-specific payload field

## Open Questions (Deferred — Not Answered By This Change)

`runtime-storage` has no authority to validate or interpret facts — deferred to `runtime-object`'s future behavior/Ports phase:

- **Q1 — Legal lifecycle transitions**: deferred to `runtime-object`; unchanged here.
- **Q3 — Monotonic lifecycle progression**: deferred to `runtime-object`; unchanged here.

Resolved by reference, not open: **Q2 — Transition ownership** — `23-object-store.md:174-176` establishes transitions originate in `runtime-object`.
