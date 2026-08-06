# TibiOS Runtime Architecture

Version: 2.0

## Purpose

The Runtime is what turns a collection of independent Tibi Box nodes into a single logical computer. Applications describe *what* should execute; the Runtime decides *whether*, *where*, *when*, and *how* it executes.

The Runtime is not a scheduler, not a storage engine, not a network stack, and not an execution engine. It is the composition of all of them — each owned by a dedicated domain, wired together at the Composition Root (`02-project-structure.md`). The Runtime itself makes no eligibility decisions, no placement decisions, no allocation decisions, and executes no Workload directly. It owns none of the domain logic described in `13-object-model.md`–`22-networking.md`; it owns the fact that those domains cooperate correctly.

Diagrams: `diagrams/runtime-overview.md`, `diagrams/runtime-pipeline.md`.

This document is the map. It shows how every domain fits together and why the pipeline has the shape it has. It does not redefine Ownership, Identity, or the Authoritative/Observational distinction — those belong to `00-philosophy.md`. Each domain's internal detail belongs to its own document (`13-object-model.md`–`22-networking.md`).

## Runtime Responsibilities

The Runtime owns:

- The Composition Root — wiring every domain's Inbound and Outbound Ports together (`02-project-structure.md`).
- The end-to-end lifecycle of a Workload, from submission to Historical Fact: `WorkloadState` moves `Created → Scheduled → Running → Completed/Failed → Recovered`, the Runtime-wide state referenced by `18-worker-model.md`'s Worker-local lifecycle (a separate, finer-grained state machine — the two are never merged).
- Nothing beyond coordination. No scheduling, admission, allocation, or execution logic lives in the Runtime itself — it lives in the domain that owns that question.

The Runtime delegates:

- Eligibility to Admission.
- Observation to State Assembler.
- Placement to Scheduling.
- Commitment to Allocation.
- Execution to Workers.
- Authentication, Sessions, and Transport to Networking.
- Durability to Storage.

A Runtime feature request that cannot be phrased as "which domain should own this?" usually means the feature does not belong in the Runtime at all.

## Runtime Domains

Not every domain listed here owns a numbered document. A domain is an architectural ownership boundary; a document is where that boundary happens to be written down. Trust, Membership, and Health are first-class domains with their own ownership — they are documented inside `22-networking.md` as the domains Networking's published facts feed, not because they belong to Networking.

| Domain | Owns | Document |
|---|---|---|
| Object | Universal identity and lifecycle for everything the Runtime manages | `13-object-model.md` |
| Resource | The language for describing assignable capacity | `14-resource-model.md` |
| Trust | Who is authorized? | documented in `22-networking.md` |
| Networking | Authentication, Sessions, Transport | `22-networking.md` |
| Membership | Who belongs? | documented in `22-networking.md` |
| Health | Who can execute? | documented in `17-cluster-snapshot.md`, `19-state-assembler.md`, `22-networking.md` |
| Admission | Whether? | `20-admission-control.md` |
| State Assembler | Turning Runtime reality into immutable, consistent observations | `19-state-assembler.md` |
| Scheduling | Where? | `16-scheduling-engine.md` |
| Allocation | Committing planned placement into real, temporary capacity | `15-allocation-model.md` |
| Worker | Executing a Workload | `18-worker-model.md` |
| Storage | Durable persistence of authoritative facts | `21-runtime-storage-engine.md` |
| Observability | Making every domain's behavior inspectable | `09-observability.md` |

Every Runtime domain answers exactly one architectural question. No two domains answer the same question, and no architectural question goes unanswered. This table is the Ownership principle from `00-philosophy.md` applied to the Runtime as a whole.

## The Runtime Pipeline

```
                    Runtime Reality
                          │
                          ▼
                  State Assembler
                  ┌────────┴────────┐
                  ▼                 ▼
          Cluster Summary    Cluster Snapshot
                  │                 │
                  ▼                 ▼
Client → Admission ─────────→ Scheduling
                               │
                               ▼
                          Allocation
                               │
                               ▼
                      Execution Context
                               │
                               ▼
                            Worker
                               │
                      ┌────────┴────────┐
                      ▼                 ▼
              Execution Events   Execution Report
```

The State Assembler is not a step a request passes through — it runs continuously, independent of any single Workload, turning Runtime reality into two derived views at different granularity: a coarse **Cluster Summary** for Admission, and a full **Cluster Snapshot** for Scheduling (`19-state-assembler.md`, `20-admission-control.md`). A request never waits for a Snapshot to be built; it consults whichever view already exists.

Every arrow is a change of ownership, not an implementation call. Admission decides *whether*. Scheduling decides *where*. Allocation decides *whether that placement can become real*. The Worker decides *nothing architectural* — it executes exactly what it was given (`18-worker-model.md`).

## The Runtime as a Knowledge Transformer

The Runtime's execution pipeline transforms knowledge through a sequence of progressively more specialized representations. Each transformation has exactly one owner.

```
Supporting Domains
──────────────────────────────────────────────
Trust · Networking · Membership · Health · Object · Resource · Observability

                    │
                    ▼

        Knowledge Transformation Pipeline

Reality
    │
    ▼
Observation
    │
    ▼
Eligibility
    │
    ▼
Planning
    │
    ▼
Commitment
    │
    ▼
Execution
    │
    ▼
Historical Fact
```

| Form of Knowledge | Owner |
|---|---|
| Reality | Runtime |
| Observation | State Assembler |
| Eligibility | Admission |
| Planning | Scheduling |
| Commitment | Allocation |
| Execution | Worker |
| Historical Fact | Storage |

Supporting domains such as Trust, Networking, Membership, Health, Object, Resource, and Observability enable this pipeline, but they do not participate directly in the transformation from observation to execution. Their responsibility is to answer independent architectural questions whose results feed or constrain the pipeline — not to occupy a stage within it.

This is why the Runtime's execution pipeline is divided into these stages. Each stage exists because a distinct form of knowledge requires a distinct owner. Merging two stages would force one domain to answer unrelated architectural questions, violating the Ownership principle defined in `00-philosophy.md`.

## Runtime State

Three distinct forms of knowledge coexist in the Runtime at any moment, and confusing them is the single most common architectural mistake this document exists to prevent (`00-philosophy.md`):

- **Reality** — what is actually true right now (a node's live CPU load, an in-flight execution). It is never directly shared; it can only be observed.
- **Observation** — a consistent, immutable snapshot of reality at a point in time (a Cluster Summary, a Cluster Snapshot, `17-cluster-snapshot.md`). It is always slightly stale, by design, and never mistaken for reality itself.
- **Authoritative Facts** — durably persisted records that cannot be reconstructed by observing reality again (an Admission Record, a Trust event, an Allocation Contract, `21-runtime-storage-engine.md`). These are the only things recovery ever replays.

Every piece of Runtime knowledge belongs to exactly one of these three categories.

## Ownership

Every architectural question in the Runtime has exactly one domain that answers it, and every domain answers exactly one question (`00-philosophy.md`). This document does not restate that principle — the Runtime Domains table above and the Knowledge Transformer are that principle, applied twice: once to *who decides*, once to *what changes hands*.

## Relationship Between Runtime Domains

Domains cooperate through Data Contracts, Service Contracts, and Runtime Events (`02-project-structure.md`). A domain never reaches into another domain's state — it publishes what it knows, and interested domains observe it (`00-philosophy.md`'s State Propagation). Regardless of the mechanism, domains never mutate another domain's state directly.

The pipeline above shows the common case. It is not the only shape of cooperation — Trust revokes independently of any in-flight request (`22-networking.md`), Health changes independently of any Workload — but every cooperation, common or exceptional, follows the same rule: publish a fact, never invoke another domain's internals.

## Runtime Philosophy

Observe.
Admit.
Plan.
Commit.
Execute.
Persist.

Six verbs, six owners, one Runtime. Nothing in TibiOS executes without first being observed, admitted, planned, and committed — and nothing that happened is ever lost, because every commitment becomes a fact before it becomes an action.
