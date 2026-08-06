# TibiOS Deployment

Version: 1.0

## Purpose

Deployment answers exactly one question: **should a Runtime instance exist, with what configuration, and for how long?** It is not Scheduling (`16-scheduling-engine.md`), not Orchestration of Workloads, not Replication (`24-replication.md`), and not Networking (`22-networking.md`) — those all operate *inside* a running Runtime. Deployment operates *outside* it.

Deployment does not know Kubernetes, Docker, Helm, or systemd. Those are technologies that may implement Deployment's decisions, exactly as REST and gRPC implement the Runtime API's capabilities (`26-runtime-api.md`) — the model stays identical whether a Runtime instance is a container, a bare-metal process, or an embedded device.

```
Outside the process
──────────────────────────────────────────────
Deployment
    │
    ├── decides that a Runtime instance should exist
    ├── selects configuration
    ├── selects infrastructure
    ├── launches the Runtime process
    └── later requests shutdown
──────────────────────── Process boundary ────────────────────────
Runtime (02-project-structure.md)
    │
    ├── Runtime Startup
    ├── Composition Root
    ├── Runtime Execution
    └── Runtime Shutdown
──────────────────────────────────────────────
```

**Deployment decides that a Runtime exists. The Composition Root decides how that Runtime comes to life.** Two completely different questions. `02-project-structure.md` already answers the second one in full; this document never redefines it. Deployment creates Runtime instances. The Composition Root composes Runtime domains.

## Ownership

Deployment owns its own crate, `runtime-deployment`. Unlike projection documents (`25-ai-runtime.md`, `27-sdk.md`, `28-cli.md`), Deployment introduces new architectural concepts with their own lifecycle and therefore requires its own domain.

Deployment owns the lifecycle of a Runtime instance. It does not own the Runtime itself — `02-project-structure.md`'s Composition Root remains the sole authority over how a Runtime instance wires itself internally once it exists.

Deployment owns the lifecycle of the Runtime process before startup and after shutdown. While the Runtime is executing, its internal lifecycle is governed exclusively by the Runtime. This is the same Ownership principle already established in `00-philosophy.md` and generalized to services in `23-object-store.md`'s review ("every domain owns the services that speak its language"), applied here to time instead of behavior.

## Core Principles

- Deployment decides that a Runtime instance exists. The Composition Root decides how it comes to life.
- Deployment owns the Runtime process before startup and after shutdown. While running, its internal lifecycle is governed exclusively by the Runtime.
- Deployment never redefines Runtime Startup, Composition Root wiring, or Runtime Shutdown — `02-project-structure.md` remains the sole authority over all three.
- Deployment infrastructure (Kubernetes, Docker, systemd, virtual machines, bare processes) is an implementation detail, never part of the model.

## Deployment Unit

A Deployment Unit is Runtime + Configuration + Identity — the smallest thing Deployment creates, tracks, and eventually destroys. A Deployment Unit is the unit of deployment, not the unit of execution — it is never confused with a Workload, a Worker, or an Allocation, and it exists whether or not the Runtime process it wraps is currently running.

A Deployment never modifies a Runtime — it instantiates one. Deployment remains outside the Runtime boundary. Once the Runtime is executing, interaction is limited to observation and lifecycle requests, never internal mutation.

## Deployment Models

A Deployment Unit may be realized as a local process, a standalone node, a cluster node (joining other Tibi Box nodes), an embedded Runtime (resource-constrained device), a container or virtual machine, or a bare-metal process. Each is an infrastructure choice for *how* a Deployment Unit is realized, never a different *kind* of Deployment Unit.

## Configuration

Configuration is declarative — it describes the Runtime instance Deployment should bring into existence, not the instance itself. Configuration is supplied before a Runtime process starts and is one of the inputs to `02-project-structure.md`'s "Create Configuration" step; Deployment produces it, the Runtime consumes it. The Runtime consumes configuration; it never owns it.

Configuration is neither authoritative nor observational Runtime state. It is deployment input — fixed at the moment a Deployment Unit is created or reconfigured, never mutated by the Runtime itself while running.

Deployment Configuration is deployment input, not a Configuration Object (`13-object-model.md`). It is never stored, versioned, or addressed through the Runtime Object Model unless explicitly imported as one.

## Process Launch

Deployment produces the Runtime configuration and initiates process creation. From that point onward, Runtime startup follows `02-project-structure.md`'s Runtime Startup sequence unchanged: Create Configuration → Create Infrastructure → Create Domain Services → Inject Dependencies → Start Runtime. Deployment never redefines the Composition Root, and never performs any of its steps itself.

Deployment's responsibility for process creation ends at the moment the Runtime process exists and has received its Configuration. From Runtime Startup onward, responsibility transfers to the Composition Root.

Shutdown is symmetric: Deployment requests it; `02-project-structure.md`'s Runtime Shutdown sequence (Stop accepting new work → Drain active operations → Release leases → Flush authoritative logs → Terminate infrastructure) governs what happens inside the process before it exits. Deployment observes process termination; it does not orchestrate the sequence that ends it.

## Relationship with Networking

A newly launched Runtime instance does not automatically belong to a cluster. Cluster participation begins only once Discovery, Authentication, and Trust Authorization (`22-networking.md`'s Architectural Pipeline) succeed — Deployment may supply the configuration a Runtime instance uses to attempt discovery (seed peers, bootstrap credentials), but it never joins a cluster on the Runtime's behalf. Joining remains entirely `22-networking.md`'s responsibility, exercised by the Runtime instance itself once running. Deployment supplies configuration. Networking establishes membership.

## Relationship with Storage

Deployment selects which Storage adapter a Runtime instance will use and where its local persistence lives (`21-runtime-storage-engine.md`) — this selection is part of Configuration, consumed at Create Infrastructure time. Deployment connects Storage; it never redefines it. Changing the Storage adapter changes deployment, never the Storage model. The Storage Engine's own model (Authoritative Event Streams, Content Store, Snapshot Store, Report Store) is entirely unaffected by which Deployment Model launched the process using it.

## Relationship with Runtime

Deployment owns the lifecycle of a Runtime instance. The Runtime owns itself while executing (`00-philosophy.md`'s Ownership principle, applied to time — see Ownership above). Deployment answers *should this process exist, and with what configuration?* The Runtime answers *how do I wire myself, initialize my domains, and execute?* — two questions, two owners, no overlap.

Deployment creates Runtime instances. The Composition Root composes Runtime domains. Neither ever performs the other's responsibility.

## Lifecycle

```
Defined
    │
    ▼
Configured
    │
    ▼
Launching
    │
    ▼
Running
    │
    ▼
Stopping
    │
    ▼
Removed
```

This is the Deployment Unit's own lifecycle — never the Runtime's. `Running` is intentionally opaque from Deployment's perspective: everything `02-project-structure.md` defines (Runtime Startup, Composition Root wiring, domain execution, Runtime Shutdown) happens entirely inside it, invisible to Deployment except as observable process state. Deployment does not track `WorkloadState` (`11-runtime.md`) or any domain-internal state — that would mean Deployment reaching past the process boundary it exists to respect.

## Failure & Recovery

A crashed Runtime process is Deployment's concern, not the Runtime's — the Runtime cannot recover itself once its process has terminated. Deployment detects the crash, decides whether to restart (per policy — always, never, with backoff, with a limit), and if so, launches a new process with the same Configuration.

Recovery *inside* the Runtime process (replaying Authoritative Event Streams, rebuilding projections, re-observing reality) is entirely `21-runtime-storage-engine.md`'s and each domain's own responsibility, unchanged by who or what launched the process — a restarted Runtime instance recovers exactly the same way a manually restarted one would. **Deployment restarts processes. Runtime recovers state.**

A configuration change creates a new generation of the Deployment Unit. Reconfiguration never mutates a live Runtime in place — it produces a new generation, launched with the new Configuration, following the same Lifecycle from `Defined` again. Configuration is never hot-patched into a running Composition Root. Deployment replaces Runtime instances. It never transforms them in place.

## Observability

Deployment exposes process-level signals: instance state (per the Lifecycle above), launch time, restart count, current Configuration generation, and time since last restart. It never exposes Runtime-internal observability (`09-observability.md`) — that belongs to the Runtime instance itself once running, surfaced through its own Observability, never duplicated by Deployment.

## Anti-Patterns

Avoid: re-implementing any step of `02-project-structure.md`'s Runtime Startup or Shutdown sequence inside Deployment, Deployment reaching into Runtime-internal state, hot-patching Configuration into a running process, a Deployment Unit joining a cluster on the Runtime's behalf, treating Configuration as Authoritative or Observational Runtime state, coupling the Deployment model to a specific infrastructure technology (Kubernetes, Docker, systemd).

## Review Checklist

Before extending Deployment ask: does this belong to whether a Runtime instance exists, or to how it behaves once running? Does it duplicate a step `02-project-structure.md` already owns? Does it require reaching past the process boundary? Would this decision still make sense if the underlying infrastructure technology changed?

## Principles

- Deployment decides that a Runtime instance exists. The Composition Root decides how it comes to life.
- Deployment owns the Runtime process before startup and after shutdown. While running, its internal lifecycle is governed exclusively by the Runtime.
- Deployment creates Runtime instances. The Composition Root composes Runtime domains.
- Deployment restarts processes. Runtime recovers state.
- Configuration is neither authoritative nor observational Runtime state. It is deployment input, produced by Deployment and consumed by the Runtime.
- Deployment replaces Runtime instances. It never transforms them in place.
- Deployment infrastructure is an implementation detail, never part of the model.
- Deployment belongs to the plane of existence — whether a Runtime instance exists. The Runtime belongs to the plane of execution — how that instance behaves once running.

## Motto

Decide that it exists. Let it wire itself. Never reach inside.
