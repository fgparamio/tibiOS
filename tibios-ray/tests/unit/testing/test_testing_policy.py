"""Tests for `tibios_ray.testing.policy` — `FakeModelSelectionPolicy`, an
injectable `ModelSelectionPolicy` double for Capability Provider tests
(`model-selection-policy` spec).
"""

import pytest

from tibios_ray.backends.adapter import BackendId
from tibios_ray.execution.context import ResolvedModelRef
from tibios_ray.execution.ids import ContentHash, ObjectId, ObjectVersion
from tibios_ray.selection.policy import (
    ModelSelectionPolicy,
    Quantization,
    ServingConstraints,
    ServingPlan,
)
from tibios_ray.testing.policy import FakeModelSelectionPolicy


def _resolved_model_ref() -> ResolvedModelRef:
    return ResolvedModelRef(
        object_id=ObjectId("01J0000000000000000000000"),
        version=ObjectVersion(18),
        content_hash=ContentHash("sha256:af2398..."),
    )


def _accepts_model_selection_policy(policy: ModelSelectionPolicy) -> None:
    assert policy is not None


def test_satisfies_the_model_selection_policy_protocol() -> None:
    plan = ServingPlan(
        model=_resolved_model_ref(),
        backend=BackendId("llama_cpp"),
        quantization=Quantization(scheme="artifact-defined", bits=0),
    )
    policy = FakeModelSelectionPolicy(plan=plan)
    _accepts_model_selection_policy(policy)


def test_plan_returns_the_caller_supplied_plan() -> None:
    model = _resolved_model_ref()
    plan = ServingPlan(
        model=model,
        backend=BackendId("vllm"),
        quantization=Quantization(scheme="artifact-defined", bits=0),
    )
    policy = FakeModelSelectionPolicy(plan=plan)
    constraints = ServingConstraints(available_backends=frozenset({BackendId("vllm")}))

    result = policy.plan(model, constraints)

    assert result is plan


def test_plan_raises_the_caller_supplied_exception() -> None:
    error = ValueError("no backend for you")
    policy = FakeModelSelectionPolicy(raises=error)
    model = _resolved_model_ref()
    constraints = ServingConstraints(available_backends=frozenset({BackendId("vllm")}))

    with pytest.raises(ValueError, match="no backend for you"):
        policy.plan(model, constraints)


def test_construction_requires_either_plan_or_raises() -> None:
    with pytest.raises(ValueError):
        FakeModelSelectionPolicy()
