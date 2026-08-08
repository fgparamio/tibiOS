"""Composition root for the tibios-ray Worker Contract entity.

This is the single place inside tibios-ray where "Worker" refers to the
entity seen by tibios-core's Runtime over gRPC (per
``../tibios-core/docs/architecture/18-worker-model.md``). It builds a
:class:`tibios_ray.runtime.registry.CapabilityRegistry` from the seven
concrete Capability Providers and hands it to exactly one
:class:`tibios_ray.runtime.worker_runtime.WorkerRuntime` — the whole
composition ``server.py`` needs before it can call
``transport.serve(build_runtime(), address)``. Imports zero ``grpc``/
``_pb2`` symbol (design decision D13); the gRPC transport that calls into
this composition lives entirely in ``transport/``.

Design decision D29: ``build_runtime()`` stays a plain function that
constructs a fresh engine set per call — ``None`` means
``WorkerConfig.from_env()``. "Constructed once at startup" is guaranteed
by there being exactly one call in production (``server.py``), not by
memoization; a module-global/``lru_cache``d singleton would be global
mutable state shared across the whole test suite (design.md D29's own
rationale — the tension ``proposal.md`` flags, unchanged from D6).

Per the ``provider-backend-composition`` spec's "Composition Root
Exclusive Backend Ownership": this is the *only* module in
``src/tibios_ray/`` that constructs a concrete Backend/engine instance
(``LlamaCppTextBackend``, ``VllmTextBackend``, ``TensorrtLlmTextBackend``,
``OnnxEmbeddingBackend``, ``OnnxRerankBackend``) — enforced by
``tests/unit/test_worker.py``'s constructor-call-scan guard (task 7.6).
``engines/__init__.py``'s
package-level re-export of those same classes is API aliasing, not
construction, and is not a violation. No wired Provider constructs,
looks up, or discovers a Backend; each is handed an already-built,
immutable mapping plus the one shared ``ModelSelectionPolicy`` instance
(ADR-0001/ADR-0002).
"""

from tibios_ray.backends.adapter import BackendId
from tibios_ray.backends.embedding import EmbeddingBackend
from tibios_ray.backends.rerank import RerankBackend
from tibios_ray.backends.text import TextGenerationBackend
from tibios_ray.capabilities.chat import ChatProvider
from tibios_ray.capabilities.embedding import EmbeddingProvider
from tibios_ray.capabilities.ocr import OcrProvider
from tibios_ray.capabilities.rerank import RerankProvider
from tibios_ray.capabilities.speech import SpeechSynthesisProvider, SpeechTranscriptionProvider
from tibios_ray.capabilities.vision import VisionProvider
from tibios_ray.config import WorkerConfig
from tibios_ray.engines import (
    LLAMA_CPP_BACKEND_ID,
    ONNXRUNTIME_BACKEND_ID,
    TENSORRT_LLM_BACKEND_ID,
    VLLM_BACKEND_ID,
    LlamaCppTextBackend,
    OnnxEmbeddingBackend,
    OnnxRerankBackend,
    TensorrtLlmTextBackend,
    VllmTextBackend,
)
from tibios_ray.runtime.registry import CapabilityRegistry
from tibios_ray.runtime.worker_runtime import WorkerRuntime
from tibios_ray.selection.preference import PreferenceOrderPolicy

# D28's preference tuple is a Composition Root output — "prefer vLLM over
# llama.cpp on this box" is a deployment belief, not something a policy
# discovers. This order (vLLM before llama.cpp) is a judgment call, not a
# measurement (mirrors `config.py`'s `DEFAULT_LLAMACPP_POOL_SIZE`,
# `engines/llamacpp.py`'s `_DEFAULT_ACQUIRE_TIMEOUT_SECONDS`): vLLM's
# continuous batching serves concurrent chat requests with higher
# throughput than a fixed-size llama.cpp pool, so on a box with both
# configured this is the more useful default. `onnxruntime` never
# competes with either — it backs only `embedding`/`rerank`, disjoint
# capabilities — but is listed for completeness of the total order D28
# requires `PreferenceOrderPolicy` to be able to fall back to.
#
# D33: TensorRT-LLM is inserted second, right after vLLM — both are
# GPU-resident, higher-throughput engines than llama.cpp's CPU-first
# pool, and neither ranks above the other by measurement; vLLM keeps
# its existing first-place slot (an insertion, not a reorder) purely to
# avoid re-litigating D28's already-shipped judgment call.
_BACKEND_PREFERENCE: tuple[BackendId, ...] = (
    VLLM_BACKEND_ID,
    TENSORRT_LLM_BACKEND_ID,
    LLAMA_CPP_BACKEND_ID,
    ONNXRUNTIME_BACKEND_ID,
)


def build_runtime(config: WorkerConfig | None = None) -> WorkerRuntime:
    """Builds the one `CapabilityRegistry` from the seven Capability
    Providers and hands it to the one `WorkerRuntime`.

    `config` defaults to `WorkerConfig.from_env()` — the only place in
    the codebase besides `config.py` itself permitted to read process
    configuration (`worker-configuration` spec: "Composition Root Is the
    Configuration Surface's Sole Consumer"). Each per-engine Backend is
    constructed only when its config is present — absent configuration
    means the matching entry is simply omitted from the injected
    mapping, never a fabricated or partially-built Backend
    (`worker-configuration` spec: "Worker starts with zero configuration
    present", "A partially configured deployment wires only the
    configured engines")."""

    config = config if config is not None else WorkerConfig.from_env()
    policy = PreferenceOrderPolicy(preference=_BACKEND_PREFERENCE)

    text: dict[BackendId, TextGenerationBackend] = {}
    if config.llamacpp is not None:
        text[LLAMA_CPP_BACKEND_ID] = LlamaCppTextBackend(
            model_path=config.llamacpp.model_path,
            pool_size=config.llamacpp.pool_size,
        )
    if config.vllm is not None:
        text[VLLM_BACKEND_ID] = VllmTextBackend(model=config.vllm.model)
    if config.tensorrt_llm is not None:
        text[TENSORRT_LLM_BACKEND_ID] = TensorrtLlmTextBackend(
            engine_path=config.tensorrt_llm.engine_path
        )

    embedding: dict[BackendId, EmbeddingBackend] = {}
    if config.onnx_embedding is not None:
        embedding[ONNXRUNTIME_BACKEND_ID] = OnnxEmbeddingBackend(
            model_path=config.onnx_embedding.model_path,
            tokenizer_path=config.onnx_embedding.tokenizer_path,
            output_name=config.onnx_embedding.output_name,
        )

    rerank: dict[BackendId, RerankBackend] = {}
    if config.onnx_rerank is not None:
        rerank[ONNXRUNTIME_BACKEND_ID] = OnnxRerankBackend(
            model_path=config.onnx_rerank.model_path,
            tokenizer_path=config.onnx_rerank.tokenizer_path,
            output_name=config.onnx_rerank.output_name,
        )

    providers = (
        ChatProvider(backends=text, selection_policy=policy),
        EmbeddingProvider(backends=embedding, selection_policy=policy),
        OcrProvider(),
        RerankProvider(backends=rerank, selection_policy=policy),
        SpeechTranscriptionProvider(),
        SpeechSynthesisProvider(),
        VisionProvider(),
    )
    return WorkerRuntime(CapabilityRegistry(providers))
