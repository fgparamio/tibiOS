"""`tensorrt-llm-text-backend` spec, Requirement "supports() Is a
Backend-Family Check Only, Never Model Selection" — `supports(plan)`
MUST check only `plan.backend == BackendId("tensorrt_llm")`, true
regardless of `plan.model` — mirrors `test_vllm_supports.py` (VL4/LC12
precedent)."""

import pytest

from tibios_ray.backends.adapter import BackendId
from tibios_ray.engines.tensorrt import TENSORRT_LLM_BACKEND_ID, LLMLike, TensorrtLlmTextBackend


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


async def _never_called_factory(engine_path: str) -> LLMLike:
    raise AssertionError("factory must not be invoked by supports()")


def _backend() -> TensorrtLlmTextBackend:
    return TensorrtLlmTextBackend(engine_path="/engines/m", engine_factory=_never_called_factory)


def test_supports_is_true_for_tensorrt_llm_backend_id() -> None:
    assert _backend().supports(_Plan(BackendId("tensorrt_llm"))) is True


@pytest.mark.parametrize("backend_id", ["llama_cpp", "vllm", "onnxruntime"])
def test_supports_is_false_for_every_other_backend_id(backend_id: str) -> None:
    assert _backend().supports(_Plan(BackendId(backend_id))) is False


def test_tensorrt_backend_id_constant_matches_the_backend_property() -> None:
    assert _backend().backend_id == TENSORRT_LLM_BACKEND_ID
    assert TENSORRT_LLM_BACKEND_ID == BackendId("tensorrt_llm")


def test_supports_ignores_a_plan_exposing_only_backend() -> None:
    # VL4/D33: the model is structurally invisible to supports() — a
    # plan exposing nothing but `.backend` still works, regardless of
    # which model the plan targets.
    class _BackendOnlyPlan:
        def __init__(self) -> None:
            self.backend = TENSORRT_LLM_BACKEND_ID

    assert _backend().supports(_BackendOnlyPlan()) is True
