# Delta for runtime-object

## MODIFIED Requirements

### Requirement: runtime-object Exposes A Data Family, Still No Public Traits

`runtime-object/src/lib.rs` MUST carry a crate-level doc comment citing `13-object-model.md` and `23-object-store.md`, and MUST NOT define public traits — `ObjectType`, `ObjectLifecycle`, `LogicalObject`, and `ContentObject` are plain enums and structs, not trait-based ports; behavior and Ports (`ObjectStore`, resolution) are deferred to a future change. The crate MUST compile.
(Previously: the crate was a bare stub with no public items at all beyond the doc comment.)

#### Scenario: Crate compiles with its data family, no public trait declarations

- GIVEN `runtime-object/src/lib.rs` and its data-family types
- WHEN `cargo check -p runtime-object` runs
- THEN it succeeds
- AND the crate declares no public trait

#### Scenario: Doc comment cites both owning docs

- GIVEN `runtime-object/src/lib.rs`
- WHEN its crate doc comment is read
- THEN it references both `13-object-model.md` and `23-object-store.md`

## ADDED Requirements

### Requirement: ObjectType Is A Closed Enum Naming The Ten Object Categories

`ObjectType` MUST be a public Rust enum with exactly ten variants — `Workload`, `Message`, `Actor`, `Service`, `Dataset`, `Tensor`, `Checkpoint`, `Configuration`, `Artifact`, `Model` — corresponding one-to-one to the categories `13-object-model.md:102` enumerates.

#### Scenario: ObjectType has exactly ten variants matching the doc

- GIVEN the `ObjectType` type definition
- WHEN its variants are enumerated
- THEN there are exactly ten, matching `13-object-model.md`'s category list one-to-one

### Requirement: ObjectLifecycle Is A Closed Enum With No Transition Behavior

`ObjectLifecycle` MUST be a public Rust enum with exactly eight variants — `Created`, `Validated`, `Registered`, `Available`, `Referenced`, `Updated`, `Archived`, `Deleted` — corresponding to `13-object-model.md:73-96`'s lifecycle diagram. `ObjectLifecycle` MUST NOT implement `Default` and MUST NOT define or carry any `transition`, `can_transition`, or `validate` method — legality of transitions, ownership of transitions, and monotonic progression are explicitly out of scope for this data-family phase (see Open Questions).

#### Scenario: ObjectLifecycle has exactly eight variants

- GIVEN the `ObjectLifecycle` type definition
- WHEN its variants are enumerated
- THEN there are exactly eight: `Created`, `Validated`, `Registered`, `Available`, `Referenced`, `Updated`, `Archived`, `Deleted`

#### Scenario: ObjectLifecycle does not implement Default

- GIVEN the `ObjectLifecycle` type definition
- WHEN its trait implementations are inspected
- THEN `Default` is not implemented for it

#### Scenario: ObjectLifecycle carries no transition method

- GIVEN `runtime-object`'s public API
- WHEN `ObjectLifecycle`'s inherent methods and trait impls are inspected
- THEN no `transition`, `can_transition`, or `validate` method exists anywhere on it

### Requirement: LogicalObject Is Immutable Data Combining Identity, Version, Content Reference, And Type

`LogicalObject` MUST be a public, immutable Rust struct carrying exactly an `ObjectId`, an `ObjectVersion`, a `ContentHash` (the Content Object it currently points to), and an `ObjectType`. `LogicalObject` MUST implement `Clone` and MUST NOT contain interior mutability. `LogicalObject` MUST be trivially constructible in a unit test with no async runtime and no transport dependency.

#### Scenario: LogicalObject exposes its four fields via accessors

- GIVEN a constructed `LogicalObject` value
- WHEN its identity, version, content reference, and type accessors are called
- THEN each returns exactly the value supplied at construction

#### Scenario: LogicalObject derives or implements Clone

- GIVEN the `LogicalObject` type definition
- WHEN its derive list or trait impls are inspected
- THEN `Clone` is implemented for it

#### Scenario: LogicalObject is constructible in a unit test without an async runtime or transport

- GIVEN a test module inside `runtime-object`
- WHEN it constructs a `LogicalObject` value using only public constructors
- THEN the test compiles and passes without starting an async runtime and without depending on any transport type

### Requirement: ContentObject Carries Only Content Identity, Never A Back-Reference To LogicalObject

`ContentObject` MUST be a public, immutable Rust struct carrying exactly a `ContentHash` as its identity. `ContentObject` MUST NOT contain a field of type `ObjectId`, `LogicalObject`, or any other type that would let it name "its" owning Logical Object — the reference direction is `LogicalObject → ContentHash` only, never the reverse, so that many `LogicalObject`s (including unrelated ones, and multiple versions of the same one) MAY reference the same `ContentObject` without `ContentObject` needing to change. `ContentObject` MUST implement `Clone` and MUST NOT contain interior mutability.

#### Scenario: ContentObject has no back-reference field

- GIVEN the `ContentObject` type definition
- WHEN its fields are enumerated
- THEN none is of type `ObjectId`, `LogicalObject`, or any type that references a Logical Object

#### Scenario: Two distinct LogicalObjects may reference the same ContentObject

- GIVEN two `LogicalObject` values with different `ObjectId`s
- WHEN both are constructed with the same `ContentHash` value
- THEN both constructions succeed and neither `LogicalObject` nor the shared `ContentHash` rejects the sharing

#### Scenario: ContentObject derives or implements Clone

- GIVEN the `ContentObject` type definition
- WHEN its derive list or trait impls are inspected
- THEN `Clone` is implemented for it

## Open Questions (Deferred — Not Answered By This Change)

This spec defines `ObjectLifecycle`'s state values only; it makes no claim about any of the following, which belong to a future Ports/behavior change:

- **Q1 — Legal lifecycle transitions**: which of the eight states may follow which? Can any be skipped or reversed?
- **Q2 — Transition ownership**: which component drives each lifecycle transition — `runtime-object`, Scheduler, Storage Engine, or the requesting consumer?
- **Q3 — Monotonic lifecycle progression**: can a state (e.g. `Created`) ever recur for the same Object after later states have already occurred?
