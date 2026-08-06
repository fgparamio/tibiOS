# Diagram: Deployment

Source: `29-deployment.md`.

```mermaid
flowchart TB
    subgraph Outside["Outside the process — Deployment"]
        Decide["Decide a Runtime instance should exist"]
        Config["Select Configuration"]
        Launch["Launch the Runtime process"]
        Shutdown["Later request shutdown"]
        Decide --> Config --> Launch
    end

    subgraph Inside["Inside the process — Composition Root (02-project-structure.md)"]
        Startup["Runtime Startup"]
        Wire["Composition Root wiring"]
        Execute["Runtime Execution"]
        StopSeq["Runtime Shutdown"]
        Startup --> Wire --> Execute --> StopSeq
    end

    Launch -->|"process boundary"| Startup
    Shutdown -->|"process boundary"| StopSeq
```

```mermaid
stateDiagram-v2
    [*] --> Defined
    Defined --> Configured
    Configured --> Launching
    Launching --> Running
    Running --> Stopping
    Stopping --> Removed
    Removed --> [*]
    note right of Running : Opaque from Deployment's\nperspective — governed\nexclusively by the Runtime
```

Notes: Deployment decides that a Runtime instance exists; the Composition Root decides how it comes to life. `Running` is intentionally opaque to Deployment — everything inside it is `02-project-structure.md`'s responsibility.
