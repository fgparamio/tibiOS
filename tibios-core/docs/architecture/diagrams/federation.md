# Diagram: Federation

Source: `31-federation.md`.

```mermaid
flowchart TB
    subgraph RuntimeA["Runtime A"]
        IslandA["Trust Island A"]
    end
    subgraph RuntimeB["Runtime B"]
        IslandB["Trust Island B"]
    end
    IslandA <-->|"Federation Trust + Federation Policy"| IslandB
```

```mermaid
stateDiagram-v2
    [*] --> Discovered
    Discovered --> Proposed
    Proposed --> Authorized : bilateral Trust approval
    Authorized --> Active
    Active --> Revoked
    Revoked --> [*]
    note right of Active : Operation invocations and\ncontent crossing permitted\nper Federation Policy
```

Notes: Federation Trust answers "may this Runtime cooperate?" (never "may this Node join?" — that's `22-networking.md`). Federation never removes a Trust Island's boundary; it only authorizes specific interactions across it, routed through the existing Runtime API (`26-runtime-api.md`) and Replication (`24-replication.md`) — never a second protocol.
