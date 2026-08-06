# TibiOS Architecture Glossary

This glossary is reference documentation, not specification. It defines nothing. Every entry points to the document that owns the term; if a definition ever needs to change, it changes there, and this file updates only its pointer or short summary.

The glossary never redefines. It only indexes.

| Term | Defined in | Owning Domain | Short Definition |
|---|---|---|---|
| Authority | `00-philosophy.md` | Philosophy | The exclusive right to modify a piece of state. |
| Consistency Domain | `00-philosophy.md` | Philosophy | The scope within which an authoritative fact is coordinated; never shared across domains. |
| Authoritative State | `00-philosophy.md` | Philosophy | Facts that cannot be reconstructed by observing reality again; must be persisted. |
| Observational State | `00-philosophy.md` | Philosophy | State that can be re-derived by observing reality; never requires authoritative persistence. |
| Volatility | `00-philosophy.md` | Philosophy | The natural rate of change of a category of state; determines its consistency strategy. |
| Runtime Primitives | `02-project-structure.md` | Project Structure | Infrastructure-neutral shared types/operations/generators used across all domains (`runtime-primitives` crate). |
| Inbound Port | `02-project-structure.md` | Project Structure | The public capabilities a domain offers to the rest of the Runtime. |
| Outbound Port | `02-project-structure.md` | Project Structure | The external capabilities a domain requires, defined by the consuming domain. |
| Composition Root | `02-project-structure.md` | Project Structure | The `runtime` crate; the sole place concrete implementations are wired together. |
| Data Contract | `02-project-structure.md` | Project Structure | Immutable information exchanged between domains; owned by the producer. |
| Service Contract | `02-project-structure.md` | Project Structure | A capability one domain requires of another; owned by the consumer. |
| NodeId | `02-project-structure.md` | Project Structure | Identity of a single machine participating in a Runtime. |
| RuntimeId | `02-project-structure.md` | Project Structure | Identity of a Runtime instance, independent of the Nodes currently composing it. |
| Runtime | `11-runtime.md` | Runtime | The composition of every domain; turns independent Tibi Box nodes into one logical computer. |
| Workload | `11-runtime.md` | Runtime | The fundamental unit of execution the Runtime accepts. |
| Runtime Pipeline | `11-runtime.md` | Runtime | The path a Workload travels: Admission → Scheduling → Allocation → Worker. |
| Knowledge Plane | `24-replication.md` | Replication | Object → Object Store → Replication; the chain that resolves and moves content. |
| Work Plane | `24-replication.md` | Replication | Admission → Scheduling → Allocation → Worker; the chain that executes Workloads. |
| Object | `13-object-model.md` | Object Model | The universal abstraction for every entity the Runtime manages. |
| Logical Object | `13-object-model.md` | Object Model | A mutable, versioned, named reference (`ObjectId` + `ObjectVersion`). |
| Content Object | `13-object-model.md` | Object Model | Immutable content addressed by `ContentHash`. |
| Physical Replica | `13-object-model.md` | Object Model | One or more physical copies of a Content Object's bytes; an implementation detail. |
| Configuration Object | `13-object-model.md` | Object Model | A persisted, versioned Object of type Configuration — distinct from Deployment Configuration (`29-deployment.md`). |
| ObjectId | `02-project-structure.md` | Runtime Primitives | Identity of a Logical Object. |
| ContentHash | `02-project-structure.md` | Runtime Primitives | Identity of a Content Object. |
| Resource | `14-resource-model.md` | Resource Model | The Scheduler's language for describing assignable capacity. |
| Capability | `14-resource-model.md` | Resource Model | A typed hardware/platform trait of a Resource or Worker (GPU, CUDA, VRAM, …) — distinct from a Worker Capability (`18-worker-model.md`). |
| Capacity | `14-resource-model.md` | Resource Model | The observed scalar quantity of a Resource currently available. |
| Allocation | `15-allocation-model.md` | Allocation Model | A temporary assignment of Resource capacity to a Workload. |
| Allocation Plan | `15-allocation-model.md` | Allocation Model | The Scheduler's proposed placement, not yet materialized. |
| Allocation Contract | `15-allocation-model.md` | Allocation Model | The immutable, authoritative terms the Runtime commits to honoring for an Allocation. |
| Scheduling Engine | `16-scheduling-engine.md` | Scheduling Engine | The pure function that decides where a Workload should execute. |
| Filter | `16-scheduling-engine.md` | Scheduling Engine | A hard, boolean eligibility check on a placement Candidate. |
| Score | `16-scheduling-engine.md` | Scheduling Engine | A soft, continuous ranking of an already-feasible Candidate. |
| Cluster Snapshot | `17-cluster-snapshot.md` | Cluster Snapshot | An immutable observation of the cluster at a point in time, used for planning. |
| Cluster Generation | `17-cluster-snapshot.md` | Cluster Snapshot | Observability metadata for topology-level events; never used to validate a Plan. |
| Worker | `18-worker-model.md` | Worker Model | The domain that executes a Workload; owns nothing but execution. |
| Execution Context | `18-worker-model.md` | Worker Model | The immutable bundle a Worker receives to execute: Workload, Allocation Contract, resolved dependencies. |
| Worker Capability | `18-worker-model.md` | Worker Model | The behavior an Execution Context requests the Worker perform (e.g. `chat.generate`) — distinct from a Capability (`14-resource-model.md`). |
| Execution Channel | `18-worker-model.md` | Worker Model | The Runtime-owned conduit a Worker emits Execution Events through. |
| Execution Event | `18-worker-model.md` | Worker Model | A fact describing execution as it unfolds. |
| Execution Report | `18-worker-model.md` | Worker Model | The terminal, authoritative summary of a completed execution. |
| Execution Pulse | `18-worker-model.md` | Worker Model | Health signal for a single execution, distinct from process/node health. |
| State Assembler | `19-state-assembler.md` | State Assembler | The continuous process turning Runtime reality into Cluster Summary and Cluster Snapshot. |
| Cluster Summary | `19-state-assembler.md` / `20-admission-control.md` | State Assembler | The coarse, cluster-wide view Admission consumes — cheaper than a full Cluster Snapshot. |
| Admission | `20-admission-control.md` | Admission Control | The domain deciding whether a Workload may enter the scheduling pipeline. |
| Admission Record | `20-admission-control.md` | Admission Control | The authoritative fact produced by an admission decision. |
| Quota Account / Quota Actor | `20-admission-control.md` | Admission Control | Per-scope partitioned administrative token tracking, never a global counter. |
| Runtime Storage Engine | `21-runtime-storage-engine.md` | Storage Engine | Infrastructure-neutral persistence for authoritative facts. |
| Authoritative Event Stream | `21-runtime-storage-engine.md` | Storage Engine | A per-aggregate, append-only log of authoritative facts. |
| Content Store | `21-runtime-storage-engine.md` | Storage Engine | Immutable, hash-addressed byte storage for Content Objects. |
| Networking | `22-networking.md` | Networking | The domain providing authenticated communication between Runtime instances. |
| Session | `22-networking.md` | Networking | An authenticated communication relationship between two Runtime instances. |
| Trust | `22-networking.md` | Networking | The domain that authorizes a Node's participation, distinct from authentication. |
| Membership | `22-networking.md` | Networking | Whether a trusted Node currently belongs to the cluster. |
| Health | `22-networking.md` / `17-cluster-snapshot.md` | Networking | Whether a member Node can currently execute work. |
| Runtime Event | `02-project-structure.md` | Project Structure | A published fact describing something that has already happened; never a command. |
| Object Store | `23-object-store.md` | Object Store | The `runtime-object` service resolving Object identity into content, resolved through `runtime-storage`. |
| Replication | `24-replication.md` | Replication | The domain guaranteeing accessible copies of Content Objects across the cluster. |
| Replica Availability | `24-replication.md` | Replication | Whether a Physical Replica exists, is reachable, and satisfies policy — never "consistency". |
| Replication Policy | `24-replication.md` | Replication | Authoritative configuration expressing desired replica placement; Pull remains sufficient without it. |
| Trust Island | `31-federation.md` | Federation | The set of Nodes sharing one `RuntimeId` and one Trust authority. |
| AI Runtime | `25-ai-runtime.md` | AI Runtime | The demonstration that AI workload execution is a specialization of the existing Runtime, introducing no new primitives. |
| Runtime API | `26-runtime-api.md` | Runtime API | The single public capability surface through which external consumers address the Runtime. |
| Runtime API Surface | `26-runtime-api.md` | Runtime API | The finite, technology-independent set of operations the Runtime exposes. |
| Runtime API Operation | `26-runtime-api.md` | Runtime API | A single named, typed operation on the Runtime API Surface (e.g. Submit Workload). |
| SDK | `27-sdk.md` | SDK | A typed, per-language projection pattern of the Runtime API; no canonical implementation. |
| CLI | `28-cli.md` | CLI | A human-command projection pattern of the Runtime API; no canonical implementation. |
| Deployment | `29-deployment.md` | Deployment | The domain deciding whether a Runtime instance exists, with what configuration, for how long. |
| Deployment Unit | `29-deployment.md` | Deployment | Runtime + Configuration + Identity — the smallest thing Deployment creates and destroys. |
| Deployment Configuration | `29-deployment.md` | Deployment | Pre-existence deployment input consumed by the Composition Root — distinct from a Configuration Object (`13-object-model.md`). |
| AI Service | `30-ai-services.md` | AI Services | A Service Object (`13-object-model.md`) whose workload performs an AI task; introduces no new Object kind. |
| Federation | `31-federation.md` | Federation | The domain governing cooperation between two independent Runtimes. |
| Federation Member | `31-federation.md` | Federation | An entire Runtime, identified by `RuntimeId`, participating in Federation — never a Node. |
| Federation Trust | `31-federation.md` | Federation | Authorization that an entire Runtime may cooperate with another — distinct from Node-level Trust. |
| Federation Membership | `31-federation.md` | Federation | The durable, authoritative, bilateral relationship produced by Federation Trust. |
| Federation Policy | `31-federation.md` | Federation | Authoritative configuration scoping what an authorized Federation Membership permits. |

## Rule

If a term appears in more than one document with the same name but a different meaning, that is a defect in the corpus, not in this glossary — report it against the two documents involved, following the same terminology-collision process already used for `Configuration` and `Capability`.
