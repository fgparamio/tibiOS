"""Selection-layer failure surface (`model-selection-policy` spec, design
decisions D21/D28).

`UnsatisfiablePlanError` is raised by a `ModelSelectionPolicy` when no
backend in `ServingConstraints.available_backends` can serve the
resolved model — including the trivial case of an empty set. It lives in
`selection/`, not `capabilities/errors.py`, because `selection/` MUST
NOT import `capabilities/` (module dependency direction: `runtime ->
capabilities -> selection -> backends`).
"""

from tibios_ray.execution.context import ResolvedModelRef


class UnsatisfiablePlanError(Exception):
    """Raised by `ModelSelectionPolicy.plan()` when no backend in
    `constraints.available_backends` can serve `model` — the policy
    fails explicitly rather than fabricating a `ServingPlan` naming an
    unavailable or invented backend (`model-selection-policy` spec:
    "plan() Never Returns a Backend Outside Availability Constraints",
    "Empty available_backends yields a failure, not a fabricated
    plan")."""

    def __init__(self, *, model: ResolvedModelRef) -> None:
        self.model = model
        super().__init__(
            f"no backend available to serve {model!r} — "
            "available_backends was empty or none could serve it"
        )
