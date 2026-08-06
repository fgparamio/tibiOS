"""`vllm-text-backend` spec, Requirement "Injectable AsyncLLMLike
Protocol for SDK-Free Unit Testing" — Scenario "The default factory
imports the SDK only when invoked": importing `tibios_ray.engines.vllm`
must never import `vllm` **or** `torch` (design decision VL8, stricter
than llamacpp's `test_llamacpp_sdk_free.py` because vLLM drags torch)."""

import sys


def test_importing_the_module_does_not_import_vllm_or_torch() -> None:
    assert "vllm" not in sys.modules
    assert "torch" not in sys.modules

    import tibios_ray.engines.vllm  # noqa: F401

    assert "vllm" not in sys.modules
    assert "torch" not in sys.modules
