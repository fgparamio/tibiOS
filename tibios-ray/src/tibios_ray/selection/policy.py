"""Model Selection Policy contract (`model-selection-policy` spec, design
decision block "selection/").

Given an ALREADY-RESOLVED `ResolvedModelRef` (`execution/context.py`,
Phase 1 — constructible only from `ExecutionContext.dependencies`), this
decides backend + quantization only. It is structurally incapable of
accepting a raw family/model-name string and picking a model itself —
that would be scheduling-time discovery, forbidden per
`18-worker-model.md`: "Dependency References already resolved — Workers
never locate Objects or perform scheduling-time discovery." See
`tests/unit/selection/pyright_fixtures/rejects_bare_family_string.py`
for the type-checker-enforced half of that guarantee.

`selection/` depends on `execution/` (for `ResolvedModelRef`) and
`backends/` (for `BackendId`, and so `ServingPlan` structurally satisfies
`backends/adapter.py`'s `ServingPlanLike` Protocol) — never on
`capabilities/` or `runtime/`, which depend on `selection/`, not the
reverse (module dependency direction: `runtime -> capabilities ->
selection -> backends`).

Quantization/precision shape: `tasks.md` Phase 3 scopes the decision
surface to "backend + quantization" (not a separate `precision` field);
`Quantization(scheme, bits)` uses a backend-scoped scheme token (e.g.
`"fp16"`, `"int8"`, `"int4"`/AWQ/GPTQ) that already carries precision —
see `design.md`'s Open Questions ("Quantization vocabulary owner",
intentionally left open until real backends exist).
"""

from dataclasses import dataclass
from typing import Protocol

from tibios_ray.backends.adapter import BackendId
from tibios_ray.execution.context import ResolvedModelRef


@dataclass(frozen=True, slots=True, kw_only=True)
class Quantization:
    """A backend-scoped quantization/precision scheme, e.g.
    `Quantization(scheme="int4", bits=4)` or
    `Quantization(scheme="fp16", bits=16)`. `scheme` is an opaque token
    interpreted by the chosen `BackendId`'s concrete adapter (Phase 4) —
    Phase 3 does not own a closed vocabulary (see module docstring)."""

    scheme: str
    bits: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ServingConstraints:
    """The subset of Allocation capacity relevant to a serving decision:
    which backends are usable for this execution. `ModelSelectionPolicy`
    compares model footprint against these constraints to choose a
    quantization — this is not the forbidden size/cost Worker-routing
    rule of `25-ai-runtime.md` (the model and the Worker are already
    fixed by the time `plan` is called; see design.md's non-violation
    note)."""

    available_backends: frozenset[BackendId]


@dataclass(frozen=True, slots=True, kw_only=True)
class ServingPlan:
    """The output of a Model Selection Policy decision: which backend to
    use and at what quantization, for an already-resolved model.

    `backend` is a plain top-level attribute (not nested) so that
    `ServingPlan` structurally satisfies `backends/adapter.py`'s
    `ServingPlanLike` Protocol (`.backend -> BackendId`) with zero import
    edge from `backends/` back to `selection/` — see that module's
    docstring for the reasoning (design decision D1: structural typing
    removes import edges)."""

    model: ResolvedModelRef
    backend: BackendId
    quantization: Quantization


class ModelSelectionPolicy(Protocol):
    """Decides backend + quantization for an already-resolved model.

    No overload, default, or alternate entry point accepts a bare
    family/model-name string — the only parameter carrying model
    identity is `model: ResolvedModelRef`. Decision scope excludes model
    discovery: the output (`ServingPlan`) references only backend +
    quantization, never an alternate model/family match or catalog
    lookup."""

    def plan(self, model: ResolvedModelRef, constraints: ServingConstraints) -> ServingPlan: ...
