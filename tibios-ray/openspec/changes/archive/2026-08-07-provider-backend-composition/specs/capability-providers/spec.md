# Delta for Capability Providers

## MODIFIED Requirements

### Requirement: No-Backend Execution Failure Is Wiring-Scoped

Chat, Embedding, and Rerank Providers (*wired*) dispatch to an injected
Backend via the [ADR-0002](../../../../../docs/adr/0002-provider-backend-selection-delegation.md)
flow instead of raising unconditionally; they fail only when their
injected backend mapping is empty or the resolved plan names a
`BackendId` absent from it (dispatch mechanics fixed by the
`provider-backend-composition` spec). Vision, Speech (transcribe and
synthesize), and OCR Providers (*unwired*) keep raising
`NoBackendAvailableError` unconditionally, exactly as before.
(Previously: "Uniform No-Backend Execution Failure" — every Provider's
`execute()` raised `NoBackendAvailableError` unconditionally, with no
wired/unwired distinction.)

#### Scenario: Unwired Provider direct execute() call raises NoBackendAvailableError

- GIVEN one of the four unwired Providers (Vision, Speech-transcribe, Speech-synthesize, OCR) and a valid `ExecutionContext`
- WHEN `execute()` is awaited directly
- THEN `NoBackendAvailableError` is raised and no `ExecutionReport` is returned

#### Scenario: Unwired Provider dispatch surfaces a Failed report, not a bare exception

- GIVEN a `WorkerRuntime` whose registry resolves to one of the four unwired Providers
- WHEN `WorkerRuntime.execute()` dispatches to that Provider
- THEN `WorkerRuntime` catches the raised `NoBackendAvailableError` and returns an `ExecutionReport` with `phase == FAILED` — no exception escapes the Worker Contract boundary

#### Scenario: Wired Provider dispatches instead of raising when its mapping and policy resolve a backend

- GIVEN Chat, Embedding, or Rerank Provider constructed with a non-empty backend mapping and a policy that resolves a valid plan
- WHEN `execute()` is awaited
- THEN `NoBackendAvailableError` is not raised — the Provider dispatches per the `provider-backend-composition` spec

#### Scenario: Wired Provider fails when its injected mapping is empty

- GIVEN Chat, Embedding, or Rerank Provider constructed with an empty backend mapping
- WHEN `execute()` is awaited
- THEN execution fails — no backend is available to dispatch to

#### Scenario: Wired Provider fails when the resolved plan names a backend absent from its mapping

- GIVEN Chat, Embedding, or Rerank Provider whose injected mapping does not contain the `BackendId` named by `ModelSelectionPolicy.plan()`
- WHEN `execute()` is awaited
- THEN execution fails — it never falls back to a different entry in the mapping

### Requirement: Binding Invariants Carried Forward From the Frozen Contracts

No Provider MUST hardcode a concrete model name outside its descriptor's
catalog data, reference `local-infer`, encode a size/cost routing
conditional, or invent a new backend protocol for vision, speech, or OCR.
No Provider MUST construct, discover, or mutate a Backend — the three
wired Providers instead hold their backend mapping and selection policy
only as constructor-injected, immutable fields
([ADR-0001](../../../../../docs/adr/0001-provider-backend-composition.md),
[ADR-0002](../../../../../docs/adr/0002-provider-backend-selection-delegation.md)).
`src/tibios_ray/capabilities/` MUST NOT import from `src/tibios_ray/runtime/`.
(Previously: "Providers hold no backend reference" — a zero-field
invariant enforced identically across all seven Providers, with no
carve-out for an injected, immutable mapping.)

#### Scenario: No hardcoded model, local-infer reference, or size/cost routing conditional exists in unwired modules

- GIVEN the four unwired Provider module source files
- WHEN searched for hardcoded model names, `local-infer` references, or size/cost routing conditionals, including any conditional branch
- THEN none are found — these four modules remain zero-branching

#### Scenario: Providers construct, discover, or mutate no Backend

- GIVEN the seven Provider classes
- WHEN inspected for how any Backend reference reaches them
- THEN none constructs, looks up, discovers, or mutates a Backend at any point; the three wired Providers instead hold a constructor-injected, immutable `Mapping[BackendId, ...]` and one `ModelSelectionPolicy`, set once at construction and never reassigned; no new backend protocol type is defined for vision, speech, or OCR

#### Scenario: capabilities/ imports nothing from runtime/

- GIVEN the `src/tibios_ray/capabilities/` module tree after this change
- WHEN its imports are traced
- THEN none resolve to `src/tibios_ray/runtime/`

#### Scenario: Dispatch-mechanical conditionals in wired Providers are not routing violations

- GIVEN the three wired Provider modules
- WHEN their `execute()` bodies are inspected for conditionals
- THEN only dispatch-mechanical checks are present — empty backend mapping, an unresolvable `plan.backend`, and cooperative cancellation — and none constitutes a size/cost routing decision or backend-selection logic (enforced by the `provider-backend-composition` spec)
