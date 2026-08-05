# TibiOS Federation

Version: 1.0

## Purpose

Federation answers a question no other document has answered: **how do two independent TibiOS Runtimes cooperate?** It is not Membership (`22-networking.md`, which governs Nodes joining a single cluster), not Replication (`24-replication.md`, which moves content once cooperation is already authorized), and not a merger — federating two Runtimes never produces one Runtime; both retain independent identity, independent Trust, and independent Storage.

Federation closes a reference `13-object-model.md` left open since it was written: *"replication across islands requires explicit authorization... see trust boundaries in `22-networking.md`"* — a concept `22` never fully defined, because it lacked the identity to define it with. This document supplies that identity and completes the definition.

## Ownership

Federation owns its own crate, `runtime-federation` — a genuinely new architectural language (Federation Member, Trust Island, Federation Policy), unlike the composition documents (`25`, `30`) that preceded it in Block 2. It consumes Trust, Networking, Replication, Deployment, and the Runtime API through their existing outbound contracts (`22-networking.md`, `24-replication.md`, `29-deployment.md`, `26-runtime-api.md`). Federation governs cooperation between Runtimes; it never reimplements what any of those domains already do within one.

## Core Principles

- Federation answers whether two Runtimes may cooperate — never whether a Node may join a cluster (`22`), and never whether content should cross (`24`).
- A Federation Member is an entire Runtime, identified by `RuntimeId` (`02-project-structure.md`), never a Node.
- Federation never reimplements Discovery, Authentication, Sessions, or Transport — `22-networking.md` remains the sole authority over all four.
- Federation never invents a second inter-Runtime protocol. All Federation communication uses the existing Runtime API surface (`26-runtime-api.md`), subject to Federation authorization.
- Trust at Node granularity and Trust at Runtime granularity are independent authorization decisions. Neither implies the other.
- Federation governs cooperation. Networking governs communication.

## Runtime Identity

Every Runtime instance has exactly one `RuntimeId` (`02-project-structure.md`), assigned when its Deployment Unit is created (`29-deployment.md`). `RuntimeId` identifies the Runtime independently of the Nodes currently composing it — a single-node Runtime and a hundred-node Runtime are each still exactly one `RuntimeId`, and that identity does not change as nodes join or leave.

`NodeId` answers which machine participates. `RuntimeId` answers one architectural question only: "to which Runtime does this Node belong?" Every Node, once authorized by Trust (`22-networking.md`), carries the `RuntimeId` of the Runtime it is currently part of.

## Trust Islands

A Trust Island is the set of Nodes sharing one `RuntimeId` and one Trust authority (`22-networking.md`). Every Runtime is, by default, its own island — Trust decisions inside one island never automatically extend to another, precisely the rule `13-object-model.md` referenced but left undefined: *"Physical Replicas never cross a trust boundary automatically."* A trust boundary is the edge of a Trust Island; crossing it always requires the explicit authorization Federation defines.

Two Runtimes remain separate islands even while federated. Federation authorizes specific cooperation between islands; it never merges them into one. Federation never removes a trust boundary. It only authorizes specific interactions across it.

## Federation Trust

Federation Trust answers a question Networking's Trust never asks: not "is this Node authorized to join my Runtime," but **"is that entire Runtime authorized to cooperate with mine."** The two are evaluated independently and by different authorities — a Node may be perfectly trustworthy while its Runtime has no Federation authorization at all, and vice versa in principle, though in practice Federation Trust constrains what any of that Runtime's Nodes may request across the boundary.

Federation Trust produces a Federation Membership: a durable, authorized cooperation between two `RuntimeId`s, revocable exactly the way Node-level Trust is revocable (`22-networking.md`'s `TrustRevoked` — Federation publishes the symmetric `FederationRevoked`), following the same revocation principles already established for Node Trust.

## Federation Policy

Federation Trust decides *whether* two Runtimes may cooperate. Federation Policy decides *what* that cooperation permits — which capabilities of the Runtime API a federated peer may invoke, which Content Objects may cross the boundary via Replication, under what constraints. Policy is authorized configuration, evaluated on top of an already-established Federation Membership; it never substitutes for Federation Trust and is never evaluated before it.

Federation Policy is authoritative configuration, following the same category `24-replication.md`'s Replication Policy already established: it expresses desired cooperation, not observed state, and is never reconstructed by observation. Federation Membership is itself an authoritative fact, durably recorded and never inferred by observation.

## Relationship with Networking

Federation never reimplements Discovery, Authentication, Sessions, or Transport. A federated Runtime's Nodes are discovered, authenticated, and connected exactly as `22-networking.md` already defines — Federation adds one fact on top: which `RuntimeId` a Session's peer belongs to, and whether that Runtime currently holds a valid Federation Membership. Networking answers whether bytes can move. Federation answers whether they are allowed to mean anything once they arrive. Networking remains transport-agnostic. Federation remains transport-independent.

## Relationship with Runtime API

Federation never invents a second inter-Runtime protocol. `26-runtime-api.md` already anticipated this: *"another TibiOS Runtime"* is listed among the Runtime API's consumers. A federated Runtime calls the same Runtime API capabilities any other consumer calls (`26`) — Submit Workload, Query Objects, Observe Events — the only difference is that Federation Policy, not just Trust and Authorization at the Boundary (`26`'s own model), gates which existing Runtime API capabilities a federated Runtime may invoke.

## Relationship with Replication

Replication (`24-replication.md`) already established the rule Federation now enforces concretely: *"Physical Replicas never cross a trust boundary automatically — replication across islands requires explicit authorization."* Federation is that authorization. A Pull crossing from one Trust Island to another must find both a valid Federation Membership between the two `RuntimeId`s and a Federation Policy permitting that specific Content Object to cross — Replication still decides *how* the Pull happens; Federation decides *whether it may happen at all*.

Federation never moves content itself. It only authorizes the crossing that Replication then performs, exactly as Trust never establishes Sessions — it only authorizes them for Networking to establish (`22-networking.md`).

## Relationship with Deployment and Runtime Identity

Deployment (`29-deployment.md`) creates Runtime instances. Every Runtime instance has one `RuntimeId`. Federation consumes `RuntimeId`; it never generates or reinterprets it. Deployment does not interpret `RuntimeId` either — it produces the Deployment Unit's Identity component and hands it to the Runtime instance; what that identity means for cooperation with other Runtimes is entirely Federation's question, never Deployment's.

A new Deployment Unit generation (`29`'s Reconfiguration) does not necessarily mean a new `RuntimeId` — whether reconfiguration preserves or renews Runtime Identity is a Deployment-level policy decision, but Federation Membership is always evaluated against whatever `RuntimeId` is currently presented, never against a specific process or Deployment Unit generation.

## Federation Lifecycle

```
Discovered
    │
    ▼
Proposed
    │
    ▼
Authorized
    │
    ▼
Active
    │
    ▼
Revoked
```

`Discovered` — another `RuntimeId` becomes known, through Networking's Discovery (`22`) or explicit configuration; discovery alone grants no cooperation. `Proposed` — a Federation Membership request exists but is not yet authorized on both sides. Federation Membership is always bilateral. One Runtime cannot federate another unilaterally. `Authorized` — both Runtimes' Trust authorities have approved the Membership. Authorization establishes that cooperation may exist. Federation Policy determines its scope. `Active` — capability invocations and content crossing are permitted per Policy. Active does not imply unrestricted cooperation. Federation Policy remains continuously in effect. `Revoked` — either Runtime's Trust authority may revoke unilaterally, publishing `FederationRevoked`, immediately terminating cooperation, following the same revocation principles already established for Node Trust.

Federation Membership is an authoritative lifecycle, independent of Networking Sessions. Sessions may come and go without changing Membership; Membership may be revoked even while Sessions still exist.

## Failure & Recovery

Federation Membership is an authoritative fact (`00-philosophy.md`) and is recovered exactly the way any other authoritative fact is: replayed from its own event stream (`21-runtime-storage-engine.md`'s Authoritative Event Streams), never reconstructed by observation. A Runtime restart never silently loses or invents a Federation Membership.

A transient Networking failure between two federated Runtimes never revokes Federation Membership by itself — Membership is a Trust-level decision with its own lifecycle (see above), and Session loss is recoverable independently (`22-networking.md`'s Connection Recovery). Only an explicit Trust decision produces `FederationRevoked`.

## Observability

Federation exposes: Federation Membership state per `RuntimeId`, Federation Trust decisions (with reasons), Federation Policy evaluations (with reasons, symmetric to Scheduling's Filter explainability in `16-scheduling-engine.md`), and cross-Runtime capability invocation counts. It never exposes another Runtime's internal state beyond what that Runtime's own Runtime API already permits.

## Anti-Patterns

Avoid: treating Node-level Trust as sufficient for Federation Trust, treating a Networking Session as equivalent to Federation Membership, a second inter-Runtime protocol alongside the Runtime API, Federation moving content directly instead of authorizing Replication to do so, unilateral Federation Membership, merging two Runtimes' Trust Islands into one.

## Review Checklist

Before extending Federation ask: does this answer a Runtime-to-Runtime question, or does it belong to Node-to-cluster Trust (`22`)? Does it reuse the existing Runtime API surface rather than inventing a new one? Does it distinguish Federation Trust (may they cooperate) from Federation Policy (what may they do)? Does it treat Federation Membership as authoritative, never observational?

## Principles

- Federation answers whether two Runtimes may cooperate — never whether a Node may join a cluster, and never whether content should cross.
- A Federation Member is an entire Runtime, identified by `RuntimeId`, never a Node.
- Trust at Node granularity and Trust at Runtime granularity are independent authorization decisions. Neither implies the other.
- Federation governs cooperation. Networking governs communication.
- Federation never removes a trust boundary. It only authorizes specific interactions across it.
- Federation never invents a second inter-Runtime protocol. All Federation communication uses the existing Runtime API surface.
- Federation Membership is an authoritative fact, durably recorded and never inferred by observation — and independent of any Networking Session's lifecycle.

## Motto

Two Runtimes. One decision to cooperate. Everything else already existed.
