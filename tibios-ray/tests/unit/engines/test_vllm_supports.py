"""`vllm-text-backend` spec references LC12 (`supports()` is a family
check, never model selection, VL4) — `supports(plan)` MUST check only
`plan.backend == BackendId("vllm")`."""

import pytest

from tibios_ray.backends.adapter import BackendId
from tibios_ray.engines.vllm import VLLM_BACKEND_ID, AsyncLLMLike, VllmTextBackend


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


async def _never_called_factory(model: str) -> AsyncLLMLike:
    raise AssertionError("factory must not be invoked by supports()")


def _backend() -> VllmTextBackend:
    return VllmTextBackend(model="m", engine_factory=_never_called_factory)


def test_supports_is_true_for_vllm_backend_id() -> None:
    assert _backend().supports(_Plan(BackendId("vllm"))) is True


@pytest.mark.parametrize("backend_id", ["llama_cpp", "tensorrt_llm", "onnxruntime"])
def test_supports_is_false_for_every_other_backend_id(backend_id: str) -> None:
    assert _backend().supports(_Plan(BackendId(backend_id))) is False


def test_vllm_backend_id_constant_matches_the_backend_property() -> None:
    assert _backend().backend_id == VLLM_BACKEND_ID
    assert VLLM_BACKEND_ID == BackendId("vllm")


def test_supports_ignores_a_plan_exposing_only_backend() -> None:
    # VL4: the model is structurally invisible to supports() — a plan
    # exposing nothing but `.backend` still works.
    class _BackendOnlyPlan:
        def __init__(self) -> None:
            self.backend = VLLM_BACKEND_ID

    assert _backend().supports(_BackendOnlyPlan()) is True
