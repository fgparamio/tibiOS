//! Stub for the State domain.
//!
//! Implements `17-cluster-snapshot.md` and `19-state-assembler.md`.
//!
//! The dependency on `runtime-network` is data-contract-only: the State
//! Assembler consumes the Runtime Events Networking publishes
//! (`TrustRevoked`, `PeerReachabilityChanged`, `SessionEstablished`/
//! `SessionClosed`, `MemberJoined`/`MemberLeft`, `HealthChanged`). This
//! crate must never reference Networking's Transport or Session internals —
//! the same exception pattern `02-project-structure.md` grants
//! `runtime-allocation -> runtime-scheduler` for `AllocationPlan`/`Resource`.
