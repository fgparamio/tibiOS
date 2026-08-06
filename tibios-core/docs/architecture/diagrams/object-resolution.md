# Diagram: Object Resolution

Source: `13-object-model.md` (identity model), `23-object-store.md` (resolution service).

```mermaid
flowchart TB
    ObjectId --> LogicalObject["Logical Object (ObjectId + ObjectVersion)"]
    LogicalObject --> ContentObject["Content Object (ContentHash)"]
    ContentObject --> ContentStore["Content Store (21-runtime-storage-engine.md)"]

    subgraph ObjectStoreSvc["Object Store (runtime-object)"]
        direction TB
        Resolve["Resolve ObjectId → ContentHash"]
        Verify["Verify Physical Replica exists locally"]
    end

    ObjectId -.-> Resolve
    Resolve -.-> Verify
    Verify -->|"missing"| Replication["Replication (24-replication.md)"]
    Verify -->|"present"| ContentStore
```

Notes: the Object Store is the canonical, sole entry point — no Runtime component queries `runtime-storage` directly to discover a Content Object. A missing local Physical Replica falls through to Replication's Pull mechanism, never to a second resolution path.
