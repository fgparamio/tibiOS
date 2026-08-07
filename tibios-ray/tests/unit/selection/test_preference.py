"""Tests for `tibios_ray.selection.preference` — `PreferenceOrderPolicy`,
the first concrete `ModelSelectionPolicy` (`model-selection-policy` spec,
design decision D28).

`PreferenceOrderPolicy` is deterministic and non-scoring: it walks a
Composition-Root-supplied preference order, falls back to a
lexicographically stable default for an unranked `BackendId`, and never
fabricates a plan naming a backend outside `available_backends`.
"""

import pytest

from tibios_ray.backends.adapter import BackendId
from tibios_ray.execution.context import ResolvedModelRef
from tibios_ray.execution.ids import ContentHash, ObjectId, ObjectVersion
from tibios_ray.selection.errors import UnsatisfiablePlanError
from tibios_ray.selection.policy import ServingConstraints
from tibios_ray.selection.preference import ARTIFACT_DEFINED, PreferenceOrderPolicy


def _resolved_model_ref() -> ResolvedModelRef:
    return ResolvedModelRef(
        object_id=ObjectId("01J0000000000000000000000"),
        version=ObjectVersion(18),
        content_hash=ContentHash("sha256:af2398..."),
    )


class TestPreferenceOrderPolicyDeterminism:
    def test_plan_is_deterministic_across_two_identical_calls(self) -> None:
        policy = PreferenceOrderPolicy(preference=(BackendId("vllm"), BackendId("llama_cpp")))
        model = _resolved_model_ref()
        constraints = ServingConstraints(
            available_backends=frozenset({BackendId("llama_cpp"), BackendId("vllm")})
        )

        first = policy.plan(model, constraints)
        second = policy.plan(model, constraints)

        assert first == second


class TestPreferenceOrderPolicyPreferenceOrder:
    def test_preference_order_is_honoured_when_multiple_backends_available(self) -> None:
        policy = PreferenceOrderPolicy(preference=(BackendId("vllm"), BackendId("llama_cpp")))
        model = _resolved_model_ref()
        constraints = ServingConstraints(
            available_backends=frozenset({BackendId("llama_cpp"), BackendId("vllm")})
        )

        plan = policy.plan(model, constraints)

        assert plan.backend == BackendId("vllm")

    def test_second_ranked_backend_is_chosen_when_first_is_unavailable(self) -> None:
        policy = PreferenceOrderPolicy(preference=(BackendId("vllm"), BackendId("llama_cpp")))
        model = _resolved_model_ref()
        constraints = ServingConstraints(available_backends=frozenset({BackendId("llama_cpp")}))

        plan = policy.plan(model, constraints)

        assert plan.backend == BackendId("llama_cpp")


class TestPreferenceOrderPolicyUnrankedFallback:
    def test_unranked_backend_falls_back_to_lexicographically_smallest_value(self) -> None:
        policy = PreferenceOrderPolicy(preference=(BackendId("vllm"),))
        model = _resolved_model_ref()
        constraints = ServingConstraints(
            available_backends=frozenset({BackendId("onnxruntime"), BackendId("llama_cpp")})
        )

        plan = policy.plan(model, constraints)

        assert plan.backend == BackendId("llama_cpp")


class TestPreferenceOrderPolicyEmptyAvailableBackends:
    def test_empty_available_backends_raises_unsatisfiable_plan_error(self) -> None:
        policy = PreferenceOrderPolicy(preference=(BackendId("vllm"),))
        model = _resolved_model_ref()
        constraints = ServingConstraints(available_backends=frozenset())

        with pytest.raises(UnsatisfiablePlanError):
            policy.plan(model, constraints)


class TestPreferenceOrderPolicyPlanNeverOutsideAvailability:
    def test_returned_plan_backend_is_always_a_member_of_available_backends(self) -> None:
        policy = PreferenceOrderPolicy(preference=(BackendId("does_not_exist"),))
        model = _resolved_model_ref()
        available = frozenset({BackendId("llama_cpp"), BackendId("onnxruntime")})
        constraints = ServingConstraints(available_backends=available)

        plan = policy.plan(model, constraints)

        assert plan.backend in available


class TestPreferenceOrderPolicyQuantizationSentinel:
    def test_plan_quantization_is_always_artifact_defined(self) -> None:
        policy = PreferenceOrderPolicy(preference=(BackendId("llama_cpp"),))
        model = _resolved_model_ref()
        constraints = ServingConstraints(available_backends=frozenset({BackendId("llama_cpp")}))

        plan = policy.plan(model, constraints)

        assert plan.quantization == ARTIFACT_DEFINED

    def test_plan_quantization_is_artifact_defined_via_fallback_path_too(self) -> None:
        policy = PreferenceOrderPolicy(preference=())
        model = _resolved_model_ref()
        constraints = ServingConstraints(available_backends=frozenset({BackendId("vllm")}))

        plan = policy.plan(model, constraints)

        assert plan.quantization == ARTIFACT_DEFINED
