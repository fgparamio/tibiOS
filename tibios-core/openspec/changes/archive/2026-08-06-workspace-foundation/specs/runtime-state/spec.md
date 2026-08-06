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

### Requirement: Stub Crate, No Public Traits

`runtime-state/src/lib.rs` MUST be a stub with a crate-level doc comment citing `17-cluster-snapshot.md` and `19-state-assembler.md`, and MUST NOT define public traits.

#### Scenario: Crate compiles with only a doc-commented stub

- GIVEN `runtime-state/src/lib.rs`
- WHEN `cargo check -p runtime-state` runs
- THEN it succeeds
- AND the file contains no public trait declarations

#### Scenario: Doc comment cites both owning docs

- GIVEN `runtime-state/src/lib.rs`
- WHEN its crate doc comment is read
- THEN it references both `17-cluster-snapshot.md` and `19-state-assembler.md`
