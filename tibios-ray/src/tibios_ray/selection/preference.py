"""The first concrete `ModelSelectionPolicy` (`model-selection-policy`
spec, design decision D28): a deterministic, non-scoring
preference-order policy. Constructed and injected by the Composition
Root (`worker.py`) — never constructed by a Provider.
"""

from dataclasses import dataclass

from tibios_ray.backends.adapter import BackendId
from tibios_ray.execution.context import ResolvedModelRef
from tibios_ray.selection.errors import UnsatisfiablePlanError
from tibios_ray.selection.policy import Quantization, ServingConstraints, ServingPlan

ARTIFACT_DEFINED = Quantization(scheme="artifact-defined", bits=0)
"""Sentinel meaning "no runtime quantization choice was made — the
configured artifact is already quantized" (design decision D23). Every
`PreferenceOrderPolicy` plan carries this, never a fabricated scheme,
because for all three current engines quantization is a property of the
artifact chosen at construction, not something a policy can select
among."""


@dataclass(frozen=True, slots=True, kw_only=True)
class PreferenceOrderPolicy:
    """Deterministic backend selection by a Composition-Root-supplied
    preference order (D28).

    `plan()` returns the first `BackendId` in `preference` that is
    present in `constraints.available_backends`. If none of
    `preference` matches, it falls back to the lexicographically
    smallest `BackendId.value` in `available_backends`, so a `BackendId`
    the operator never ranked still yields a plan rather than an
    arbitrary one. An empty `available_backends` raises
    `UnsatisfiablePlanError` — never a fabricated plan. Quantization is
    always `ARTIFACT_DEFINED` (D23)."""

    preference: tuple[BackendId, ...]

    def plan(self, model: ResolvedModelRef, constraints: ServingConstraints) -> ServingPlan:
        if not constraints.available_backends:
            raise UnsatisfiablePlanError(model=model)

        for backend in self.preference:
            if backend in constraints.available_backends:
                return ServingPlan(model=model, backend=backend, quantization=ARTIFACT_DEFINED)

        fallback = min(constraints.available_backends, key=lambda backend: backend.value)
        return ServingPlan(model=model, backend=fallback, quantization=ARTIFACT_DEFINED)
