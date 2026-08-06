"""Reference data for the Embedding capability group (`design.md` line
400, "Remaining groups").

Filing convenience only (design decision MC12) — the catalog itself is
keyed by family, not capability. `CHAT_ENTRIES` and its neighbours
follow the same shape.

`EMBEDDING_ENTRIES` is this module's only exported entry point per
family group (MC14 — `entries/__init__.py`'s `ALL_ENTRIES`/
`DEFAULT_CATALOG` assembly is deferred to the final slice).

Unlike the Chat family group (slices 3-4), `design.md` has no worked
Reference data table for `bge`/`nomic_embed`/`e5`/`jina_embeddings` —
only the family/model-name list (line 400). Every `min_vram_bytes`
figure here is therefore *derived*, not copied, from MC13's formula
(`ceil_gib(parameter_count x bits/8 x 1.2)`), using each model's
publicly published parameter count. `context_window` is the natively
published window.

Every `BackendSupport` row uses `onnxruntime` — the only backend
`capabilities/embedding.py`'s `EMBEDDING_GENERATE_DESCRIPTOR` advertises
for these families (`capability-providers` spec, "Embedding/Rerank
advertise none"). Two quantization tiers are used throughout: `int8`
(8 bits) and `fp32` (32 bits) — the two precisions ONNX Runtime
embedding exports commonly ship. Where both tiers round to the same
whole-GiB figure at a given parameter count, they share one
`BackendSupport` row (design decision MC5's pattern: `quantizations` on
a row holds every scheme sharing one `min_vram_bytes`).
"""

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import ModelFamily
from tibios_ray.catalog.model import BackendSupport, ModelDescriptor
from tibios_ray.catalog.names import PublishedModelName
from tibios_ray.selection.policy import Quantization

_ONNXRUNTIME = BackendId("onnxruntime")

_INT8 = Quantization(scheme="int8", bits=8)
_FP32 = Quantization(scheme="fp32", bits=32)

_BGE = ModelFamily("bge")
_NOMIC_EMBED = ModelFamily("nomic_embed")
_E5 = ModelFamily("e5")
_JINA_EMBEDDINGS = ModelFamily("jina_embeddings")

BGE_ENTRIES: tuple[ModelDescriptor, ...] = (
    ModelDescriptor(
        # XLM-RoBERTa-large backbone, 568M params, 8192-token context —
        # the multilingual/multi-granularity flagship of the family.
        name=PublishedModelName("BAAI/bge-m3"),
        family=_BGE,
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
    ModelDescriptor(
        # BERT-large backbone, 335M params, 512-token context.
        name=PublishedModelName("BAAI/bge-large-en-v1.5"),
        family=_BGE,
        parameter_count=335_000_000,
        context_window=512,
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

NOMIC_EMBED_ENTRIES: tuple[ModelDescriptor, ...] = (
    ModelDescriptor(
        # Nomic BERT backbone, 137M params, 8192-token context. int8
        # and fp32 both round to 1 GiB at this parameter count, so they
        # share one row.
        name=PublishedModelName("nomic-ai/nomic-embed-text-v1.5"),
        family=_NOMIC_EMBED,
        parameter_count=137_000_000,
        context_window=8192,
        serving=frozenset(
            {
                BackendSupport(
                    backend=_ONNXRUNTIME,
                    quantizations=frozenset({_INT8, _FP32}),
                    min_vram_bytes=1,
                ),
            }
        ),
    ),
)

E5_ENTRIES: tuple[ModelDescriptor, ...] = (
    ModelDescriptor(
        # XLM-RoBERTa-large backbone, 560M params, 512-token context.
        name=PublishedModelName("intfloat/multilingual-e5-large"),
        family=_E5,
        parameter_count=560_000_000,
        context_window=512,
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
    ModelDescriptor(
        # BERT-large backbone, 335M params, 512-token context.
        name=PublishedModelName("intfloat/e5-large-v2"),
        family=_E5,
        parameter_count=335_000_000,
        context_window=512,
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

JINA_EMBEDDINGS_ENTRIES: tuple[ModelDescriptor, ...] = (
    ModelDescriptor(
        # XLM-RoBERTa backbone with task-specific LoRA adapters, 572M
        # params, 8192-token context.
        name=PublishedModelName("jinaai/jina-embeddings-v3"),
        family=_JINA_EMBEDDINGS,
        parameter_count=572_000_000,
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

EMBEDDING_ENTRIES: tuple[ModelDescriptor, ...] = (
    BGE_ENTRIES + NOMIC_EMBED_ENTRIES + E5_ENTRIES + JINA_EMBEDDINGS_ENTRIES
)
