# Diagram: Runtime Overview

Source: `11-runtime.md`. Every Runtime domain, grouped by whether it participates in the knowledge-transformation pipeline or supports it.

```mermaid
flowchart TB
    subgraph Pipeline["Knowledge Transformation Pipeline"]
        direction LR
        Reality --> Observation --> Eligibility --> Planning --> Commitment --> Execution --> HistoricalFact["Historical Fact"]
    end

    subgraph Owners["Owning Domain per Stage"]
        direction LR
        RuntimeD["Runtime"] -.-> StateAssembler["State Assembler"] -.-> Admission -.-> Scheduling -.-> Allocation -.-> Worker -.-> Storage
    end

    subgraph Supporting["Supporting Domains"]
        direction LR
        Trust
        Networking
        Membership
        Health
        Object["Object Model"]
        Resource["Resource Model"]
        Observability
    end

    Supporting -. enables .-> Pipeline
```

Notes: the top row is the abstract knowledge chain (`11-runtime.md`'s Knowledge Transformer); the middle row is the owner of each stage; the bottom row lists domains that feed or constrain the pipeline without occupying a stage in it (`11-runtime.md`'s Runtime Domains table).
