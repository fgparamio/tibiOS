//! The Scheduling domain's data family: `Resource`, `Candidate`,
//! `FilterResult`, `Score`, `AllocationPlan`. No Ports yet —
//! `FilterPolicy`/`ScoringPolicy`/`SchedulingStrategy` and any placement
//! algorithm are a future change.
//!
//! Implements `14-resource-model.md` and `16-scheduling-engine.md`.

use runtime_primitives::{NodeId, ObjectId, ObjectVersion, WorkloadId};

/// Assignable capacity, specialized from the Object Model: identity is
/// `ObjectId` + `ObjectVersion` (`14-resource-model.md`), never a separate
/// `ResourceId`. `capacity` is observational state only — this type carries
/// no current-workload, reservation, or lease field; that state belongs to
/// `runtime-allocation` (`15-allocation-model.md`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Resource {
    id: ObjectId,
    version: ObjectVersion,
    capacity: u64,
}

impl Resource {
    /// Builds a `Resource` from its identity and observed capacity.
    #[must_use]
    pub const fn new(id: ObjectId, version: ObjectVersion, capacity: u64) -> Self {
        Self {
            id,
            version,
            capacity,
        }
    }

    /// This Resource's identity, independent of its version.
    #[must_use]
    pub const fn id(&self) -> ObjectId {
        self.id
    }

    /// This Resource's current version.
    #[must_use]
    pub const fn version(&self) -> ObjectVersion {
        self.version
    }

    /// The observed capacity this Resource currently offers.
    #[must_use]
    pub const fn capacity(&self) -> u64 {
        self.capacity
    }
}

/// A `Resource` under evaluation during Candidate Discovery
/// (`16-scheduling-engine.md`) — which Node offers which Resource.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Candidate {
    node: NodeId,
    resource: Resource,
}

impl Candidate {
    /// Pairs a Node with the Resource it offers.
    #[must_use]
    pub const fn new(node: NodeId, resource: Resource) -> Self {
        Self { node, resource }
    }

    /// The Node offering this Candidate's Resource.
    #[must_use]
    pub const fn node(&self) -> NodeId {
        self.node
    }

    /// The Resource under evaluation.
    #[must_use]
    pub const fn resource(&self) -> &Resource {
        &self.resource
    }
}

/// The Filter phase's hard, boolean outcome — never a score
/// (`16-scheduling-engine.md`'s Filter/Score separation).
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FilterResult {
    /// The candidate satisfies every hard requirement.
    Feasible,
    /// The candidate fails a hard requirement, with an explanation.
    Infeasible(String),
}

/// The Score phase's continuous output (`16-scheduling-engine.md`). Wraps
/// `f64`; ordering is total via `f64::total_cmp`, so no constructor needs to
/// reject `NaN`.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Score(f64);

impl Score {
    /// Builds a `Score` from its raw value.
    #[must_use]
    pub const fn new(value: f64) -> Self {
        Self(value)
    }

    /// The wrapped value.
    #[must_use]
    pub const fn value(&self) -> f64 {
        self.0
    }
}

impl Eq for Score {}

impl PartialOrd for Score {
    fn partial_cmp(&self, other: &Self) -> Option<core::cmp::Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for Score {
    fn cmp(&self, other: &Self) -> core::cmp::Ordering {
        self.0.total_cmp(&other.0)
    }
}

/// The Scheduling Engine's pure-function output — a Data Contract it owns,
/// not `runtime-allocation` (`15-allocation-model.md`'s producer-owns-data-
/// contract rule). Carries only its core `WorkloadId`+`Candidate` binding
/// this slice; Scheduling Metadata (`Priority`, `Cost`, `Affinity`, ...) and
/// declared dependencies are deferred, same "intentionally partial"
/// precedent as `runtime-allocation`'s `AllocationContract`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AllocationPlan {
    workload: WorkloadId,
    candidate: Candidate,
}

impl AllocationPlan {
    /// Binds a Workload to the Candidate chosen to run it.
    #[must_use]
    pub const fn new(workload: WorkloadId, candidate: Candidate) -> Self {
        Self {
            workload,
            candidate,
        }
    }

    /// The Workload this Plan places.
    #[must_use]
    pub const fn workload(&self) -> WorkloadId {
        self.workload
    }

    /// The Candidate chosen to run it.
    #[must_use]
    pub const fn candidate(&self) -> &Candidate {
        &self.candidate
    }
}

#[cfg(test)]
mod tests {
    use super::{AllocationPlan, Candidate, FilterResult, Resource, Score};
    use runtime_primitives::{NodeId, ObjectId, ObjectVersion, WorkloadId};

    #[test]
    fn resource_round_trips_its_fields() {
        let id = ObjectId::new();
        let version = ObjectVersion::initial();
        let resource = Resource::new(id, version, 42);

        assert_eq!(resource.id(), id);
        assert_eq!(resource.version(), version);
        assert_eq!(resource.capacity(), 42);
    }

    #[test]
    fn candidate_round_trips_its_fields() {
        let node = NodeId::new();
        let resource = Resource::new(ObjectId::new(), ObjectVersion::initial(), 8);
        let candidate = Candidate::new(node, resource);

        assert_eq!(candidate.node(), node);
        assert_eq!(candidate.resource(), &resource);
    }

    #[test]
    fn filter_result_infeasible_round_trips_its_reason() {
        let result = FilterResult::Infeasible("insufficient GPU memory".to_string());
        assert_eq!(
            result,
            FilterResult::Infeasible("insufficient GPU memory".to_string())
        );
    }

    #[test]
    fn a_higher_score_compares_greater_than_a_lower_one() {
        let lower = Score::new(0.3);
        let higher = Score::new(0.9);
        assert!(higher > lower);
    }

    #[test]
    fn allocation_plan_round_trips_its_fields() {
        let workload = WorkloadId::new();
        let candidate = Candidate::new(
            NodeId::new(),
            Resource::new(ObjectId::new(), ObjectVersion::initial(), 4),
        );
        let plan = AllocationPlan::new(workload, candidate.clone());

        assert_eq!(plan.workload(), workload);
        assert_eq!(plan.candidate(), &candidate);
    }
}
