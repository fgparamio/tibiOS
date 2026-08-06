# Diagram: Scheduling Engine

Source: `16-scheduling-engine.md`.

```mermaid
flowchart TB
    TrustedNodes["Trusted Nodes (Trust)"] --> ClusterMembership["Cluster Membership"]
    ClusterMembership --> HealthyNodes["Healthy Nodes (Health)"]
    HealthyNodes --> ClusterSnapshot["Cluster Snapshot (19-state-assembler.md)"]
    ClusterSnapshot --> CandidateDiscovery["Candidate Discovery"]
    CandidateDiscovery --> CapabilityFilter["Capability Filter"]
    CapabilityFilter -->|"feasible"| ScoringPolicies["Scoring Policies"]
    CapabilityFilter -->|"infeasible"| Rejected["Rejected (reason recorded)"]
    ScoringPolicies --> AllocationPlan["Allocation Plan"]
    AllocationPlan --> AllocationMaterializer["Allocation Materializer (15-allocation-model.md)"]
```

Notes: Filter answers "can it?" (hard, boolean); Score answers "how good?" (soft, continuous) — never combined into one weighted number. Trust, Membership, and Health are each answered exactly once, upstream, never re-checked inside the Scheduling Engine.
