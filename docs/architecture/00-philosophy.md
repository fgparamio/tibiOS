# TibiOS Architecture Philosophy

Version: 2.0

## Purpose

TibiOS is designed as a distributed Runtime for executing intelligent workloads across heterogeneous infrastructure.

The purpose of this document is not to describe how the Runtime is implemented.

Its purpose is to describe why the Runtime is designed the way it is.

This document defines the architectural principles from which every other design decision should naturally follow.

Implementation evolves.

Architecture should remain stable.

## Architecture Before Implementation

Architecture defines the space of valid implementations.

Implementation realizes only a subset of that space.

A Runtime implementation is expected to evolve over time.

The architectural model should not be constrained by today's implementation.

Whenever possible, the model should express the complete conceptual design, even if only part of that design is implemented initially.

### The Model Is Larger Than Today's Implementation

The architectural model intentionally includes capabilities that may not exist in the first Runtime release.

Examples include resource overcommit, allocation preemption, live migration, checkpointing, and advanced scheduling policies.

These concepts belong to the architectural model because they are natural consequences of the model itself.

An implementation may postpone them without changing the architecture.

### Zero Cost Until Used

Describing a capability does not require implementing it.

Unused architectural concepts impose no operational cost.

The Runtime should pay only for the capabilities it actually enables.

Architecture defines possibility. Implementation defines reality.

### Zero Cost Applies to the Model

Architectural concepts are free only while they remain part of the conceptual model.

A capability expressed through types, contracts, or architectural relationships imposes no operational cost until an implementation chooses to realize it.

The Runtime should not construct, initialize, or maintain mechanisms that have no active consumer.

Architectural completeness does not justify implementation complexity.

Cost begins when behavior is introduced, not when possibility is described.

*Architectural level* — "Allocation supports migration." This costs nothing. It is a property of the model.

*Implementation level* — `MigrationManager::start()`, `CheckpointThread::spawn()`, `BackgroundScanner::run()`. This has a cost, even if no Allocation is ever migrated.

### Simplicity Through Correct Models

Complex systems rarely become simpler by removing concepts.

They become simpler by assigning every concept a clear responsibility.

A complete model with explicit ownership is easier to evolve than an incomplete model filled with special cases.

Architectural simplicity emerges from correct boundaries, not from minimizing the number of concepts.

### Architecture Evolves by Discovering Invariants

The Runtime should not evolve by accumulating features.

It should evolve by discovering invariants.

An invariant is a property that remains true regardless of future implementation choices.

Whenever a recurring design decision appears, it should be examined as a potential architectural invariant.

Once identified, an invariant becomes part of the architectural model.

Future implementations should derive from these invariants, rather than redefining them.

### Stable Principles

Implementation changes. Technology changes. Infrastructure changes.

Architectural principles should remain stable.

Whenever implementation and principles disagree, the implementation should be reconsidered before changing the principles.

Architectural principles change only when the conceptual model itself changes.

### Long-Term Design

The Runtime is designed to support continuous evolution.

New capabilities should extend the existing model. They should not require replacing it.

A successful architecture is one that becomes easier to extend over time, because its invariants become clearer as experience grows.

### Consequences

This philosophy has several important consequences.

The Runtime deliberately distinguishes between architectural possibility and implementation maturity.

Features may exist in the architectural model before they exist in code.

Implementation order is an engineering decision. Architecture is not.

### Principles

- The model is larger than today's implementation.
- Architecture defines possibility. Implementation defines reality.
- Unused abstractions cost nothing — but only at the type level; unconsumed infrastructure is never free.
- Simplicity emerges from correct ownership, not from fewer concepts.
- Architecture evolves by discovering invariants, not by accumulating features.
- Stable principles outlive individual implementations.

---

## Ownership

Distributed systems become difficult when responsibility is unclear.

Whenever multiple components are allowed to modify the same state, coordination becomes unavoidable.

Synchronization, locking, distributed consensus and race conditions are often symptoms of unclear ownership rather than inherent properties of distributed computing.

The Runtime therefore treats ownership as the primary architectural tool for reducing complexity.

### Authority

Every mutable state has exactly one authoritative owner.

Authority means the exclusive right to modify a piece of state.

Other Runtime domains may observe that state. They may cache it. They may derive new information from it. They never modify it.

Ownership defines authority. Authority defines responsibility.

### Ownership Reduces Synchronization

Concurrency is not eliminated. Shared mutation is.

When only one owner may modify a state, coordination becomes local to that owner.

The rest of the Runtime communicates through immutable facts.

This minimizes synchronization while preserving consistency.

Ownership is therefore preferred over distributed coordination whenever possible.

### Responsibility

Authority and responsibility are inseparable.

A Runtime domain that owns a state is responsible for validating it, updating it, preserving its invariants, and publishing authoritative facts about its evolution.

No other domain performs these tasks on its behalf.

### Source of Truth

Every authoritative state has exactly one source of truth.

The Runtime never maintains multiple authoritative representations of the same state.

Additional representations may exist as caches, projections, indexes, or snapshots.

These representations improve efficiency. They never replace the source of truth.

### Consistency Domains

Every authoritative fact belongs to exactly one consistency domain.

Consistency is always local.

No authoritative fact is jointly owned by multiple Runtime domains.

Each domain evolves independently.

Cross-domain coordination occurs through published facts, never through shared mutable state.

### Ownership Boundaries

Ownership should be explicit.

If two Runtime domains appear to own the same concept, the ownership model is incorrect.

The correct solution is to redefine boundaries, not to introduce shared ownership.

Shared ownership increases coupling. Clear ownership reduces it.

### Services Belong to Domains

Ownership does not stop at state. A domain also owns the services that speak its language — the operations that interpret its concepts, not merely the data those concepts describe.

Infrastructure provides capabilities: durability, transport, computation. It never owns the meaning of what it stores, sends, or executes. A service belongs to the domain whose language it speaks, regardless of which infrastructure implements the capability underneath it.

This produces a small but complete symmetry:

- Every domain owns its state.
- Every domain owns the services that speak its language.
- Every consumer owns the ports it requires (`02-project-structure.md`).

These are not three separate rules. They are the same Ownership principle, seen from three angles: what is owned, by whom, and through what boundary.

### Communication

Runtime domains interact through three complementary mechanisms.

Service Contracts request work. Data Contracts transfer immutable information between domains. Runtime Events publish facts that have already become true.

Each mechanism serves a different architectural purpose. They are not interchangeable.

### State Propagation

Changes to authoritative state are never communicated by direct mutation.

Instead, only the owning domain publishes facts describing what has already changed.

Other domains may observe those facts. They may update their own projections. They never publish facts on behalf of the owning domain. They never modify the authoritative state directly.

State changes therefore propagate through facts, not through shared mutable state.

### Facts and Commands

Commands request work. Facts describe completed reality.

A command may or may not succeed.

A fact is published only after the owning domain has successfully committed the change it describes.

This distinction keeps ownership explicit and prevents consumers from assuming authority over another domain's state.

### Consequences

Ownership naturally produces independent domains, local reasoning, deterministic responsibilities, simpler recovery, and reduced synchronization.

The architecture therefore favors ownership even when alternative designs appear more flexible.

The cost of flexibility is often hidden coupling. Ownership makes coupling explicit.

### Principles

- Every mutable state has exactly one authoritative owner.
- Every authoritative state has exactly one source of truth.
- Every authoritative fact belongs to exactly one consistency domain.
- Ownership reduces synchronization.
- Authority and responsibility are inseparable.
- Authoritative state changes propagate through facts, never through shared mutable state.
- Shared ownership is a design error, not an optimization.
- Every domain owns the services that speak its language; infrastructure provides capabilities, never meaning.

---

## State

Not all Runtime state has the same nature.

Some state represents authoritative facts that cannot be recovered once lost.

Other state is merely an observation of external reality.

Treating both categories identically introduces unnecessary complexity.

The Runtime therefore distinguishes between authoritative state and observational state.

### Authoritative State

Authoritative state represents facts owned by the Runtime.

Once created, these facts define reality for the Runtime.

Examples include Object lifecycle, Admission decisions, Allocation contracts, and Trust decisions.

Authoritative state cannot be reconstructed by simply observing the world again. It must therefore be preserved.

### Observational State

Observational state represents measurements of an external reality.

Examples include current node health, current resource utilization, network reachability, and heartbeat information.

Observational state continuously changes.

Its value comes from describing the present, not from preserving its history.

If lost, it can simply be observed again.

### Facts and Observations

Facts create Runtime reality. Observations describe Runtime environment.

Facts are owned. Observations are measured.

Facts evolve through authoritative decisions. Observations evolve through continuous measurement.

Confusing these categories leads to unnecessary persistence, unnecessary synchronization, and unnecessary complexity.

### Persistence

Persistence exists to preserve authoritative facts.

The Runtime does not persist information merely because it changes.

It persists information because losing it would destroy knowledge that cannot be reconstructed.

Persistence therefore protects authority, not activity.

### Reconstructability

Whenever possible, the Runtime prefers reconstruction over persistence.

If reality can be observed again, replaying historical observations provides little value.

Instead, the Runtime simply measures the current state again.

Only irrecoverable facts require durable storage.

### Volatility

Different kinds of state evolve at different rates.

Some state changes rarely. Some changes continuously.

Architecture should reflect this difference.

Applying identical consistency mechanisms to states with radically different volatility creates unnecessary cost.

Consistency strategies should match the natural volatility of the state they protect.

### Volatility Examples

Trust changes rarely. Membership changes frequently. Health changes continuously. Resource utilization changes constantly.

These categories require different synchronization, different persistence, and different recovery strategies.

The Runtime deliberately avoids treating them uniformly.

### Recovery

Recovery restores authoritative knowledge. Recovery does not recreate transient observations.

After a Runtime restart, authoritative facts are reconstructed from authoritative persistence.

Observational state is measured again from reality.

Recovery therefore combines replay, reconstruction, and fresh observation — each according to the nature of the state involved.

### Consequences

This distinction naturally produces authoritative logs, rebuildable projections, ephemeral observations, lightweight snapshots, and efficient recovery.

The Runtime persists only what cannot be rediscovered. Everything else is reobserved.

### Principles

- Persist facts. Reobserve observations.
- Authoritative persistence exists only for state that cannot be reconstructed by observing reality again.
- Facts create Runtime reality. Observations describe Runtime environment.
- Recovery reconstructs authority and reobserves reality.
- Different volatility requires different consistency strategies.
- Persistence protects knowledge, not activity.
- Reconstruction is preferred whenever reality can be observed again.

---

## Runtime Evolution

The Runtime is expected to evolve continuously.

New technologies will appear. Hardware will change. Execution models will improve.

The architecture should accommodate this evolution without requiring fundamental redesign.

Evolution should preserve principles while extending capabilities.

### Separation of Concerns

Architectural concerns should remain independent.

Admission decides whether work is eligible to enter the Runtime.

Scheduling decides where work should execute.

Allocation commits Runtime resources.

Workers execute workloads.

Object preserves identity and meaning, independent of how content is stored.

State Assembler observes Runtime reality and publishes consistent snapshots.

Storage preserves authoritative knowledge.

Networking transports communication.

Trust authorizes participation.

Observability explains Runtime behavior.

Each concern exists for one purpose. Responsibilities should never overlap.

### Layers of Decision

Not every Runtime component makes decisions.

Some components own policy. Some own execution. Some own observation.

Separating these responsibilities keeps the Runtime predictable.

Decision-making should remain explicit. Execution should remain deterministic. Observation should remain descriptive.

### Architectural Growth

A mature architecture does not grow by accumulating mechanisms.

It grows by revealing deeper invariants.

Every new capability should naturally fit an existing principle.

Whenever a feature appears to require an exception, the architecture should first ask whether an invariant has not yet been discovered.

Exceptions often indicate incomplete understanding. New invariants simplify future designs.

### Technology Independence

The Runtime should never be defined by its implementation technologies.

Protocols, databases, network transports, storage engines, or execution frameworks are implementation choices.

They may evolve without changing the architectural model.

Technology serves architecture. Architecture never serves technology.

### Local Reasoning

Every Runtime domain should be understandable in isolation.

Its responsibilities, authority, contracts, and invariants should be understandable without requiring knowledge of the entire Runtime.

Global behavior emerges from the interaction of locally consistent domains.

Complexity should emerge through composition, never through individual components.

### Architectural Consistency

Architectural decisions should reinforce one another.

Ownership supports consistency. Consistency supports recovery. Recovery supports evolution. Evolution preserves architectural stability.

Independent principles should naturally converge toward the same design.

When independent reasoning repeatedly produces the same solution, the architecture has likely discovered an invariant rather than invented a convention.

### Long-Term Stability

An architecture succeeds when future changes require fewer architectural decisions, not more.

As the Runtime matures, new capabilities should increasingly become applications of existing principles, rather than motivations for creating new ones.

Stable principles reduce future complexity.

### Engineering Mindset

Engineering should seek clarity before optimization.

Correct ownership before synchronization. Correct models before implementation. Correct abstractions before reuse. Correct principles before mechanisms.

Well-chosen principles remove complexity more effectively than sophisticated implementations.

### Relationship to Other Documents

This document defines the philosophical foundations of the Runtime.

The remaining architecture documents apply these principles to specific domains.

Whenever implementation guidance appears to conflict with this document, the conflict should first be examined as a misunderstanding of ownership, authority, state, or architectural boundaries, before introducing new mechanisms.

Architecture derives from philosophy. Implementation derives from architecture.

### Final Principles

- Architecture is discovered, not invented.
- Stable invariants outlive individual implementations.
- Ownership is the foundation of simplicity.
- Facts deserve persistence. Observations deserve freshness.
- Technology is replaceable. Principles are not.
- Complexity should emerge from composition, never from individual components.
- Every architectural decision should reinforce the whole.

### Closing Statement

The purpose of architecture is not to predict every future implementation.

Its purpose is to establish principles that remain valid as implementations evolve.

A successful Runtime is not one that never changes.

It is one whose changes naturally follow the principles that define it.

Those principles are the true architecture of TibiOS.
