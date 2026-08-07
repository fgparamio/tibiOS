"""Engine package — SDK-bound concrete Backend Adapters (design.md
"Technical Approach": "`backends/` is the contract package. `engines/`
is the new SDK-bound package"). Re-exports the public llama.cpp, vLLM,
and ONNX Runtime surface so consumers write `from tibios_ray.engines
import LlamaCppTextBackend` / `VllmTextBackend` / `OnnxEmbeddingBackend`
rather than reaching into `engines.llamacpp` / `engines.vllm` /
`engines.onnxrt` directly — mirrors `tibios_ray.backends`'s
package-exports convention.

Nothing outside `engines/` constructs `LlamaCppTextBackend`,
`VllmTextBackend`, `OnnxEmbeddingBackend`, or `OnnxRerankBackend` yet —
no composition root exists (`worker.py` is blocked on
`proto-worker-contract`, design.md "Technical Approach").
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
    "ONNXRUNTIME_BACKEND_ID",
    "OnnxEmbeddingBackend",
    "OnnxRerankBackend",
    "InferenceSessionLike",
    "TokenizerLike",
]
