# Diagram: Replication

Source: `24-replication.md`.

```mermaid
flowchart TB
    ContentRequired["Content Object required"] --> ResolveHash["Object Store: resolve ContentHash"]
    ResolveHash --> HasReplica{"Physical Replica already held?"}
    HasReplica -->|"yes"| Available["Physical Replica available"]
    HasReplica -->|"no"| LocateNode["Locate a node holding one (via Object Store)"]
    LocateNode --> TrustCheck{"Authorized by Trust?"}
    TrustCheck -->|"no"| Refuse["Refuse"]
    TrustCheck -->|"yes"| Pull["Pull Content Object"]
    Pull --> Available

    Policy["Replication Policy (optional)"] -.->|"pre-position"| Pull
```

Notes: Pull is the sole fundamental mechanism, sufficient alone for correctness. Push exists only as policy layered on top, never a second mechanism. Crossing a Trust Island always requires explicit Federation authorization (`31-federation.md`).
