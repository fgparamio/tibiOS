# 2. Provider-Backend Selection Delegation

## Status

Accepted — amends [0001](0001-provider-backend-composition.md)

## Context

[ADR-0001](0001-provider-backend-composition.md) states: *"Providers never
construct, look up, or select a Backend. They only execute against the one
they were given."* Exploring the codebase ahead of implementing that
decision surfaced a conflict: `selection/policy.py` already defines
`ModelSelectionPolicy.plan(model, constraints) -> ServingPlan`, a per-request
decision that picks a `BackendId` (plus quantization) out of
`ServingConstraints.available_backends`. This module already exists, is
already accepted (Phase 3), and its own docstring documents the intended
dependency direction `runtime -> capabilities -> selection -> backends` —
i.e. Providers were always meant to consult it.

ADR-0001's Decision conflated three distinct responsibilities under the verb
"select":

1. **Construction** — instantiating a Backend (loading weights, opening a
   session/engine/context).
2. **Ownership** — which component holds the constructed instance and for
   how long.
3. **Selection** — given several already-constructed instances, choosing
   which one handles a given request.

Only (1) and (2) were the actual concern ADR-0001 was written to settle
(stateful Backends must not be built per request). (3) is a legitimate,
separate, already-implemented responsibility that ADR-0001's wording
accidentally forbade.

## Decision

- ADR-0001's construction and ownership rules stand unchanged: Backends are
  built exactly once at startup, owned by the Composition Root, and never
  constructed by a Provider.
- Providers SHALL NOT implement backend selection logic (no branching,
  scoring, or capability-matching code inside a Provider).
- Providers MAY delegate backend selection to an injected
  `ModelSelectionPolicy` and dispatch execution to the pre-constructed
  Backend instance the policy's `ServingPlan.backend` names.
- A Provider is injected, at construction time, with:
  - a fixed, immutable mapping of every pre-built Backend instance it can
    dispatch to, keyed by `BackendId` (e.g.
    `backends: Mapping[BackendId, TextGenerationBackend]` for `ChatProvider`)
  - one `ModelSelectionPolicy` instance
  - both are Composition Root outputs; a Provider never mutates either after
    construction.
- At request time, a Provider's `execute()`:
  1. builds `ServingConstraints(available_backends=frozenset(self._backends))`
  2. calls `plan = self._selection_policy.plan(model, constraints)`
  3. looks up `backend = self._backends[plan.backend]`
  4. dispatches to that backend's capability method (e.g. `backend.generate(...)`)
- This mapping lookup is not a `BackendRegistry`: it is a fixed, injected,
  immutable dict populated once at boot — never a mutable global, service
  locator, or anything a Provider populates or discovers dynamically.

## Consequences

- `selection/policy.py`'s existing `ModelSelectionPolicy` is now explicitly
  in scope for `provider-backend-composition` instead of being ignored and
  revisited weeks later.
- A Provider that only ever has one Backend for its capability still works
  under this decision — its injected mapping just has one entry, and
  `ModelSelectionPolicy.plan()` has nothing to choose between.
- Providers stay trivially testable: inject a fake mapping and a fake
  `ModelSelectionPolicy`, no framework or container needed.
- `ADR-0001`'s original "Backend selection is fixed at startup... switching
  backends at runtime is out of scope" consequence is superseded by this
  ADR: runtime, per-request selection among startup-built instances was
  always the intended shape of `selection/`, and is now explicitly in scope.
- Quantization is carried on the same `ServingPlan` returned by
  `ModelSelectionPolicy.plan()` — this ADR only settles backend dispatch;
  how a Provider or Backend acts on `ServingPlan.quantization` is
  implementation detail for the `provider-backend-composition` change, not
  an architectural decision.
