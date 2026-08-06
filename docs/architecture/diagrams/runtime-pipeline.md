# Diagram: Runtime Pipeline & Knowledge/Work Planes

Source: `11-runtime.md` (operational pipeline), `24-replication.md` (knowledge plane / work plane).

## Operational pipeline

```mermaid
flowchart TB
    RuntimeReality["Runtime Reality"] --> StateAssembler["State Assembler"]
    StateAssembler --> ClusterSummary["Cluster Summary"]
    StateAssembler --> ClusterSnapshot["Cluster Snapshot"]

    Client --> Admission
    ClusterSummary --> Admission
    Admission --> Scheduling
    ClusterSnapshot --> Scheduling
    Scheduling --> Allocation
    Allocation --> ExecutionContext["Execution Context"]
    ExecutionContext --> Worker
    Worker --> ExecutionEvents["Execution Events"]
    Worker --> ExecutionReport["Execution Report"]
```

## Knowledge plane vs. work plane

```mermaid
flowchart LR
    subgraph Knowledge["Knowledge Plane"]
        Object --> ObjectStore["Object Store"] --> Replication
    end
    subgraph Work["Work Plane"]
        Admission2["Admission"] --> Scheduling2["Scheduling"] --> Allocation2["Allocation"] --> Worker2["Worker"]
    end
    Knowledge -->|"meet in"| ExecutionContext2["Execution Context"]
    Work -->|"meet in"| ExecutionContext2
```

Notes: the State Assembler is a continuous side-process, never a per-request step — Admission consults the coarse Cluster Summary, Scheduling consults the full Cluster Snapshot, both derived from the same observation. The two planes are independent and intersect exactly once, inside the Execution Context.
