# TibiOS Scheduling Engine

Version: 2.0

## Purpose

The Scheduling Engine decides where a Workload should execute. It never decides whether a Workload is admitted (`20-admission-control.md`) and never materializes an Allocation (`15-allocation-model.md`) — it only plans.

This document follows the principles in `00-philosophy.md` and `02-project-structure.md`. It does not redefine Ownership, Object identity, or the Ports & Adapters model.

Diagram: `diagrams/scheduling.md`.

## The Scheduler Coordinates. Policies Decide.

The Scheduling Engine never makes placement decisions directly. Decisions belong to small, independent Policies, each answering exactly one question: Capacity, Locality, Latency, Cost, Energy, NUMA, GPU/Capability, Maintenance-window awareness. New policies (Carbon Footprint, Rack Temperature, LLM Affinity) are added without touching the Scheduling Engine itself.

## Filter and Score: Two Phases, Not One

A Policy answers two different questions, and conflating them is a correctness bug, not a style choice: "Can this candidate even run this?" (Filter — hard, boolean) is a different question from "how good is this candidate?" (Score — soft, continuous). A weighted average of scores can silently "rescue" a candidate that fails a hard requirement (e.g. insufficient GPU memory) if its other scores are high enough — this is exactly why Kubernetes' Scheduling Framework separates Filter and Score into distinct phases, and TibiOS does the same.

```rust
trait FilterPolicy {
    fn filter(&self, candidate: &Candidate) -> FilterResult; // Feasible | Infeasible(reason)
}

trait ScoringPolicy {
    fn score(&self, candidate: &Candidate) -> Score;
}
```

Separate traits, not one `SchedulingPolicy` with both methods — a Policy that only filters (e.g. minimum GPU capacity) should not need to implement an unused `score()`, and vice versa (e.g. preferring lower energy consumption among already-feasible nodes). `score()` never runs on an infeasible candidate.

`Infeasible(reason)` also buys explainability for free: "Node A: ❌ GPU memory too small. Node B: ❌ Capability mismatch. Node C: ✔ Candidate, Score 0.91" is far more useful than a bare `0.0`.

## Trust, Membership, and Capability Are Answered Once, Upstream

The Scheduling Engine operates only on Runtime-approved candidates. It never performs cluster membership or node authentication checks — those are answered exactly once, by their respective owners, before a node ever appears as a candidate:

```
Trusted Nodes (Trust/Networking)
        │
        ▼
Cluster Membership (Membership)
        │
        ▼
Healthy Nodes (Health)
        │
        ▼
Cluster Snapshot (State Assembler, 19-state-assembler.md)
        │
        ▼
Candidate Discovery
        │
        ▼
Capability Filter (Filter phase)
        │
        ▼
Scoring Policies (Score phase)
        │
        ▼
Allocation Plan
        │
        ▼
Allocation Materializer
```

The Allocation Materializer belongs to `15-allocation-model.md`, not to the Scheduling Engine — it is shown here only so the reader can see exactly where this document's responsibility ends.

What was previously called "Security Filter" is renamed **Capability Filter** — it is not a security decision (that already happened upstream), it is a hardware/platform compatibility check: GPU, CUDA, Metal, AVX-512, RDMA, SGX, TPM, ARM SVE, minimum Runtime version. A trusted node can lack a capability; a capable node still had to pass Trust first — these are orthogonal questions, each answered exactly once.

A previously-listed "Maintenance Policy" Filter is removed for the same reason: it duplicated what Membership's `Draining` state already answers. If a *predictive* maintenance-aware Score is needed later ("avoid scheduling long Workloads where maintenance is imminent"), that is a Scoring Policy about risk, not a Filter repeating current state.

The cascading reduction this produces is significant in practice: 1000 machines → 987 authenticated → 945 healthy → 120 with GPU → 18 with sufficient VRAM → 5 meet affinity → only then Score.

## The Scheduling Engine Is a Pure Function

`(Cluster Snapshot, Workload Requirements) → AllocationPlan`. It never reserves Resources, never touches Workers, never creates Allocations, never mutates Runtime state. The Scheduling Engine consumes Data Contracts; it never invokes Runtime services during planning — a direct consequence of the hexagonal architecture in `02-project-structure.md`. This enables simulation, deterministic tests (property-testing with `proptest`, per `06-testing.md`), comparing two algorithms against identical state, and reproducible/explainable decisions.

## Optimistic Concurrency, Validated by Dependency

Planning assumes the Cluster Snapshot remains valid; materialization verifies that assumption — but **per the specific dependencies the Plan declares** (the Resource(s) and Object(s) it references, each with an observed Object Version or Content Hash — see `13-object-model.md` and `17-cluster-snapshot.md`), never against a single global counter. A global "did anything change anywhere?" check would invalidate a Plan on every unrelated heartbeat in a large cluster, making retry the common case instead of the exception — this was an actual granularity bug caught and fixed during design (see `17-cluster-snapshot.md`'s Cluster Generation).

## Retry Strategy

Allocation Plan invalidation is expected under concurrent Runtime evolution — it does not mean plans normally fail. The Runtime retries planning using a newer Snapshot. Retries are bounded, observable, exponentially backed off, and jittered — infinite retries are forbidden (`05-async-concurrency.md`).

## Known MVP Limitation

Optimistic scheduling without preemption can starve large resource requests under sustained contention. This is accepted for Phase 1 (see `15-allocation-model.md`) and does not require changing this model to fix later — preemption, reservation windows, workload aging, and fairness policies extend it without redefining it.

## Observability

Every scheduling operation records Snapshot ID, candidate count, Filter decisions (with reasons), Score breakdown, the resulting Allocation Plan, and planning duration. Every rejected candidate records the Filter that rejected it. Scheduling decisions are fully explainable.

## Relationship with Allocation

Scheduling produces Allocation Plans. Allocation decides whether those Plans become Allocation Contracts (`15-allocation-model.md`). Scheduling never observes Allocation Runtime State and never reserves Resources.

## Relationship with Admission

Scheduling assumes the Workload has already been admitted (`20-admission-control.md`). Admission determines whether planning may begin; Scheduling determines where execution should occur. These remain independent questions.

## Anti-Patterns

Avoid: a monolithic scheduling algorithm instead of composable Policies, mixing Filter and Score into one weighted computation, re-checking Trust/Membership/Health inside the Scheduling Engine, global-counter-based plan invalidation, the Scheduling Engine touching live Runtime state.

## Principles

- Schedulers plan. Allocators commit.
- Filter answers "can it?" Scoring answers "how good?" — never mixed into one number.
- The Scheduling Engine is a pure function of a Cluster Snapshot.
- A Plan is invalidated only by changes to the objects it depends on.
- Trust, Membership, and Capability are three independent questions, each answered exactly once, upstream of scheduling.
- Planning is deterministic. Materialization is authoritative.

## Motto

Reject early. Plan only what deserves planning. Never schedule invalid work. Never plan on moving ground.
