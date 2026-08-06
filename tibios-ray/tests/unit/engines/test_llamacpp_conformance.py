"""Protocol conformance for `LlamaCppTextBackend` (`llamacpp-text-backend`
spec, Requirement "Structural Conformance to TextGenerationBackend").

A typed binding, not `isinstance`: `TextGenerationBackend` is a
structural `typing.Protocol`, not `@runtime_checkable` (design decision
D1), so pyright's static assignment check is the only conformance proof
possible — mirrors `tests/unit/backends/test_text.py`'s
`test_fake_text_backend_satisfies_the_protocol` and the `assert_type`
harness in `tests/unit/backends/test_protocol_conformance.py` (CP7
precedent).
"""

from tibios_ray.backends.text import TextGenerationBackend
from tibios_ray.engines.llamacpp import LlamaCppTextBackend, LlamaLike


def _never_called_factory(model_path: str) -> LlamaLike:
    raise AssertionError("factory must not be invoked for a typed binding")


def test_llamacpp_text_backend_satisfies_text_generation_backend() -> None:
    # The assignment itself is the conformance proof: pyright rejects
    # this line if `LlamaCppTextBackend` does not structurally satisfy
    # `TextGenerationBackend` (no base class, `uv run pyright`).
    backend: TextGenerationBackend = LlamaCppTextBackend(
        model_path="model.gguf", factory=_never_called_factory
    )
    assert backend.backend_id.value == "llama_cpp"


def test_llamacpp_text_backend_inherits_from_no_base_class() -> None:
    assert LlamaCppTextBackend.__bases__ == (object,)
