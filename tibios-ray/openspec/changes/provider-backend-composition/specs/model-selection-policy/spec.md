# Delta for Model Selection Policy

## ADDED Requirements

### Requirement: A Concrete ModelSelectionPolicy Implementation Exists

The system MUST provide at least one concrete class structurally
satisfying `ModelSelectionPolicy`, constructed by the Composition Root
and injected into each wired Provider
([ADR-0002](../../../../../docs/adr/0002-provider-backend-selection-delegation.md)).
It MUST be deterministic and MUST NOT perform scoring beyond selecting
among `ServingConstraints.available_backends`.

#### Scenario: A concrete implementation exists and is injected

- GIVEN `worker.py::build_runtime()`
- WHEN it constructs the three wired Providers
- THEN each is injected with a concrete `ModelSelectionPolicy` instance — no wired Provider is left without one

#### Scenario: Deterministic selection for identical inputs

- GIVEN a concrete `ModelSelectionPolicy` implementation and a resolved model
- WHEN `plan()` is called twice with the same model and the same `ServingConstraints`
- THEN both calls return an identical `ServingPlan` — no randomness, no hidden state

### Requirement: plan() Never Returns a Backend Outside Availability Constraints

`plan()` MUST NOT return a `ServingPlan` whose `backend` is absent from
`constraints.available_backends`. When no backend in
`available_backends` can serve the resolved model, `plan()` MUST fail
rather than return a plan naming an unavailable or fabricated backend.

#### Scenario: Plan never names a backend outside the available set

- GIVEN `ServingConstraints.available_backends` containing one or more `BackendId`s
- WHEN `plan()` returns a `ServingPlan`
- THEN `ServingPlan.backend` is a member of `available_backends` — never a `BackendId` invented by the policy

#### Scenario: Empty available_backends yields a failure, not a fabricated plan

- GIVEN `ServingConstraints(available_backends=frozenset())`
- WHEN `plan()` is called
- THEN it fails explicitly rather than returning a `ServingPlan` naming any backend
