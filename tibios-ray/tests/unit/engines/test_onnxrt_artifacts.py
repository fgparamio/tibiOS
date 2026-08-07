"""`onnxruntime-backend` spec, design decision OR10 — "The Artifact
Bundle: every artifact and hardware fact is a construction argument".
`providers` MUST reach the session factory (never `supports()`, which
consults none of these): a deterministic `("CPUExecutionProvider",)`
default when unspecified, and the exact caller-supplied tuple when
one is given.
"""

import asyncio

from stub_onnx import make_stub_session_factory, make_stub_tokenizer_factory

from tibios_ray.backends.adapter import BackendId
from tibios_ray.engines.onnxrt import ONNXRUNTIME_BACKEND_ID, OnnxEmbeddingBackend


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


_PLAN = _Plan(ONNXRUNTIME_BACKEND_ID)


def test_default_providers_reach_the_session_factory() -> None:
    session_factory, sessions = make_stub_session_factory()
    tokenizer_factory, _ = make_stub_tokenizer_factory()
    backend = OnnxEmbeddingBackend(
        model_path="model.onnx",
        tokenizer_path="tok",
        session_factory=session_factory,
        tokenizer_factory=tokenizer_factory,
    )

    asyncio.run(backend.acquire(_PLAN))

    assert sessions[0].providers == ("CPUExecutionProvider",)


def test_custom_providers_reach_the_session_factory() -> None:
    session_factory, sessions = make_stub_session_factory()
    tokenizer_factory, _ = make_stub_tokenizer_factory()
    backend = OnnxEmbeddingBackend(
        model_path="model.onnx",
        tokenizer_path="tok",
        session_factory=session_factory,
        tokenizer_factory=tokenizer_factory,
        providers=("CUDAExecutionProvider", "CPUExecutionProvider"),
    )

    asyncio.run(backend.acquire(_PLAN))

    assert sessions[0].providers == ("CUDAExecutionProvider", "CPUExecutionProvider")


def test_supports_behavior_is_identical_regardless_of_providers() -> None:
    # OR10: `supports()` consults none of the Artifact Bundle fields.
    session_factory, _ = make_stub_session_factory()
    tokenizer_factory, _ = make_stub_tokenizer_factory()
    default_backend = OnnxEmbeddingBackend(
        model_path="model.onnx",
        tokenizer_path="tok",
        session_factory=session_factory,
        tokenizer_factory=tokenizer_factory,
    )
    custom_backend = OnnxEmbeddingBackend(
        model_path="model.onnx",
        tokenizer_path="tok",
        session_factory=session_factory,
        tokenizer_factory=tokenizer_factory,
        providers=("CUDAExecutionProvider",),
    )

    assert default_backend.supports(_PLAN) == custom_backend.supports(_PLAN) is True
