"""Tests for `tibios_ray.selection.policy` — `ModelSelectionPolicy`,
`ServingConstraints`, `ServingPlan`, `Quantization` (`model-selection-policy`
spec, design decision block "selection/").

The whole point of this module is a *narrow* decision surface: given an
already-resolved `ResolvedModelRef` (Phase 1, `execution/context.py`),
decide backend + quantization only. No family/model-name parameter may
exist anywhere on `ModelSelectionPolicy.plan`'s signature — that would be
scheduling-time discovery, forbidden per `18-worker-model.md`. The
runtime-checkable half of that guarantee lives here (signature
introspection); the type-checker half lives in
`tests/unit/selection/pyright_fixtures/rejects_bare_family_string.py`.
"""

import dataclasses
import inspect
import typing
from typing import assert_type

import pytest

from tibios_ray.backends.adapter import BackendId, ServingPlanLike
from tibios_ray.execution.context import ResolvedModelRef
from tibios_ray.execution.ids import ContentHash, ObjectId, ObjectVersion
from tibios_ray.selection.policy import (
    ModelSelectionPolicy,
    Quantization,
    ServingConstraints,
    ServingPlan,
)


def _resolved_model_ref() -> ResolvedModelRef:
    return ResolvedModelRef(
        object_id=ObjectId("01J0000000000000000000000"),
        version=ObjectVersion(18),
        content_hash=ContentHash("sha256:af2398..."),
    )


class TestQuantization:
    def test_holds_scheme_and_bits(self) -> None:
        quantization = Quantization(scheme="int4", bits=4)
        assert quantization.scheme == "int4"
        assert quantization.bits == 4

    def test_is_frozen(self) -> None:
        quantization = Quantization(scheme="int4", bits=4)
        with pytest.raises(dataclasses.FrozenInstanceError):
            quantization.bits = 8  # type: ignore[misc]

    def test_equality_is_by_value(self) -> None:
        assert Quantization(scheme="fp16", bits=16) == Quantization(scheme="fp16", bits=16)
        assert Quantization(scheme="fp16", bits=16) != Quantization(scheme="int8", bits=8)


class TestServingConstraints:
    def test_holds_available_backends(self) -> None:
        constraints = ServingConstraints(
            available_backends=frozenset({BackendId("llama_cpp"), BackendId("vllm")})
        )
        assert constraints.available_backends == frozenset(
            {BackendId("llama_cpp"), BackendId("vllm")}
        )

    def test_is_frozen(self) -> None:
        constraints = ServingConstraints(available_backends=frozenset({BackendId("llama_cpp")}))
        with pytest.raises(dataclasses.FrozenInstanceError):
            constraints.available_backends = frozenset()  # type: ignore[misc]


class TestServingPlan:
    def test_holds_model_backend_and_quantization(self) -> None:
        model = _resolved_model_ref()
        plan = ServingPlan(
            model=model,
            backend=BackendId("llama_cpp"),
            quantization=Quantization(scheme="int4", bits=4),
        )
        assert plan.model == model
        assert plan.backend == BackendId("llama_cpp")
        assert plan.quantization == Quantization(scheme="int4", bits=4)

    def test_is_frozen(self) -> None:
        plan = ServingPlan(
            model=_resolved_model_ref(),
            backend=BackendId("llama_cpp"),
            quantization=Quantization(scheme="int4", bits=4),
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            plan.backend = BackendId("vllm")  # type: ignore[misc]

    def test_satisfies_backends_serving_plan_like(self) -> None:
        # Reconciliation with `backends/adapter.py`'s structural
        # `ServingPlanLike` Protocol (`.backend -> BackendId`) — no
        # import edge from `backends/` to `selection/` is needed;
        # `ServingPlan` merely has to have the right shape.
        plan = ServingPlan(
            model=_resolved_model_ref(),
            backend=BackendId("llama_cpp"),
            quantization=Quantization(scheme="int4", bits=4),
        )
        _accepts_serving_plan_like(plan)
        assert plan.backend == BackendId("llama_cpp")


def _accepts_serving_plan_like(plan: ServingPlanLike) -> None:
    assert_type(plan, ServingPlanLike)


def _accepts_model_selection_policy(policy: ModelSelectionPolicy) -> None:
    assert_type(policy, ModelSelectionPolicy)


class _FakeModelSelectionPolicy:
    """Minimal `ModelSelectionPolicy` conformance fake — no model catalog,
    no discovery, just a fixed decision."""

    def plan(self, model: ResolvedModelRef, constraints: ServingConstraints) -> ServingPlan:
        backend = next(iter(constraints.available_backends))
        return ServingPlan(
            model=model, backend=backend, quantization=Quantization(scheme="fp16", bits=16)
        )


def test_fake_policy_satisfies_the_model_selection_policy_protocol() -> None:
    policy = _FakeModelSelectionPolicy()
    _accepts_model_selection_policy(policy)


def test_fake_policy_plan_decides_only_backend_and_quantization() -> None:
    policy = _FakeModelSelectionPolicy()
    model = _resolved_model_ref()
    constraints = ServingConstraints(available_backends=frozenset({BackendId("onnxruntime")}))

    plan = policy.plan(model, constraints)

    assert plan.model == model
    assert plan.backend == BackendId("onnxruntime")
    assert isinstance(plan.quantization, Quantization)


def test_plan_signature_has_exactly_model_and_constraints_parameters() -> None:
    # No family/model-name parameter exists anywhere on the signature —
    # the decision surface is only (already-resolved model, constraints).
    params = list(inspect.signature(ModelSelectionPolicy.plan).parameters)
    assert params == ["self", "model", "constraints"]


def test_plan_model_parameter_is_typed_as_resolved_model_ref_not_str() -> None:
    hints = typing.get_type_hints(ModelSelectionPolicy.plan)
    assert hints["model"] is ResolvedModelRef
    assert hints["return"] is ServingPlan
