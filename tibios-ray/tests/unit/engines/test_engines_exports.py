"""`tibios_ray.engines` re-exports its public vocabulary at the package
level, so consumers write `from tibios_ray.engines import
LlamaCppTextBackend` rather than reaching into `engines.llamacpp` —
mirrors `tests/unit/backends/test_backends_exports.py`.
"""

import tibios_ray.engines as engines


def test_package_exports_all_slice_1_public_names() -> None:
    expected = {"LLAMA_CPP_BACKEND_ID", "LlamaCppTextBackend", "LlamaLike"}
    assert expected <= set(engines.__all__)
    for name in expected:
        assert hasattr(engines, name), f"tibios_ray.engines.{name} missing"


def test_package_exports_vllm_backend_public_names() -> None:
    expected = {"VLLM_BACKEND_ID", "VllmTextBackend", "AsyncLLMLike"}
    assert expected <= set(engines.__all__)
    for name in expected:
        assert hasattr(engines, name), f"tibios_ray.engines.{name} missing"


def test_package_exports_onnxrt_backend_public_names() -> None:
    expected = {
        "ONNXRUNTIME_BACKEND_ID",
        "OnnxEmbeddingBackend",
        "OnnxRerankBackend",
        "InferenceSessionLike",
        "TokenizerLike",
    }
    assert expected <= set(engines.__all__)
    for name in expected:
        assert hasattr(engines, name), f"tibios_ray.engines.{name} missing"


def test_package_exports_tensorrt_backend_public_names() -> None:
    expected = {"TENSORRT_LLM_BACKEND_ID", "TensorrtLlmTextBackend", "LLMLike"}
    assert expected <= set(engines.__all__)
    for name in expected:
        assert hasattr(engines, name), f"tibios_ray.engines.{name} missing"
