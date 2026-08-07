# Model Selection Policy Specification

## Purpose

Given an already-resolved concrete Model ObjectId, the Model Selection Policy decides HOW to serve it: which backend and which quantization/precision. It MUST be structurally incapable of accepting a raw family string and picking a model itself — that is scheduling-time discovery, forbidden for Workers per `18-worker-model.md` ("Dependency References already resolved").

## Requirements

### Requirement: Input Is Restricted to a Resolved Model ObjectId

The Model Selection Policy's entry point MUST accept only an already-resolved concrete Model ObjectId. Its signature MUST NOT offer any parameter, overload, or code path that accepts a raw model-family string (e.g. `"deepseek"`) as a substitute for a resolved ObjectId.

#### Scenario: Policy invoked with a resolved ObjectId returns a serving decision

- GIVEN a concrete, resolved Model ObjectId
- WHEN the Model Selection Policy is invoked
- THEN it returns a decision containing exactly a backend choice and a quantization/precision choice

#### Scenario: Passing a bare family string is structurally impossible

- GIVEN the Model Selection Policy's public entry point signature
- WHEN inspected (type signature and/or attempted call with a bare `str` family name)
- THEN no accepted parameter type or overload permits a bare family string; the call fails type-checking or is rejected at the interface boundary

### Requirement: Decision Scope Excludes Model Discovery

The Model Selection Policy MUST limit its output to backend and quantization/precision selection. It MUST NOT perform family-to-model resolution, catalog search, or any other form of model discovery.

#### Scenario: Decision output contains no discovery step

- GIVEN a resolved Model ObjectId as input
- WHEN the Model Selection Policy produces its decision
- THEN the decision references only backend and quantization/precision — no alternate model, family match, or catalog lookup is performed or returned

### Requirement: A Concrete ModelSelectionPolicy Implementation Exists

The system MUST provide at least one concrete class structurally
satisfying `ModelSelectionPolicy`, constructed by the Composition Root
and injected into each wired Provider
([ADR-0002](../../../docs/adr/0002-provider-backend-selection-delegation.md)).
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
