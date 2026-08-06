# Diagram: Document Dependency Graph

Source: derived from every document's own cross-references. Shows which documents a given document depends on (never the reverse — the corpus is acyclic, following `02-project-structure.md`'s Dependency Rule applied to documentation itself).

```mermaid
flowchart TB
    P00["00-philosophy"]
    P02["02-project-structure"]
    P11["11-runtime"]

    P00 --> P02
    P00 --> P11
    P02 --> P11

    subgraph Core["Runtime Domain Series (13-22)"]
        P13["13-object-model"]
        P14["14-resource-model"]
        P15["15-allocation-model"]
        P16["16-scheduling-engine"]
        P17["17-cluster-snapshot"]
        P18["18-worker-model"]
        P19["19-state-assembler"]
        P20["20-admission-control"]
        P21["21-runtime-storage-engine"]
        P22["22-networking"]
    end
    P11 --> Core
    P14 --> P13
    P15 --> P14
    P16 --> P15
    P17 --> P16
    P19 --> P17
    P20 --> P19
    P21 --> P20
    P22 --> P21

    P23["23-object-store"] --> P13
    P23 --> P21
    P24["24-replication"] --> P23
    P24 --> P22
    P25["25-ai-runtime"] --> P13
    P25 --> P14
    P25 --> P16
    P25 --> P18
    P25 --> P23
    P25 --> P24

    P26["26-runtime-api"] --> P25
    P27["27-sdk"] --> P26
    P28["28-cli"] --> P26
    P29["29-deployment"] --> P02
    P30["30-ai-services"] --> P13
    P30 --> P18
    P30 --> P25
    P30 --> P26
    P30 --> P29
    P31["31-federation"] --> P22
    P31 --> P24
    P31 --> P26
    P31 --> P29
```

Notes: `27-sdk` and `28-cli` both depend only on `26-runtime-api` — never on each other, per the star-graph rule in `29-deployment.md`'s Ownership section. This graph is documentation-only; it does not imply a Cargo crate dependency graph, though the two are closely related (see `02-project-structure.md`'s own Dependency Graph).
