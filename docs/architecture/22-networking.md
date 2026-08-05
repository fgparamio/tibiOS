# Runtime Networking

Version: 2.0

## Purpose

The Networking domain provides communication between Runtime instances.

Its responsibility is transport.

Networking does not participate in scheduling, allocation, storage, or execution.

It provides authenticated communication channels over which Runtime domains exchange information.

## Scope

Networking owns:

- peer discovery
- peer authentication
- Runtime sessions
- stream transport
- connection lifecycle

Networking does not own: Trust, Membership, Health, Resource discovery, Scheduling.

Those responsibilities belong to their respective Runtime domains.

## Relationship to Other Domains

Networking follows the architectural principles defined in `00-philosophy.md` and `02-project-structure.md`.

Networking communicates through Service Contracts, Data Contracts, and Runtime Events.

Networking never assumes ownership of another domain's state.

## Responsibilities

Networking has four responsibilities.

**Discovery** — locate reachable Runtime peers.

**Authentication** — cryptographically verify peer identity.

**Sessions** — maintain authenticated Runtime communication sessions.

**Transport** — carry Runtime Streams between Runtime instances.

No additional responsibilities belong to Networking.

## Architectural Pipeline

Networking follows a fixed execution pipeline.

```
Discovery
    │
    ▼
Authentication
    │
    ▼
Trust Authorization
    │
    ▼
Session
    │
    ▼
Transport
```

Each stage produces the input required by the next stage. Responsibilities never overlap.

### Discovery

Discovery identifies reachable peers. Discovery answers one question only: "Which Runtime peers are reachable?"

Discovery does not determine identity, trust, membership, or health. Discovery merely provides candidate peers.

### Authentication

Authentication verifies cryptographic identity. Networking performs the transport-level authentication protocol.

Successful authentication produces a **Verified Identity**.

Authentication proves identity. It does not grant authorization.

### Trust Authorization

After identity has been verified, Networking queries the Trust domain.

```
Verified Identity
        │
        ▼
Authorize(identity)?
        │
        ▼
      Trust
```

Trust answers `authorized` or `rejected`.

Networking never decides authorization. Trust never establishes network sessions. Authorization and session management remain separate concerns.

### Session Creation

Only authorized identities may establish Runtime Sessions.

A Session represents the logical communication relationship between two Runtime instances.

Sessions are owned exclusively by Networking. Other Runtime domains may observe Session state. They never modify it.

---

## Runtime Sessions

A Runtime Session represents an authenticated communication relationship between two Runtime instances.

Sessions are logical Runtime concepts. They are independent of the underlying transport connection.

Networking owns every Session. No other Runtime domain may modify Session state.

### Session Identity

Every Session has a `SessionId`, a Verified Identity, a Lease, and a current State.

Session identifiers belong to Runtime Primitives. Networking owns the Session lifecycle.

### Session States

```
Pending
    │
    ▼
Authenticated
    │
    ▼
Authorized
    │
    ▼
Active
    │
    ▼
Closed
```

State transitions occur only inside Networking. Other Runtime domains observe Session state through published facts.

### Session Lease

Every active Session owns a Lease. The Lease defines the maximum lifetime of the authorization represented by the Session.

Sessions remain valid only while their Lease remains valid.

Lease semantics are defined by Runtime Primitives. Networking applies those semantics to Session lifecycle management.

**Lease Renewal** — a Session Lease may be renewed while authorization remains valid. Renewal does not require recreating the Session. Lease renewal extends authorization; it does not establish new identity.

**Lease Expiration** — when a Session Lease expires, Networking must revalidate authorization before allowing further communication. If revalidation succeeds, the Lease is renewed. Otherwise, the Session transitions to Closed. Lease expiration guarantees eventual correctness, even if external notifications are delayed or lost.

### Runtime Streams

Sessions own Runtime Streams. Streams never exist independently of a Session.

Every Runtime Stream belongs to exactly one Session. Closing a Session automatically closes every Stream owned by that Session.

**Stream Categories** — Networking distinguishes two categories of Streams. Control Streams carry Runtime coordination traffic. Data Streams carry Runtime payloads. Transport treats both identically; their interpretation belongs to higher Runtime domains.

### Transport

Transport moves Streams. Transport does not interpret messages, commands, events, objects, or workloads.

Transport preserves delivery semantics. Meaning belongs entirely to Runtime domains.

## Session Revocation

Networking never invents authorization changes. Authorization changes originate exclusively in the Trust domain.

Trust publishes the Runtime Event `TrustRevoked`. This event communicates an authoritative fact. It does not request an action.

### Revocation Handling

Networking subscribes to `TrustRevoked` events. When a matching authorization is revoked, Networking immediately terminates every affected Session.

Session termination is an internal Networking decision. The published Runtime Event remains `TrustRevoked` — Networking does not publish `CloseSession`, because closing a Session is internal behavior, not an inter-domain fact.

### Fast Path and Safety Net

Authorization changes propagate through two complementary mechanisms:

```
TrustRevoked
        │
        ▼
Immediate Session termination
```

and

```
Lease expiration
        │
        ▼
Periodic authorization revalidation
```

Events accelerate convergence. Leases guarantee correctness.

## Ownership

Trust owns authorization. Networking owns Sessions and Transport.

Each Runtime domain reacts to authoritative facts. No Runtime domain directly modifies another domain's state.

### Consequences

This design naturally provides immediate revocation, bounded authorization lifetime, eventual consistency under message loss, independent ownership, and deterministic Session lifecycle.

Correctness derives from ownership, not from perfectly reliable communication.

---

## Session Events

Networking publishes Runtime Events describing the lifecycle of Sessions.

As the authoritative owner of Session state, Networking publishes `SessionEstablished` and `SessionClosed`, following the State Propagation principle defined in `00-philosophy.md`.

These events communicate completed facts. They never request actions from other Runtime domains.

### Session Closure

A Session may close for many reasons: authorization revoked, Lease expiration, transport failure, graceful shutdown, peer disconnect.

Regardless of the cause, Networking publishes the same Runtime Event: `SessionClosed`.

The reason for closure may be included as event metadata. The event itself remains stable.

## Peer Reachability

Networking observes transport connectivity.

Whenever the reachability of a peer changes, Networking publishes the Runtime Event `PeerReachabilityChanged`.

This event communicates only transport reachability. It does not imply authorization, cluster membership, node health, or scheduling eligibility. Those concerns belong to other Runtime domains.

## Membership

Membership is a separate Runtime domain. Networking neither owns nor maintains Membership.

Membership observes the Runtime Events published by Networking:

- `PeerReachabilityChanged`
- `SessionEstablished`
- `SessionClosed`

Using these facts, Membership determines the current set of cluster members (`MemberJoined` / `MemberLeft`). Membership does not require any heartbeat mechanism of its own.

Networking never decides who is a cluster member, cluster topology, or node health. Those responsibilities belong to Membership (and Health, respectively).

> Networking, Membership, and Health answer three distinct, non-overlapping questions: *Can I communicate with this peer?* (Networking), *Is it currently part of the cluster?* (Membership), *Is it operationally fit to serve?* (Health). A peer can be reachable yet Draining, or can lose Membership before ever reporting a Health change — the three axes fail independently.

## Relationship with State Assembler

State Assembler observes Membership, Health, and Resource information.

Networking does not build Cluster Snapshots. Networking merely publishes Session and reachability facts.

State Assembler integrates information from multiple Runtime domains to construct a consistent Runtime view.

## Relationship with Scheduling

Scheduling never communicates directly with Networking. Scheduling consumes Cluster Snapshots.

Networking contributes indirectly through the Session information incorporated into Membership and State Assembler.

```
Networking
    │
    ▼
Membership
    │
    ▼
State Assembler
    │
    ▼
Cluster Snapshot
    │
    ▼
Scheduling
```

Each Runtime domain owns one stage of the pipeline.

## Relationship with Transport

Transport is an internal Networking responsibility. Transport provides reliable movement of Runtime Streams.

Transport does not authenticate peers, authorize Sessions, maintain Membership, or understand Runtime semantics.

Transport moves bytes. Networking owns meaning.

## Failure Handling

Networking assumes communication is unreliable. Connections may fail. Messages may be delayed, duplicated, or lost.

Correctness never depends on perfect communication. Networking relies on Session ownership, Runtime Events, and Session Leases to preserve correctness despite unreliable transport.

### Connection Recovery

Loss of a transport connection does not necessarily imply permanent loss of a Runtime relationship.

Networking may establish a new transport connection and continue communication, provided identity is authenticated, authorization succeeds, and the Session Lease remains valid.

Otherwise, a new Session must be established.

## Runtime Independence

Networking provides communication services. It never schedules work, allocates resources, executes workloads, or stores authoritative Runtime state.

Networking remains independent from Runtime policy. Its responsibility is communication. Nothing more.

---

## Runtime Interfaces

Networking exposes Service Contracts, Data Contracts, and Runtime Events following the principles defined in `00-philosophy.md` and `02-project-structure.md`.

Networking never exposes transport-specific APIs to other Runtime domains. Implementation technologies remain encapsulated inside Networking.

### Outbound Ports

Networking may depend on infrastructure through Outbound Ports. Examples include:

- Transport Adapter
- Discovery Adapter
- Cryptographic Identity Provider

These Ports belong to Networking because Networking is their consumer. Implementations remain replaceable.

> Sessions are not persisted. A Session is a live communication relationship — if the Networking process restarts, transport connections, Streams, and Leases are lost regardless, and there is nothing meaningful to resume: identity must be re-authenticated and authorization re-queried from Trust either way. Sessions therefore fail the persistence test from `00-philosophy.md` ("authoritative persistence exists only for state that cannot be reconstructed by observing reality again") — a Session *can*, and must, be reconstructed by re-running the same pipeline that created it. No Session Persistence port exists. A future transport-level optimization (e.g. resuming a TLS/QUIC session across a process restart, or connection handoff between nodes) may exist as a transport implementation detail, but is never an architectural responsibility of Networking — consistent with "the model is larger than today's implementation."

### Inbound Ports

Networking exposes Runtime services through Inbound Ports. Examples include `SessionService` and `DiscoveryService`.

These interfaces describe Networking capabilities. They never expose implementation details of the underlying transport.

### Runtime Events

Networking publishes Runtime Events describing only Networking-owned state:

- `PeerReachabilityChanged`
- `SessionEstablished`
- `SessionClosed`

Networking never publishes events describing Membership, Trust, Health, Scheduling, or Allocation. Those facts belong to their respective authoritative owners.

## Technology Independence

The Networking architecture is independent of any transport technology. Possible implementations include libp2p, QUIC, TCP, Unix Domain Sockets (local Runtime), and future transports.

Replacing one transport implementation with another should not require architectural changes.

Technology implements Networking. Technology does not define Networking.

## Security

Networking authenticates identities. Trust authorizes identities.

Networking enforces authorization decisions by controlling Session lifecycle.

Cryptographic mechanisms belong to Networking. Authorization policy belongs to Trust. Authentication and authorization remain independent responsibilities.

## Extensibility

Future Networking capabilities should naturally fit the existing ownership model. Examples include multiplexed transports, relay nodes, NAT traversal, alternative discovery mechanisms, and transport optimization.

These capabilities extend Networking. They do not redefine its responsibilities.

## Relationship with the Runtime

Networking collaborates with multiple Runtime domains. It owns only communication.

Networking does not admit work, schedule work, allocate resources, execute workloads, assemble Runtime state, determine Membership, evaluate Health, or preserve authoritative Runtime knowledge.

Those responsibilities remain isolated within their respective Runtime domains.

## Architecture Summary

Networking provides authenticated Runtime communication.

Discovery identifies peers. Authentication verifies identity. Trust authorizes participation. Sessions establish Runtime relationships. Transport carries Runtime Streams. Membership derives cluster participation. State Assembler constructs a coherent Runtime view. Scheduling consumes Runtime state.

Each Runtime domain contributes one responsibility. No responsibility overlaps another.

```
Networking
    │
    ├── PeerReachabilityChanged
    ├── SessionEstablished
    └── SessionClosed
            │
            ▼
        Membership
            │
            ├── MemberJoined
            └── MemberLeft
                    │
                    ▼
                Health
                    │
                    └── HealthChanged
                            │
                            ▼
                    State Assembler
                            │
                            ▼
                    Cluster Snapshot
                            │
                            ▼
                        Scheduling
                            │
                            ▼
                        Allocation
                            │
                            ▼
                          Worker
```

Every arrow in this diagram is a change of ownership, not an arbitrary call between components — the Runtime's execution flow is a sequence of authoritative domains publishing facts for the next.

## Principles

- Networking owns communication.
- Networking owns Sessions.
- Networking publishes only Networking facts.
- Authentication and authorization are separate concerns.
- Sessions outlive transport connections when permitted by policy.
- Transport implementations are replaceable.
- Runtime policy remains independent of communication.
- Ownership defines every Networking boundary.

## Closing Statement

Networking exists to move information, not to interpret it.

Its responsibility is to establish secure, authenticated, and reliable Runtime communication while remaining independent from Runtime policy.

By limiting its authority to communication alone, Networking preserves the ownership boundaries on which the entire Runtime architecture depends.
