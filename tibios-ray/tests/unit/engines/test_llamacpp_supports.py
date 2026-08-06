"""`llamacpp-text-backend` spec, Requirement "An Engine Never Performs
Model Selection" — `supports(plan)` MUST check only
`plan.backend == BackendId("llama_cpp")`, never model identity
(design decision LC12)."""

import pytest

from tibios_ray.backends.adapter import BackendId
from tibios_ray.engines.llamacpp import LLAMA_CPP_BACKEND_ID, LlamaCppTextBackend, LlamaLike


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


def _never_called_factory(model_path: str) -> LlamaLike:
    raise AssertionError("factory must not be invoked by supports()")


def _backend() -> LlamaCppTextBackend:
    return LlamaCppTextBackend(model_path="model.gguf", factory=_never_called_factory)


def test_supports_is_true_for_llama_cpp_backend_id() -> None:
    assert _backend().supports(_Plan(BackendId("llama_cpp"))) is True


@pytest.mark.parametrize("backend_id", ["vllm", "tensorrt_llm", "onnxruntime"])
def test_supports_is_false_for_every_other_backend_id(backend_id: str) -> None:
    assert _backend().supports(_Plan(BackendId(backend_id))) is False


def test_llama_cpp_backend_id_constant_matches_the_backend_property() -> None:
    assert _backend().backend_id == LLAMA_CPP_BACKEND_ID
    assert LLAMA_CPP_BACKEND_ID == BackendId("llama_cpp")
