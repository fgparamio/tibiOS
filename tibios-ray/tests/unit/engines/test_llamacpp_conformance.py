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

from pathlib import Path

from stub_llama import StubLlama

from tibios_ray.backends.text import TextGenerationBackend
from tibios_ray.engines.llamacpp import LlamaCppTextBackend


def _gguf_path(tmp_path: Path) -> str:
    path = tmp_path / "model.gguf"
    path.write_bytes(b"not a real gguf, just needs to exist and be readable")
    return str(path)


def test_llamacpp_text_backend_satisfies_text_generation_backend(tmp_path: Path) -> None:
    # The assignment itself is the conformance proof: pyright rejects
    # this line if `LlamaCppTextBackend` does not structurally satisfy
    # `TextGenerationBackend` (no base class, `uv run pyright`). Slice 6
    # (D26/D27): the pool is built eagerly, so the factory does run
    # once here (pool_size=1) — a real, readable `model_path` is
    # required for construction to succeed at all.
    backend: TextGenerationBackend = LlamaCppTextBackend(
        model_path=_gguf_path(tmp_path), factory=lambda path: StubLlama()
    )
    assert backend.backend_id.value == "llama_cpp"


def test_llamacpp_text_backend_inherits_from_no_base_class() -> None:
    assert LlamaCppTextBackend.__bases__ == (object,)
