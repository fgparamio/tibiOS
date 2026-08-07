"""A fake, injectable `ModelSelectionPolicy` (`model-selection-policy`
spec) for Capability Provider tests — returns a caller-supplied
`ServingPlan` or raises a caller-supplied exception, so a Provider test
can exercise its backend-resolution dispatch without a real selection
algorithm.
"""

from tibios_ray.execution.context import ResolvedModelRef
from tibios_ray.selection.policy import ServingConstraints, ServingPlan


class FakeModelSelectionPolicy:
    """A conforming `ModelSelectionPolicy` (Protocol) whose `plan()`
    result is fully controlled by the test: either a fixed `ServingPlan`
    or a fixed exception, set at construction. Exactly one of `plan` /
    `raises` must be supplied."""

    def __init__(
        self,
        *,
        plan: ServingPlan | None = None,
        raises: Exception | None = None,
    ) -> None:
        if plan is None and raises is None:
            raise ValueError("FakeModelSelectionPolicy requires either plan or raises")
        self._plan = plan
        self._raises = raises

    def plan(self, model: ResolvedModelRef, constraints: ServingConstraints) -> ServingPlan:
        if self._raises is not None:
            raise self._raises
        assert self._plan is not None
        return self._plan
