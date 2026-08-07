"""Engine package — SDK-bound concrete Backend Adapters (design.md
"Technical Approach": "`backends/` is the contract package. `engines/`
is the new SDK-bound package"). Re-exports the public llama.cpp and
vLLM surface so consumers write `from tibios_ray.engines import
LlamaCppTextBackend` / `VllmTextBackend` rather than reaching into
`engines.llamacpp` / `engines.vllm` directly — mirrors
`tibios_ray.backends`'s package-exports convention.

Nothing outside `engines/` constructs `LlamaCppTextBackend` or
`VllmTextBackend` yet — no composition root exists (`worker.py` is
blocked on `proto-worker-contract`, design.md "Technical Approach").
"""

from tibios_ray.engines.llamacpp import (
    LLAMA_CPP_BACKEND_ID,
    LlamaCppTextBackend,
    LlamaLike,
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
]
