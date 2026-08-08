"""`tensorrt-llm-text-backend` spec, Requirement "Injectable SDK Protocol
for SDK-Free Unit Testing" — Scenario "Unit tests run without
tensorrt_llm or CUDA installed": importing `tibios_ray.engines.tensorrt`
must never import `tensorrt_llm` (design.md "Technical Approach", LC11's
lazy `importlib` seam, inherited via VL8)."""

import sys


def test_importing_the_module_does_not_import_tensorrt_llm() -> None:
    assert "tensorrt_llm" not in sys.modules

    import tibios_ray.engines.tensorrt  # noqa: F401

    assert "tensorrt_llm" not in sys.modules
