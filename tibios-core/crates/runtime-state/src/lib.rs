//! The State domain's data family: `ClusterGeneration`, `HealthState`,
//! `NodeState`, `AllocationSummary`, `ClusterSnapshot`. No Ports yet — the
//! State Assembler's Trust -> Membership -> Health -> Resources pipeline
//! and any policy are a future change.
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

use runtime_primitives::{AllocationId, NodeId, Timestamp, WorkloadId};
use runtime_scheduler::Resource;

/// Monotonic snapshot counter, mirroring `ObjectVersion`'s shape
/// (`17-cluster-snapshot.md`). This is observability/topology metadata
/// only — it MUST NEVER be used to validate an individual Allocation Plan.
/// A Plan is invalidated only by changes to the objects it depends on,
/// never by a global generation counter (`17-cluster-snapshot.md:105`). No
/// public API in this crate pairs a `ClusterGeneration` with an
/// `AllocationPlan`, a `Candidate`, or an admission decision. `Ord`
/// answers only "which observation is more recent" — never plan validity.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct ClusterGeneration(u64);

impl ClusterGeneration {
    /// The generation of a freshly initialized cluster.
    #[must_use]
    pub const fn initial() -> Self {
        Self(0)
    }

    /// Pure Operation: the next generation in sequence — deterministic, no
    /// side effects, no I/O.
    #[must_use]
    pub const fn next(&self) -> Self {
        Self(self.0 + 1)
    }

    /// Infallible numeric constructor, mirroring `ObjectVersion::from_u64`.
    #[must_use]
    pub const fn from_u64(value: u64) -> Self {
        Self(value)
    }

    /// Accessor returning the wrapped `u64`, the counterpart to
    /// `from_u64`.
    #[must_use]
    pub const fn as_u64(&self) -> u64 {
        self.0
    }
}

impl Default for ClusterGeneration {
    fn default() -> Self {
        Self::initial()
    }
}

/// A Node's or Resource's coarse health. Unlike the exhaustively specified
/// `ObjectType`/`ObjectLifecycle`, this variant set is **inferred from
/// passing prose in `14-resource-model.md`, not doc-mandated** — Health's
/// real owning domain (`22-networking.md`'s `HealthChanged` event, or a
/// future security/membership crate) may revise it. `Draining` is
/// deliberately excluded: it is Membership's state
/// (`16-scheduling-engine.md:71`), and re-deriving it here would violate
/// `19-state-assembler.md`'s one-stage-one-question pipeline discipline.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HealthState {
    /// Fully operational — no degradation, no internal errors observed.
    Healthy,
    /// Operational but exhibiting load or internal-error degradation.
    Degraded,
    /// Not operationally fit.
    Unhealthy,
}

/// Pairs a Node's identity, its coarse health, and the Resource(s) it
/// offers (`17-cluster-snapshot.md`'s Snapshot Contents). Reuses
/// `runtime_scheduler::Resource` directly — no parallel `ResourceState`
/// type is defined in this crate. Carries no Trust, Membership, or
/// capability field: a Node appearing in a `ClusterSnapshot` is
/// trusted-and-a-member by construction (`19-state-assembler.md`), and
/// Trust/Membership decisions remain owned by their respective domains.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NodeState {
    node: NodeId,
    health: HealthState,
    resources: Vec<Resource>,
}

impl NodeState {
    /// Builds a `NodeState` from a Node's identity, observed health, and
    /// the Resource(s) it offers.
    #[must_use]
    pub fn new(node: NodeId, health: HealthState, resources: Vec<Resource>) -> Self {
        Self {
            node,
            health,
            resources,
        }
    }

    /// This Node's identity.
    #[must_use]
    pub const fn node(&self) -> NodeId {
        self.node
    }

    /// This Node's observed health.
    #[must_use]
    pub const fn health(&self) -> HealthState {
        self.health
    }

    /// The Resource(s) this Node offers.
    #[must_use]
    pub fn resources(&self) -> &[Resource] {
        &self.resources
    }
}

/// Pairs an Allocation's identity with the Workload it serves
/// (`17-cluster-snapshot.md`'s Snapshot Contents). Intentionally minimal —
/// carries no Allocation-owned lifecycle, status, phase, or timestamp
/// field; that state stays `runtime-allocation`'s (`15-allocation-model.md`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct AllocationSummary {
    allocation: AllocationId,
    workload: WorkloadId,
}

impl AllocationSummary {
    /// Pairs an Allocation with the Workload it serves.
    #[must_use]
    pub const fn new(allocation: AllocationId, workload: WorkloadId) -> Self {
        Self {
            allocation,
            workload,
        }
    }

    /// The Allocation this summary describes.
    #[must_use]
    pub const fn allocation(&self) -> AllocationId {
        self.allocation
    }

    /// The Workload this Allocation serves.
    #[must_use]
    pub const fn workload(&self) -> WorkloadId {
        self.workload
    }
}

/// A complete, atomically-published observation of the Cluster's Nodes and
/// Allocations at a point in time (`17-cluster-snapshot.md`). `created_at`
/// completes the identity triple `17-cluster-snapshot.md:55` names
/// alongside `generation` — `snapshot_id` remains blocked on minting a
/// `SnapshotId` primitive and is deferred; neither `generation` nor
/// `created_at` is an identity substitute for it. Carries no cluster
/// topology or Runtime capabilities field this slice. Immutable by
/// construction: a single all-fields constructor and read-only accessors
/// make a partially-assembled Snapshot unrepresentable
/// (`19-state-assembler.md:53` forbids partial publication).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ClusterSnapshot {
    generation: ClusterGeneration,
    created_at: Timestamp,
    nodes: Vec<NodeState>,
    allocations: Vec<AllocationSummary>,
}

impl ClusterSnapshot {
    /// Builds a complete `ClusterSnapshot` from all of its parts at once —
    /// there is no incremental builder, so a partially-assembled Snapshot
    /// is not representable.
    #[must_use]
    pub fn new(
        generation: ClusterGeneration,
        created_at: Timestamp,
        nodes: Vec<NodeState>,
        allocations: Vec<AllocationSummary>,
    ) -> Self {
        Self {
            generation,
            created_at,
            nodes,
            allocations,
        }
    }

    /// This Snapshot's generation counter.
    #[must_use]
    pub const fn generation(&self) -> ClusterGeneration {
        self.generation
    }

    /// The wall-clock time this Snapshot was created.
    #[must_use]
    pub const fn created_at(&self) -> Timestamp {
        self.created_at
    }

    /// The Nodes observed in this Snapshot.
    #[must_use]
    pub fn nodes(&self) -> &[NodeState] {
        &self.nodes
    }

    /// The Allocation summaries observed in this Snapshot.
    #[must_use]
    pub fn allocations(&self) -> &[AllocationSummary] {
        &self.allocations
    }
}

#[cfg(test)]
mod tests {
    use super::{AllocationSummary, ClusterGeneration, ClusterSnapshot, HealthState, NodeState};
    use runtime_primitives::{
        AllocationId, NodeId, ObjectId, ObjectVersion, Timestamp, WorkloadId,
    };
    use runtime_scheduler::Resource;

    #[test]
    fn initial_generation_is_zero() {
        assert_eq!(ClusterGeneration::initial().as_u64(), 0);
    }

    #[test]
    fn next_advances_by_one_and_is_pure() {
        let generation = ClusterGeneration::from_u64(4);
        assert_eq!(generation.next().as_u64(), 5);
        assert_eq!(generation.next().as_u64(), 5);
    }

    #[test]
    fn from_u64_and_as_u64_round_trip() {
        assert_eq!(ClusterGeneration::from_u64(17).as_u64(), 17);
    }

    #[test]
    fn a_later_generation_compares_greater_than_an_earlier_one() {
        let earlier = ClusterGeneration::from_u64(1);
        let later = ClusterGeneration::from_u64(2);
        assert!(later > earlier);
    }

    #[test]
    fn default_equals_initial() {
        assert_eq!(ClusterGeneration::default(), ClusterGeneration::initial());
    }

    #[test]
    fn health_state_variants_are_distinct_and_copy() {
        let healthy = HealthState::Healthy;
        let degraded = HealthState::Degraded;
        let unhealthy = HealthState::Unhealthy;

        let healthy_copy = healthy;
        assert_ne!(healthy, degraded);
        assert_ne!(degraded, unhealthy);
        assert_ne!(healthy, unhealthy);
        assert_eq!(healthy, healthy_copy);
    }

    #[test]
    fn node_state_round_trips_its_fields_with_multiple_resources() {
        let node = NodeId::new();
        let health = HealthState::Degraded;
        let resources = vec![
            Resource::new(ObjectId::new(), ObjectVersion::initial(), 4),
            Resource::new(ObjectId::new(), ObjectVersion::initial(), 8),
        ];

        let node_state = NodeState::new(node, health, resources.clone());

        assert_eq!(node_state.node(), node);
        assert_eq!(node_state.health(), health);
        assert_eq!(node_state.resources(), resources.as_slice());
    }

    #[test]
    fn node_state_with_no_resources_is_representable() {
        let node_state = NodeState::new(NodeId::new(), HealthState::Healthy, Vec::new());
        assert!(node_state.resources().is_empty());
    }

    #[test]
    fn allocation_summary_round_trips_its_fields() {
        let allocation = AllocationId::new();
        let workload = WorkloadId::new();

        let summary = AllocationSummary::new(allocation, workload);

        assert_eq!(summary.allocation(), allocation);
        assert_eq!(summary.workload(), workload);
    }

    #[test]
    fn cluster_snapshot_round_trips_its_fields() {
        let generation = ClusterGeneration::from_u64(3);
        let created_at = Timestamp::from_millis(1_000);
        let nodes = vec![NodeState::new(
            NodeId::new(),
            HealthState::Healthy,
            vec![Resource::new(ObjectId::new(), ObjectVersion::initial(), 2)],
        )];
        let allocations = vec![AllocationSummary::new(
            AllocationId::new(),
            WorkloadId::new(),
        )];

        let snapshot =
            ClusterSnapshot::new(generation, created_at, nodes.clone(), allocations.clone());

        assert_eq!(snapshot.generation(), generation);
        assert_eq!(snapshot.created_at(), created_at);
        assert_eq!(snapshot.nodes(), nodes.as_slice());
        assert_eq!(snapshot.allocations(), allocations.as_slice());
    }

    #[test]
    fn an_empty_cluster_snapshot_is_representable() {
        let snapshot = ClusterSnapshot::new(
            ClusterGeneration::initial(),
            Timestamp::from_millis(0),
            Vec::new(),
            Vec::new(),
        );

        assert!(snapshot.nodes().is_empty());
        assert!(snapshot.allocations().is_empty());
    }

    #[test]
    fn cluster_snapshot_equality_is_structural() {
        let generation = ClusterGeneration::from_u64(1);
        let created_at = Timestamp::from_millis(42);
        let node = NodeId::new();
        let allocation = AllocationId::new();
        let workload = WorkloadId::new();

        let first = ClusterSnapshot::new(
            generation,
            created_at,
            vec![NodeState::new(node, HealthState::Healthy, Vec::new())],
            vec![AllocationSummary::new(allocation, workload)],
        );
        let second = ClusterSnapshot::new(
            generation,
            created_at,
            vec![NodeState::new(node, HealthState::Healthy, Vec::new())],
            vec![AllocationSummary::new(allocation, workload)],
        );

        assert_eq!(first, second);
    }
}
