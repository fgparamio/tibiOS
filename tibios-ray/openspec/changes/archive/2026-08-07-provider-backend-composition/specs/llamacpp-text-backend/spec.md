# Delta for Llama.cpp Text Backend

## MODIFIED Requirements

### Requirement: Residency Is Backend-Owned, Not Request-Owned

A ready-to-use model residency MUST exist before any request is served.
Constructing a residency MUST belong to the Backend's own lifecycle
([ADR-0003](../../../../../docs/adr/0003-backend-resource-ownership.md)),
never to a request's `acquire()` call — `acquire(plan)` MUST return an
existing residency without constructing one, and MUST NOT block on model
construction. `release(session)` MUST return the residency to the Backend
for reuse, not discard it. When no residency is available, `acquire(plan)`
MUST wait up to a configured timeout for one to become free, then raise
`PoolExhaustedError` if none does within that timeout — the timeout bounds
the wait for an available residency, not the duration of any inference. The
number of residencies the Backend maintains MUST be operator-configurable,
not a fixed constant.

This requirement constrains observable behavior only. It does not name a
pool, a queue, or any other concurrency mechanism — those are implementation
choices documented in `design.md`, free to change without revisiting this
requirement.

#### Scenario: No model is constructed while serving a request

- GIVEN a Backend that has already finished constructing its residencies
- WHEN `acquire(plan)` is awaited for any request
- THEN no model-construction call happens during that `acquire(plan)` — the
  underlying model already existed

#### Scenario: Construction happens exactly once per residency, at Backend construction time

- GIVEN a Backend configured for `N` residencies
- WHEN the Backend is constructed, followed by `M > N` sequential
  `acquire()`/`release()` cycles
- THEN the model-construction call is made exactly `N` times, all during
  Backend construction, and never again regardless of `M`

#### Scenario: release returns the residency for reuse, not destruction

- GIVEN an acquired residency
- WHEN `release(session)` is awaited
- THEN the underlying model instance remains usable and becomes available
  to a subsequent `acquire(plan)` — it is not torn down

#### Scenario: Exhaustion waits, then fails explicitly — no other behavior is invented

- GIVEN every residency is currently acquired and none is released before
  the configured timeout elapses
- WHEN another `acquire(plan)` is awaited
- THEN it waits up to the configured timeout and then raises
  `PoolExhaustedError`; `release(session)` is never called for that
  attempt, since no residency was ever handed out

#### Scenario: Residency count is operator-configured, not hardcoded

- GIVEN two Backends of the same kind configured with different residency
  counts
- WHEN each is constructed
- THEN each constructs exactly its own configured number of residencies —
  the count is read from configuration, not a constant in the Backend's
  source
