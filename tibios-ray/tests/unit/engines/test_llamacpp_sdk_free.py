"""`llamacpp-text-backend` spec, Requirement "Injectable Llama Factory
for SDK-Free Unit Testing" — Scenario "The default factory imports the
SDK only when invoked": importing `tibios_ray.engines.llamacpp` must
never import `llama_cpp` (design decision LC11)."""

import sys


def test_importing_the_module_does_not_import_llama_cpp() -> None:
    assert "llama_cpp" not in sys.modules

    import tibios_ray.engines.llamacpp  # noqa: F401

    assert "llama_cpp" not in sys.modules
