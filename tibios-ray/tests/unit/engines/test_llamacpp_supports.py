"""`llamacpp-text-backend` spec, Requirement "An Engine Never Performs
Model Selection" — `supports(plan)` MUST check only
`plan.backend == BackendId("llama_cpp")`, never model identity
(design decision LC12)."""

from pathlib import Path

import pytest
from stub_llama import StubLlama

from tibios_ray.backends.adapter import BackendId
from tibios_ray.engines.llamacpp import LLAMA_CPP_BACKEND_ID, LlamaCppTextBackend


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


def _gguf_path(tmp_path: Path) -> str:
    path = tmp_path / "model.gguf"
    path.write_bytes(b"not a real gguf, just needs to exist and be readable")
    return str(path)


def _backend(tmp_path: Path) -> LlamaCppTextBackend:
    # Slice 6 (D26/D27): the pool is built eagerly in `__init__`, so the
    # factory *is* called once here (pool_size=1) — unlike the pre-pool
    # world, `supports()` no longer proves anything about whether the
    # factory runs. `supports()`'s own contract (backend-family check
    # only) is what these tests exercise.
    return LlamaCppTextBackend(
        model_path=_gguf_path(tmp_path), factory=lambda path: StubLlama()
    )


def test_supports_is_true_for_llama_cpp_backend_id(tmp_path: Path) -> None:
    assert _backend(tmp_path).supports(_Plan(BackendId("llama_cpp"))) is True


@pytest.mark.parametrize("backend_id", ["vllm", "tensorrt_llm", "onnxruntime"])
def test_supports_is_false_for_every_other_backend_id(
    backend_id: str, tmp_path: Path
) -> None:
    assert _backend(tmp_path).supports(_Plan(BackendId(backend_id))) is False


def test_llama_cpp_backend_id_constant_matches_the_backend_property(tmp_path: Path) -> None:
    assert _backend(tmp_path).backend_id == LLAMA_CPP_BACKEND_ID
    assert LLAMA_CPP_BACKEND_ID == BackendId("llama_cpp")
