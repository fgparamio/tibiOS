"""Protocol conformance for `OnnxEmbeddingBackend`/`OnnxRerankBackend`
(`onnxruntime-backend` spec, Requirement "Structural Conformance to
EmbeddingBackend and RerankBackend").

Typed bindings, not `isinstance`: neither protocol is
`@runtime_checkable` (design decision D1), so pyright's static
assignment check is the only conformance proof possible — mirrors
`test_llamacpp_conformance.py`/`test_vllm_conformance.py`. The negative
assertions (`OnnxEmbeddingBackend` has no `rerank` attribute and vice
versa) are OR5's own stated discriminator: `supports()` cannot tell the
two modalities apart, so the static protocol type — and therefore the
*absence* of the other modality's method — is the only thing that can.
"""

from collections.abc import Sequence

from tibios_ray.backends.embedding import EmbeddingBackend
from tibios_ray.backends.rerank import RerankBackend
from tibios_ray.engines.onnxrt import (
    InferenceSessionLike,
    OnnxEmbeddingBackend,
    OnnxRerankBackend,
    TokenizerLike,
    _OnnxBackendBase,
)


def _never_called_session_factory(
    model_path: str, providers: Sequence[str]
) -> InferenceSessionLike:
    raise AssertionError("session factory must not be invoked for a typed binding")


def _never_called_tokenizer_factory(tokenizer_path: str) -> TokenizerLike:
    raise AssertionError("tokenizer factory must not be invoked for a typed binding")


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


def test_onnx_embedding_backend_satisfies_embedding_backend() -> None:
    # The assignment itself is the conformance proof: pyright rejects
    # this line if `OnnxEmbeddingBackend` does not structurally satisfy
    # `EmbeddingBackend` (`uv run pyright`).
    backend: EmbeddingBackend = _embedding_backend()
    assert backend.backend_id.value == "onnxruntime"


def test_onnx_rerank_backend_satisfies_rerank_backend() -> None:
    backend: RerankBackend = _rerank_backend()
    assert backend.backend_id.value == "onnxruntime"


def test_onnx_backends_share_the_private_base_not_the_protocol() -> None:
    # OR5: sharing via a private base is not D1's prohibition (that bans
    # inheriting the *Protocol*) — both concrete types inherit
    # `_OnnxBackendBase`, never `EmbeddingBackend`/`RerankBackend`.
    assert OnnxEmbeddingBackend.__bases__ == (_OnnxBackendBase,)
    assert OnnxRerankBackend.__bases__ == (_OnnxBackendBase,)


def test_onnx_embedding_backend_has_no_rerank_attribute() -> None:
    assert not hasattr(_embedding_backend(), "rerank")


def test_onnx_rerank_backend_has_no_embed_attribute() -> None:
    assert not hasattr(_rerank_backend(), "embed")
