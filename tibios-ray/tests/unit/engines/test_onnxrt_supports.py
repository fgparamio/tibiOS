"""`onnxruntime-backend` spec, Requirement "An Engine Never Performs
Model Selection" (LC12/OR5) — `supports(plan)` MUST check only
`plan.backend == BackendId("onnxruntime")`. Explicitly asserts **both**
concrete classes answer identically: `supports()` cannot distinguish
embedding from rerank (OR5's stated reason two classes exist, since
`ServingPlanLike` exposes only `.backend`)."""

import pytest

from tibios_ray.backends.adapter import BackendId
from tibios_ray.engines.onnxrt import (
    ONNXRUNTIME_BACKEND_ID,
    InferenceSessionLike,
    OnnxEmbeddingBackend,
    OnnxRerankBackend,
    TokenizerLike,
)


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


def _never_called_session_factory(model_path: str, providers) -> InferenceSessionLike:
    raise AssertionError("session factory must not be invoked by supports()")


def _never_called_tokenizer_factory(tokenizer_path: str) -> TokenizerLike:
    raise AssertionError("tokenizer factory must not be invoked by supports()")


def _embedding_backend() -> OnnxEmbeddingBackend:
    return OnnxEmbeddingBackend(
        model_path="model.onnx",
        tokenizer_path="tok",
        session_factory=_never_called_session_factory,
        tokenizer_factory=_never_called_tokenizer_factory,
    )


def _rerank_backend() -> OnnxRerankBackend:
    return OnnxRerankBackend(
        model_path="model.onnx",
        tokenizer_path="tok",
        session_factory=_never_called_session_factory,
        tokenizer_factory=_never_called_tokenizer_factory,
    )


def test_supports_is_true_for_onnxruntime_backend_id_on_embedding_backend() -> None:
    assert _embedding_backend().supports(_Plan(BackendId("onnxruntime"))) is True


def test_supports_is_true_for_onnxruntime_backend_id_on_rerank_backend() -> None:
    assert _rerank_backend().supports(_Plan(BackendId("onnxruntime"))) is True


@pytest.mark.parametrize("backend_id", ["llama_cpp", "vllm", "tensorrt_llm"])
def test_supports_is_false_for_every_other_backend_id_on_embedding_backend(
    backend_id: str,
) -> None:
    assert _embedding_backend().supports(_Plan(BackendId(backend_id))) is False


@pytest.mark.parametrize("backend_id", ["llama_cpp", "vllm", "tensorrt_llm"])
def test_supports_is_false_for_every_other_backend_id_on_rerank_backend(backend_id: str) -> None:
    assert _rerank_backend().supports(_Plan(BackendId(backend_id))) is False


def test_onnx_backend_id_constant_matches_the_backend_property() -> None:
    assert _embedding_backend().backend_id == ONNXRUNTIME_BACKEND_ID
    assert _rerank_backend().backend_id == ONNXRUNTIME_BACKEND_ID
    assert ONNXRUNTIME_BACKEND_ID == BackendId("onnxruntime")


def test_both_classes_answer_supports_identically() -> None:
    # OR5's stated discriminator: supports() cannot tell the modalities
    # apart, so both concrete types must answer every plan identically.
    for backend_id in ("onnxruntime", "llama_cpp", "vllm"):
        plan = _Plan(BackendId(backend_id))
        assert _embedding_backend().supports(plan) == _rerank_backend().supports(plan)
