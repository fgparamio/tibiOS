# State Domain Specification

## Purpose

`runtime-state` is the stub for the State domain, implementing `17-cluster-snapshot.md` and `19-state-assembler.md`.

## Requirements

### Requirement: Exhaustive Dependency Set

`runtime-state` MUST depend on exactly `runtime-primitives`, `runtime-object`, `runtime-scheduler`, and `runtime-network` among workspace crates, and on no other workspace crate.

#### Scenario: Declared dependencies match the allowed set

- GIVEN `runtime-state/Cargo.toml`
- WHEN `cargo metadata` is inspected
- THEN its workspace-crate dependencies are exactly `runtime-primitives`, `runtime-object`, `runtime-scheduler`, and `runtime-network`

### Requirement: The Network Dependency Is Data-Contract-Only

The dependency on `runtime-network` MUST exist only because the State Assembler consumes the Runtime Events that Networking publishes (`TrustRevoked`, `PeerReachabilityChanged`, `SessionEstablished`/`SessionClosed`, `MemberJoined`/`MemberLeft`, `HealthChanged`). `runtime-state` MUST NEVER reference Networking's Transport or Session internals — this is the same exception pattern `02-project-structure.md` already grants `runtime-allocation → runtime-scheduler` for the `AllocationPlan`/`Resource` types.

The exact shape of this dependency (whether these event types get hoisted into `runtime-primitives`) is open for the trait-design follow-up change — do not resolve here.

#### Scenario: Only event/data-contract types are referenced

- GIVEN `runtime-state`'s stub declares its dependency on `runtime-network`
- WHEN the crate's intent is reviewed
- THEN the documented rationale names only the event types above, never Transport/Session types

### Requirement: runtime-state Exposes A Data Family, Still No Public Traits

`runtime-state/src/lib.rs` MUST carry a crate-level doc comment citing both `17-cluster-snapshot.md` and `19-state-assembler.md`, and MUST NOT define public traits — `ClusterGeneration`, `HealthState`, `NodeState`, `AllocationSummary`, and `ClusterSnapshot` are plain data types; the State Assembler pipeline, any Port, and any policy are deferred. The crate MUST compile.
(Previously: a bare stub with no public items beyond the doc comment.)

#### Scenario: Crate compiles with its data family, no public trait declarations

- GIVEN `runtime-state/src/lib.rs` and its Cluster Snapshot domain types
- WHEN `cargo check -p runtime-state` runs
- THEN it succeeds
- AND the crate declares no public trait

#### Scenario: Doc comment cites both owning docs

- GIVEN `runtime-state/src/lib.rs`
- WHEN its crate doc comment is read
- THEN it references both `17-cluster-snapshot.md` and `19-state-assembler.md`

### Requirement: ClusterGeneration Is Topology Metadata, Never A Plan Validity Token

`ClusterGeneration` MUST be a public type representing a monotonic snapshot counter, mirroring `ObjectVersion`'s shape (`17-cluster-snapshot.md`). `ClusterGeneration`'s doc comment MUST state explicitly that it is observability/topology metadata only and MUST NEVER be used to validate an individual Allocation Plan. No public API MAY pair a `ClusterGeneration` with an `AllocationPlan` or an admission decision.

#### Scenario: ClusterGeneration is constructible and monotonic

- GIVEN a numeric generation value
- WHEN a `ClusterGeneration` is constructed from it
- THEN construction succeeds and the value is retrievable

#### Scenario: Doc comment states the plan-validation guardrail

- GIVEN `ClusterGeneration`'s doc comment
- WHEN it is read
- THEN it states the type is never used to validate an Allocation Plan

### Requirement: HealthState Is An Inferred, Revisable Enum

`HealthState` MUST be a public enum representing a Node's or Resource's coarse health, with a minimal variant set inferred from `14-resource-model.md`'s informal prose (`Draining`, `Unhealthy`, and at least one healthy variant). `HealthState`'s doc comment MUST flag explicitly that its variants are inferred, not doc-mandated — unlike the exhaustively specified `ObjectType`/`ObjectLifecycle` — and MAY be revised once Health's real owning domain is built out.

#### Scenario: HealthState variants are constructible and comparable

- GIVEN each `HealthState` variant
- WHEN two variants are compared for equality
- THEN equal variants compare equal and distinct variants compare unequal

#### Scenario: Doc comment flags the enum as inferred, not doc-mandated

- GIVEN `HealthState`'s doc comment
- WHEN it is read
- THEN it states the variant set is inferred from prose, not exhaustively doc-mandated

### Requirement: NodeState Pairs Identity, Health, And Reused Resource Data

`NodeState` MUST be a public type pairing a `NodeId`, a `HealthState`, and the Node's `runtime_scheduler::Resource`(s) (`17-cluster-snapshot.md`'s Snapshot Contents). `NodeState` MUST reuse `runtime_scheduler::Resource` directly and MUST NOT define a parallel `ResourceState` type.

#### Scenario: NodeState is constructible from a NodeId, HealthState, and Resources

- GIVEN a `NodeId`, a `HealthState`, and one or more `runtime_scheduler::Resource` values
- WHEN a `NodeState` is constructed from them
- THEN construction succeeds and all three are retrievable

#### Scenario: NodeState carries no parallel Resource type

- GIVEN `NodeState`'s public fields and accessors
- WHEN they are enumerated
- THEN the resource data is exactly `runtime_scheduler::Resource`, and no `ResourceState` type exists anywhere in the crate

### Requirement: AllocationSummary Is Intentionally Minimal, No Lifecycle Field

`AllocationSummary` MUST be a public type pairing an `AllocationId` and a `WorkloadId`, per `17-cluster-snapshot.md`'s Snapshot Contents. `AllocationSummary` MUST NOT carry any Allocation-owned lifecycle, status, phase, or timestamp field — that state stays `runtime-allocation`'s.

#### Scenario: AllocationSummary is constructible from an AllocationId and a WorkloadId

- GIVEN an `AllocationId` and a `WorkloadId`
- WHEN an `AllocationSummary` is constructed from them
- THEN construction succeeds and both are retrievable

#### Scenario: AllocationSummary carries no lifecycle field

- GIVEN `AllocationSummary`'s public fields and accessors
- WHEN they are enumerated
- THEN none represents Allocation status, phase, or timestamp state

### Requirement: ClusterSnapshot Composes Generation, Creation Timestamp, Nodes, And Allocation Summaries

`ClusterSnapshot` MUST be a public type composed of a `ClusterGeneration`, a `Timestamp` (`created_at`), a `Vec<NodeState>`, and a `Vec<AllocationSummary>` (`17-cluster-snapshot.md`). `ClusterSnapshot` MUST NOT carry a `snapshot_id`, cluster topology, or Runtime capabilities field this slice — those are deferred.

#### Scenario: ClusterSnapshot is constructible from a generation, creation timestamp, nodes, and allocation summaries

- GIVEN a `ClusterGeneration`, a `Timestamp`, a `Vec<NodeState>`, and a `Vec<AllocationSummary>`
- WHEN a `ClusterSnapshot` is constructed from them
- THEN construction succeeds and all four are retrievable

#### Scenario: ClusterSnapshot carries no deferred field

- GIVEN `ClusterSnapshot`'s public fields and accessors
- WHEN they are enumerated
- THEN none represents `snapshot_id`, cluster topology, or Runtime capabilities

## Open Questions (Deferred — Not Answered By This Change)

- **`snapshot_id`**: blocked on minting a `SnapshotId` primitive, an architectural change to `runtime-primitives`/`02-project-structure.md`, same category as the precedent of adding `RuntimeId` — not this slice's call.
- **Cluster topology and Runtime capabilities**: listed in `17-cluster-snapshot.md`'s Snapshot Contents with zero doc elaboration; deferred, same "intentionally partial" precedent as `runtime-scheduler`'s deferred capability taxonomy.
- **The State Assembler / Trust → Membership → Health → Resources pipeline** (`19-state-assembler.md`) and any Port or policy: future trait-design follow-up, not this data-only slice.
