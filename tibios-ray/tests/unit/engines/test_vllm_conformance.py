"""Protocol conformance for `VllmTextBackend` (`vllm-text-backend` spec,
Requirement "Structural Conformance to TextGenerationBackend").

A typed binding, not `isinstance`: `TextGenerationBackend` is a
structural `typing.Protocol`, not `@runtime_checkable` (design decision
D1), so pyright's static assignment check is the only conformance proof
possible — mirrors `test_llamacpp_conformance.py` (LC precedent).
"""

from tibios_ray.backends.text import TextGenerationBackend
from tibios_ray.engines.vllm import AsyncLLMLike, VllmTextBackend


async def _never_called_factory(model: str) -> AsyncLLMLike:
    raise AssertionError("factory must not be invoked for a typed binding")


def test_vllm_text_backend_satisfies_text_generation_backend() -> None:
    # The assignment itself is the conformance proof: pyright rejects
    # this line if `VllmTextBackend` does not structurally satisfy
    # `TextGenerationBackend` (no base class, `uv run pyright`).
    backend: TextGenerationBackend = VllmTextBackend(
        model="m", engine_factory=_never_called_factory
    )
    assert backend.backend_id.value == "vllm"


def test_vllm_text_backend_inherits_from_no_base_class() -> None:
    assert VllmTextBackend.__bases__ == (object,)
