# TibiOS Distributed Systems Philosophy

Version: 1.0

## Purpose

TibiOS is a distributed runtime. Distribution is not an extension — it is the foundation. Every subsystem must assume that execution may occur across multiple nodes, processes, networks, and failure domains.

## First Principle

The network is not reliable. Everything else follows from this assumption.

## Fundamental Assumptions

Assume: nodes fail, disks fail, processes crash, messages are delayed, messages are duplicated, messages are reordered, clocks drift, networks partition, operators make mistakes. Design accordingly.

## Failure is Normal

Failure is not exceptional — it is expected. Recovery is part of normal execution.

## Distribution is Invisible

Applications should not care where computation occurs. Applications describe work; the runtime decides execution.

## Local First

Whenever possible, execute work locally. Move computation before moving data — data movement is expensive.

## Network is Expensive

CPU is cheap, memory is cheaper, disk is slower, network is the most expensive shared resource. Reduce network communication whenever possible.

## Ownership

Every object has one logical owner. Ownership simplifies reasoning, reduces synchronization, and improves scalability.

## Message Passing

Components communicate through messages. Shared mutable state is discouraged. Ownership moves with messages.

## Immutable Messages

Messages should be immutable — they describe intent, never expose internal state.

## Idempotency

Distributed operations should be idempotent whenever possible. Executing the same request twice must not produce unexpected behavior.

> This is why every Workload/Admission request carries a stable identity (`WorkloadId`, ULID) used as the idempotency key — a network retry must never create a second logical Workload or double-consume quota (see `20-admission-control.md`).

## Retries / Timeouts / Backpressure

Retries are normal — operations must tolerate them, with limits, backoff, and observability. Every remote operation has a timeout; no operation waits forever. Every queue has limits; every producer must respect consumers.

## Stateless Coordination

Coordinators should own as little state as possible. State belongs close to the owner.

## Determinism

Deterministic systems are easier to test, debug, and recover. Avoid unnecessary nondeterminism.

## Consistency

Not every operation requires global consistency. Choose the weakest consistency model that satisfies correctness — consistency is a business decision, not an engineering reflex.

## Availability / Partition Tolerance

Availability matters, but availability without correctness is failure — correctness remains the highest priority. Network partitions are expected; the runtime must degrade gracefully.

## Fault Domains

Failures should remain local. One failed node should not destabilize the cluster.

## Scheduling

Scheduling decisions should consider locality, load, latency, data placement, resource availability. Never schedule randomly.

## Scalability

Scaling should not require architectural changes — adding nodes should improve throughput, not complexity. Prefer more nodes over larger nodes (horizontal before vertical).

## Storage

Storage is distributed. Replication is expected. Recovery is expected. Corruption is possible.

## Communication

Communication should be explicit, versioned, observable, authenticated. Never rely on undocumented protocols.

## Versioning

Nodes of different versions may coexist. Protocols should evolve safely — compatibility is intentional.

> Concretely: never renumber or reuse a protobuf field in the core↔ray contract, and include an explicit protocol-version field in overlay messages between islands.

## Recovery

Recovery begins immediately after failure and should require minimal operator intervention. Automation is preferred.

## Observability / Security

Every distributed operation is observable; every decision can be reconstructed; every failure leaves evidence. Every node is untrusted until verified; every message is validated; every protocol is authenticated.

## AI Workloads

AI execution is simply another distributed workload. Models are resources. Inference is scheduling. Memory is a shared constraint. The runtime treats AI workloads using the same architectural principles as everything else.

## Architecture Rules

Applications express intent. The runtime plans execution. Workers execute work. Storage preserves state. Networking transports messages. Schedulers coordinate resources. Responsibilities never overlap.

## Anti-Patterns

Avoid: global mutable state, centralized bottlenecks, hidden communication, synchronous distributed workflows, unbounded queues, implicit retries, implicit ownership, node-specific assumptions.

## Review Checklist

Before designing a feature ask: what happens if the node crashes? What happens if the network partitions? What happens if the message arrives twice? What happens if execution is delayed? Can ownership be simplified? Is communication observable? Is recovery automatic? Can this scale to hundreds of nodes?

## TibiOS Philosophy

Nodes are temporary. Messages are permanent records of intent. Ownership defines architecture. The runtime owns orchestration. Applications describe work. Failures are expected. Recovery is continuous. Distribution should feel invisible.

## Engineering Motto

Do not build software that survives success. Build software that survives failure.
