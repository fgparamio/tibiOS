# Provider-Backend Composition Specification

## Purpose

This spec fixes the injection shape and per-request dispatch flow for the
three *wired* Capability Providers (`ChatProvider`, `EmbeddingProvider`,
`RerankProvider`). Construction/ownership rules are [ADR-0001](../../../../../docs/adr/0001-provider-backend-composition.md)
and [ADR-0003](../../../../../docs/adr/0003-backend-resource-ownership.md);
selection delegation is [ADR-0002](../../../../../docs/adr/0002-provider-backend-selection-delegation.md);
payload decoding is [ADR-0004](../../../../../docs/adr/0004-capability-request-boundary.md)
(covered by each capability's own Request type, not restated here). These
ADRs are ground truth — this spec states requirements and scenarios, not
their rationale.

## Requirements

### Requirement: Composition Root Exclusive Backend Ownership

Per ADR-0001, `worker.py::build_runtime()` MUST be the only module that
names a concrete Backend/engine class or constructs one. No wired
Provider MUST construct, look up, or discover a Backend.

#### Scenario: worker.py is the sole importer of concrete engine classes

- GIVEN the `src/tibios_ray/` module tree after this change
- WHEN searched for imports of concrete engine classes (e.g. `LlamaCppTextBackend`, `VllmTextBackend`, `OnnxEmbeddingBackend`, `OnnxRerankBackend`)
- THEN only `worker.py` imports them

### Requirement: Constructor-Injected Immutable Dependencies

Per ADR-0002, each wired Provider MUST be constructed with exactly two
injected fields: an immutable `Mapping[BackendId, <capability's Backend
Protocol>]` and one `ModelSelectionPolicy` instance. Neither MUST be
mutated, replaced, or added to after construction.

#### Scenario: A wired Provider holds exactly its two injected fields

- GIVEN `ChatProvider`, `EmbeddingProvider`, or `RerankProvider`
- WHEN its declared dataclass fields are inspected
- THEN exactly two fields exist: a backend mapping and a selection policy — nothing else

#### Scenario: The injected mapping is immutable after construction

- GIVEN a constructed wired Provider
- WHEN an attempt is made to add, remove, or reassign an entry in its backend mapping after construction
- THEN the attempt fails (frozen dataclass field, immutable mapping type)

### Requirement: Model Reference Selection From Context Dependencies

`ExecutionContext.dependencies` is `tuple[ResolvedModelRef, ...]`
(unkeyed). A wired Provider's `execute()` MUST select one
`ResolvedModelRef` from it before calling `ModelSelectionPolicy.plan()`.
The exact selection rule for more than one entry is a design decision;
this requirement fixes only that the outcome is unambiguous and
repeatable.

#### Scenario: Exactly one dependency is used unambiguously

- GIVEN `context.dependencies` containing exactly one `ResolvedModelRef`
- WHEN a wired Provider's `execute()` runs
- THEN that `ResolvedModelRef` is the one passed to `ModelSelectionPolicy.plan()`

#### Scenario: Zero dependencies fails explicitly, not with an unhandled exception

- GIVEN `context.dependencies` is an empty tuple
- WHEN a wired Provider's `execute()` runs
- THEN execution ends as a distinguishable, handled failure — never an uncaught `IndexError` or similar — and the `ExecutionReport` is not `COMPLETED`

#### Scenario: Multiple dependencies resolve deterministically

- GIVEN `context.dependencies` containing more than one `ResolvedModelRef`
- WHEN the same Provider instance executes twice against equivalent contexts
- THEN the same `ResolvedModelRef` is selected both times

### Requirement: Per-Request Dispatch Flow

Per ADR-0002, a wired Provider's `execute()` MUST: build
`ServingConstraints(available_backends=frozenset(self._backends))`; call
`self._selection_policy.plan(model, constraints)`; look up
`self._backends[plan.backend]`; `acquire(plan)` → capability method
(`generate`/`embed`/`rerank`) → `release(session)`; stream results onto
`context.channel` as `OutputChunk`s terminated by `EndOfStream`; poll
`context.cancellation` cooperatively; return an `ExecutionReport` that
never carries application output (`18-worker-model.md`).

#### Scenario: Successful dispatch streams output and returns COMPLETED

- GIVEN a wired Provider with a non-empty backend mapping and a policy that resolves a valid plan
- WHEN `execute()` runs to completion
- THEN the resolved Backend's `acquire()` is called with the plan, its capability method runs, `release()` is called, one or more `OutputChunk`s are emitted followed by `EndOfStream`, and the returned `ExecutionReport.phase == COMPLETED`

#### Scenario: Cooperative cancellation is observed mid-execution

- GIVEN an execution in progress against a wired Provider
- WHEN `context.cancellation` signals cancelled before the Backend finishes
- THEN the Provider stops driving further output, still releases any acquired session, and the returned `ExecutionReport.phase == CANCELLED`

#### Scenario: ExecutionReport never carries application output

- GIVEN any wired Provider execution, successful or not
- WHEN its `ExecutionReport` is inspected
- THEN none of its fields contain generated text, embedding vectors, or rerank scores — that data appears only as `OutputChunk` events on the channel

### Requirement: Backend Session Release Is Guaranteed

Per ADR-0003's `acquire()`/`release()` cycle, a wired Provider MUST call
`release()` exactly once for every successful `acquire()`, including when
the Backend's capability method raises mid-execution.

#### Scenario: Release happens after the Backend raises mid-stream

- GIVEN an acquired `BackendSession` and a Backend capability method that raises partway through
- WHEN `execute()` handles that exception
- THEN `release(session)` has still been called with that session before `execute()` returns or re-raises

#### Scenario: Release is not called when acquire() itself fails

- GIVEN a Backend whose `acquire()` raises before returning a session
- WHEN `execute()` handles that exception
- THEN `release()` is never called — no session exists to release

### Requirement: Non-Streaming Results Travel Through the Channel

`embedding.generate` and `rerank.documents` produce a batch result, not a
token stream. Their Provider MUST place that result onto `context.channel`
as one or more `OutputChunk`s (`data: bytes`), never as a field on
`ExecutionReport`. The exact byte-level serialization is a design
decision; this requirement fixes only the transport.

#### Scenario: Embedding output appears on the channel, not the report

- GIVEN `EmbeddingProvider.execute()` completing successfully
- WHEN its `ExecutionReport` and channel emissions are inspected
- THEN the embedding vectors appear only among emitted `OutputChunk`s; the `ExecutionReport` carries none of them

#### Scenario: Rerank output appears on the channel, not the report

- GIVEN `RerankProvider.execute()` completing successfully
- WHEN its `ExecutionReport` and channel emissions are inspected
- THEN the rerank scores appear only among emitted `OutputChunk`s; the `ExecutionReport` carries none of them

### Requirement: No Selection Logic Inside Wired Providers

Per ADR-0002, the three wired Providers SHALL NOT implement backend
selection logic — no branching, scoring, or capability-matching inside
`execute()`. Only dispatch-mechanical conditionals are permitted: an
empty backend mapping, a `plan.backend` absent from that mapping, and
cooperative cancellation.

#### Scenario: No scoring or capability-matching code exists

- GIVEN the three wired Provider module source files
- WHEN inspected for logic that chooses among backends based on model/family/size/cost
- THEN no such logic exists — every backend choice originates from `self._selection_policy.plan(...)`

#### Scenario: Every conditional present is dispatch-mechanical

- GIVEN the three wired Providers' `execute()` bodies
- WHEN their conditionals are enumerated
- THEN each guards only an empty mapping, an unresolvable `plan.backend`, or cooperative cancellation — none re-implements what `plan()` already decided

### Requirement: Failure Outcomes Are Behaviorally Distinguishable

A wired Provider's `execute()` MUST produce behaviorally distinguishable
outcomes for: (a) no backend configured (empty mapping); (b) a resolved
plan naming a `BackendId` absent from the mapping; (c) the Backend itself
raising; (d) cancellation. The exact exception/error-type hierarchy is a
design decision; this requirement fixes only that the four are never
collapsed into one indistinguishable catch-all.

#### Scenario: Empty mapping fails distinguishably from an absent-backend plan

- GIVEN a wired Provider constructed with an empty backend mapping
- WHEN `execute()` runs
- THEN it fails identifiably as "no backend configured", distinct from the absent-backend-in-plan case below

#### Scenario: A plan naming an absent backend fails, not silently picks another

- GIVEN a wired Provider whose mapping has one entry and whose policy returns a plan naming a different `BackendId`
- WHEN `execute()` runs
- THEN it fails — it never falls back to the mapping's existing entry or any other backend

#### Scenario: A Backend's own exception propagates as a distinguishable failure

- GIVEN a wired Provider whose Backend raises during `acquire()`/dispatch/`release()`
- WHEN `execute()` runs
- THEN the resulting `FAILED` report's failure information is distinguishable from the two mapping-related cases above

#### Scenario: Cancellation yields CANCELLED, not FAILED

- GIVEN an execution cancelled via `context.cancellation` mid-flight
- WHEN `execute()` observes the cancellation
- THEN `ExecutionReport.phase == CANCELLED`, distinguishable from all three failure cases above
