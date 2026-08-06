"""Pyright-only fixture proving `ModelSelectionPolicy.plan` structurally
rejects a bare model-family string, per the `model-selection-policy` spec
Requirement "Input Restricted to Resolved Model ObjectId": "passing a
bare family string ('deepseek') is structurally impossible -- fails
type-check or rejected at interface boundary." This is also the concrete
enforcement of the proposal's binding boundary rule: "Model Selection
Policy can never accept a raw family string."

This module is never imported by pytest and asserts nothing at runtime
(the function below is never called) — its only job is to be
type-checked by `uv run pyright`, which is included via `pyproject.toml`
`[tool.pyright] include = ["src", "tests"]`.

`# type: ignore[arg-type]` below suppresses the *expected* argument-type
error where a raw `str` is passed where `ModelSelectionPolicy.plan`
requires a `ResolvedModelRef`. `pyproject.toml` sets
`reportUnnecessaryTypeIgnoreComment = true`: if `plan`'s signature is ever
loosened to also accept `str` (readmitting family-string discovery), the
underlying argument-type error disappears, the ignore comment becomes
unnecessary, and `uv run pyright` fails the build on
`reportUnnecessaryTypeIgnoreComment` — turning a silent architecture regression
into a hard CI failure instead of a comment nobody notices.
"""

from tibios_ray.execution.context import ResolvedModelRef
from tibios_ray.selection.policy import ModelSelectionPolicy, ServingConstraints, ServingPlan


def _rejects_bare_family_string(
    policy: ModelSelectionPolicy,
    constraints: ServingConstraints,
) -> ServingPlan:
    return policy.plan("deepseek", constraints)  # type: ignore[arg-type]


def _accepts_resolved_model_ref(
    policy: ModelSelectionPolicy,
    model: ResolvedModelRef,
    constraints: ServingConstraints,
) -> ServingPlan:
    # Control case: the one shape `plan` actually accepts, with no ignore
    # comment — proves the fixture above is testing a real rejection, not
    # a signature pyright would reject for any argument.
    return policy.plan(model, constraints)
