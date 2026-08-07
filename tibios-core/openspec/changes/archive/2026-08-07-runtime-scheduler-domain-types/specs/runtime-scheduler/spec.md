# Delta for runtime-scheduler

## MODIFIED Requirements

### Requirement: runtime-scheduler Exposes A Data Family, Still No Public Traits

`runtime-scheduler/src/lib.rs` MUST carry a crate-level doc comment citing both `14-resource-model.md` and `16-scheduling-engine.md`, and MUST NOT define public traits — `Resource`, `Candidate`, `FilterResult`, `Score`, and `AllocationPlan` are plain data types; `FilterPolicy`/`ScoringPolicy`/`SchedulingStrategy` and any Port are deferred. The crate MUST compile.
(Previously: a bare stub with no public items beyond the doc comment.)

#### Scenario: Crate compiles with its data family, no public trait declarations

- GIVEN `runtime-scheduler/src/lib.rs` and its scheduling-domain types
- WHEN `cargo check -p runtime-scheduler` runs
- THEN it succeeds
- AND the crate declares no public trait

#### Scenario: Doc comment cites both owning docs

- GIVEN `runtime-scheduler/src/lib.rs`
- WHEN its crate doc comment is read
- THEN it references both `14-resource-model.md` and `16-scheduling-engine.md`

## ADDED Requirements

### Requirement: Resource Describes Observable Capacity, Never Allocation State

`Resource` MUST be a public type representing assignable capacity as a specialized Logical Object — identity is `ObjectId`+`ObjectVersion` (`14-resource-model.md`). `Resource` MUST expose only observable capacity/capability data. `Resource` MUST NOT carry any field describing current workload assignment, reservation, lease, or scheduler-internal bookkeeping — those are owned by `runtime-allocation` (`15-allocation-model.md`).

#### Scenario: Resource is constructible from its identity and capacity

- GIVEN an `ObjectId`, an `ObjectVersion`, and a capacity value
- WHEN a `Resource` is constructed from them
- THEN construction succeeds and the identity and capacity are retrievable

#### Scenario: Resource carries no allocation-owned field

- GIVEN `Resource`'s public fields and accessors
- WHEN they are enumerated
- THEN none represents current workload, reservation, or lease state

### Requirement: Candidate Represents A Resource Under Evaluation

`Candidate` MUST be a public type pairing a `Resource` with the identity of the Node offering it, for use during Candidate Discovery (`16-scheduling-engine.md`). `Candidate` MUST be constructible.

#### Scenario: Candidate is constructible from a Node and a Resource

- GIVEN a `NodeId` and a `Resource`
- WHEN a `Candidate` is constructed from them
- THEN construction succeeds and both are retrievable

### Requirement: FilterResult Distinguishes Feasible From Infeasible, With A Reason

`FilterResult` MUST be a public enum with exactly two variants: `Feasible` and `Infeasible` carrying a reason. This is a hard boolean outcome, never a score (`16-scheduling-engine.md`'s Filter/Score separation).

#### Scenario: An infeasible result carries its reason

- GIVEN a `FilterResult::Infeasible` constructed with a reason
- WHEN the reason is read back
- THEN it matches what was supplied

### Requirement: Score Is A Continuous, Comparable Scoring Output

`Score` MUST be a public type representing a Scoring Policy's continuous output and MUST implement a total ordering usable for ranking candidates (`16-scheduling-engine.md`'s Score phase).

#### Scenario: A higher Score compares greater than a lower one

- GIVEN two `Score` values, one higher and one lower
- WHEN they are compared
- THEN the higher value is greater

### Requirement: AllocationPlan Is The Scheduler's Pure-Function Output

`AllocationPlan` MUST be a public type representing the Scheduling Engine's output — a `WorkloadId` bound to a `Candidate`, per `15-allocation-model.md`'s producer-owns-data-contract rule (the Scheduler owns this type, not `runtime-allocation`). `AllocationPlan` MUST be constructible.

#### Scenario: AllocationPlan is constructible from a Workload and a Candidate

- GIVEN a `WorkloadId` and a `Candidate`
- WHEN an `AllocationPlan` is constructed from them
- THEN construction succeeds and both are retrievable

## Open Questions (Deferred — Not Answered By This Change)

- **Full capability taxonomy** (GPU/CUDA/Metal/ROCm/etc.): `Resource`'s capacity/capability representation stays minimal this slice; a richer typed vocabulary is future work once a real Filter Policy needs it.
- **Scheduling Metadata on `AllocationPlan`** (`Priority`, `Cost`, `Affinity`, `Locality Score`, `Energy Score`, `Rack Preference`, `AI Placement Score`, dependency list): deferred to the future Ports/behavior change — `AllocationPlan` in this slice carries only its core `WorkloadId`+`Candidate` binding, same "intentionally partial" precedent as `runtime-allocation`'s `AllocationContract`.
