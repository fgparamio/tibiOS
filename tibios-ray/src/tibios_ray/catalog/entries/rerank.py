"""Reference data for the Rerank capability group (`design.md` line 400,
"Remaining groups").

Filing convenience only (design decision MC12) — the catalog itself is
keyed by family, not capability. `RERANK_ENTRIES` is this module's only
exported entry point per family group (MC14 — `entries/__init__.py`'s
`ALL_ENTRIES`/`DEFAULT_CATALOG` assembly is deferred to the final
slice).

Same situation as `entries/embedding.py`: `design.md` has no worked
Reference data table for `bge_reranker`/`jina_reranker` — only the
family/model-name list (line 400). Every `min_vram_bytes` figure here is
*derived*, not copied, from MC13's formula
(`ceil_gib(parameter_count x bits/8 x 1.2)`), using each model's
publicly published parameter count. `context_window` is the natively
published window.

Every `BackendSupport` row uses `onnxruntime` — the only backend
`capabilities/rerank.py`'s `RERANK_DOCUMENTS_DESCRIPTOR` advertises for
these families (`capability-providers` spec, "Embedding/Rerank advertise
none"). Same two quantization tiers as `entries/embedding.py`: `int8`
(8 bits) and `fp32` (32 bits).
"""

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import ModelFamily
from tibios_ray.catalog.model import BackendSupport, ModelDescriptor
from tibios_ray.catalog.names import PublishedModelName
from tibios_ray.selection.policy import Quantization

_ONNXRUNTIME = BackendId("onnxruntime")

_INT8 = Quantization(scheme="int8", bits=8)
_FP32 = Quantization(scheme="fp32", bits=32)

_BGE_RERANKER = ModelFamily("bge_reranker")
_JINA_RERANKER = ModelFamily("jina_reranker")

BGE_RERANKER_ENTRIES: tuple[ModelDescriptor, ...] = (
    ModelDescriptor(
        # Cross-encoder head on the same XLM-RoBERTa-large backbone as
        # bge-m3, 568M params, 8192-token context.
        name=PublishedModelName("BAAI/bge-reranker-v2-m3"),
        family=_BGE_RERANKER,
        parameter_count=568_000_000,
        context_window=8192,
        serving=frozenset(
            {
                BackendSupport(
                    backend=_ONNXRUNTIME, quantizations=frozenset({_INT8}), min_vram_bytes=1
                ),
                BackendSupport(
                    backend=_ONNXRUNTIME, quantizations=frozenset({_FP32}), min_vram_bytes=3
                ),
            }
        ),
    ),
)

JINA_RERANKER_ENTRIES: tuple[ModelDescriptor, ...] = (
    ModelDescriptor(
        # Cross-encoder, 278M params, 1024-token context.
        name=PublishedModelName("jinaai/jina-reranker-v2-base-multilingual"),
        family=_JINA_RERANKER,
        parameter_count=278_000_000,
        context_window=1024,
        serving=frozenset(
            {
                BackendSupport(
                    backend=_ONNXRUNTIME, quantizations=frozenset({_INT8}), min_vram_bytes=1
                ),
                BackendSupport(
                    backend=_ONNXRUNTIME, quantizations=frozenset({_FP32}), min_vram_bytes=2
                ),
            }
        ),
    ),
)

RERANK_ENTRIES: tuple[ModelDescriptor, ...] = BGE_RERANKER_ENTRIES + JINA_RERANKER_ENTRIES
