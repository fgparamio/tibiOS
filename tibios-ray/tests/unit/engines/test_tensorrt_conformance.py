"""Protocol conformance for `TensorrtLlmTextBackend`
(`tensorrt-llm-text-backend` spec, Requirement "Structural Conformance to
TextGenerationBackend").

A typed binding, not `isinstance`: `TextGenerationBackend` is a
structural `typing.Protocol`, not `@runtime_checkable` (design decision
D1 inherited), so pyright's static assignment check is the only
conformance proof possible — mirrors `test_vllm_conformance.py` (VL
precedent).
"""

from tibios_ray.backends.text import TextGenerationBackend
from tibios_ray.engines.tensorrt import LLMLike, TensorrtLlmTextBackend


async def _never_called_factory(engine_path: str) -> LLMLike:
    raise AssertionError("factory must not be invoked for a typed binding")


def test_tensorrt_text_backend_satisfies_text_generation_backend() -> None:
    # The assignment itself is the conformance proof: pyright rejects
    # this line if `TensorrtLlmTextBackend` does not structurally
    # satisfy `TextGenerationBackend` (no base class, `uv run pyright`).
    backend: TextGenerationBackend = TensorrtLlmTextBackend(
        engine_path="/engines/m", engine_factory=_never_called_factory
    )
    assert backend.backend_id.value == "tensorrt_llm"


def test_tensorrt_text_backend_inherits_from_no_base_class() -> None:
    assert TensorrtLlmTextBackend.__bases__ == (object,)
