"""Engine package — SDK-bound concrete Backend Adapters (design.md
"Technical Approach": "`backends/` is the contract package. `engines/`
is the new SDK-bound package"). Re-exports the public llama.cpp, vLLM,
TensorRT-LLM, and ONNX Runtime surface so consumers write
`from tibios_ray.engines import LlamaCppTextBackend` /
`VllmTextBackend` / `TensorrtLlmTextBackend` / `OnnxEmbeddingBackend`
rather than reaching into `engines.llamacpp` / `engines.vllm` /
`engines.tensorrt` / `engines.onnxrt` directly — mirrors
`tibios_ray.backends`'s package-exports convention.

`worker.py` (the Composition Root) is the sole constructor of these
concrete Backend Adapters — this package only re-exports the names,
never constructs them itself.
"""

from tibios_ray.engines.llamacpp import (
    LLAMA_CPP_BACKEND_ID,
    LlamaCppTextBackend,
    LlamaLike,
)
from tibios_ray.engines.onnxrt import (
    ONNXRUNTIME_BACKEND_ID,
    InferenceSessionLike,
    OnnxEmbeddingBackend,
    OnnxRerankBackend,
    TokenizerLike,
)
from tibios_ray.engines.tensorrt import (
    TENSORRT_LLM_BACKEND_ID,
    LLMLike,
    TensorrtLlmTextBackend,
)
from tibios_ray.engines.vllm import (
    VLLM_BACKEND_ID,
    AsyncLLMLike,
    VllmTextBackend,
)

__all__ = [
    "LLAMA_CPP_BACKEND_ID",
    "LlamaCppTextBackend",
    "LlamaLike",
    "VLLM_BACKEND_ID",
    "VllmTextBackend",
    "AsyncLLMLike",
    "TENSORRT_LLM_BACKEND_ID",
    "TensorrtLlmTextBackend",
    "LLMLike",
    "ONNXRUNTIME_BACKEND_ID",
    "OnnxEmbeddingBackend",
    "OnnxRerankBackend",
    "InferenceSessionLike",
    "TokenizerLike",
]
