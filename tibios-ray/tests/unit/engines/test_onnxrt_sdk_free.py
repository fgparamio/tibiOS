"""`onnxruntime-backend` spec, Requirement "Injectable InferenceSessionLike
and Tokenizer Seams Enable SDK-Free Unit Testing" — Scenario "The
default factories import the SDK only when invoked": importing
`tibios_ray.engines.onnxrt` must never import `onnxruntime`,
`transformers`, **or `numpy`** (design decision OR6's stricter claim —
the tokenizer's `return_tensors="np"` is the only would-be numpy
producer, and it is default-factory-only, so the module itself stays
numpy-free too). Mirrors `test_llamacpp_sdk_free.py`/`test_vllm_sdk_free.py`.
"""

import sys


def test_importing_the_module_does_not_import_onnxruntime_transformers_or_numpy() -> None:
    assert "onnxruntime" not in sys.modules
    assert "transformers" not in sys.modules
    assert "numpy" not in sys.modules

    import tibios_ray.engines.onnxrt  # noqa: F401

    assert "onnxruntime" not in sys.modules
    assert "transformers" not in sys.modules
    assert "numpy" not in sys.modules
