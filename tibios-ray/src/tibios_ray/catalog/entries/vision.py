"""Reference data for the Vision capability group.

Two families only (design decision MC12): `qwen_vl`, `llama_vision`.
`gemma` is also `vision.understand`'s advertised family, but its three
entries already live in `entries/chat.py` (slice 4) and are deliberately
**not** restated here — the catalog is keyed by family, not capability,
and one lineage (`gemma`) legitimately serves two capabilities
(`chat.generate` and `vision.understand`). The descriptor <-> catalog
consistency check that validates this (entry backends <= the *union* of
every descriptor advertising the family) is deferred to slice 8's
`test_catalog_consistency.py`, per design.md's "assert only their own
data" per-group test scoping.

`VISION_ENTRIES` is this module's only exported entry point per family
group (MC14 — `entries/__init__.py`'s `ALL_ENTRIES`/`DEFAULT_CATALOG`
assembly is deferred to the final slice).

Unlike the Chat family group (slices 3-4), `design.md`'s worked
Reference data table does not cover `qwen_vl`/`llama_vision` — only the
family/model-name list (line 400, "Remaining groups"). Every
`min_vram_bytes` figure here is therefore *derived*, not copied, from
MC13's formula (`ceil_gib(parameter_count x bits/8 x 1.2)`), using the
decimal-GB (`bytes / 1e9`, ceiling) interpretation established in slice
5's `entries/embedding.py`/`entries/rerank.py` (reverse-engineered from
`entries/chat.py`'s own accepted figures — e.g. Llama-3.3-70B's fp16 row
reproduces exactly under `bytes / 1e9`, not `bytes / 2**30`).
`context_window` is the natively published window, matching each
lineage's sibling text-only entry in `entries/chat.py` where one exists
(Qwen2.5-VL mirrors `Qwen2.5-7B-Instruct`'s 32_768; Llama-3.2-Vision
mirrors the other Llama 3.2 entries' 131_072).

Every `BackendSupport` row here uses `vllm` or `tensorrt_llm` only.
`capabilities/vision.py`'s `VISION_UNDERSTAND_DESCRIPTOR.backends` is
`{vllm, tensorrt_llm}` — no `llama_cpp` — unlike `entries/chat.py`'s
`gemma` rows, which do advertise `llama_cpp` under `chat.generate`;
MC8's union rule is what reconciles the two capabilities' backend sets
for `gemma`, and it does not apply here since neither `qwen_vl` nor
`llama_vision` is advertised by any other capability.
"""

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import ModelFamily
from tibios_ray.catalog.model import BackendSupport, ModelDescriptor
from tibios_ray.catalog.names import PublishedModelName
from tibios_ray.selection.policy import Quantization

_VLLM = BackendId("vllm")
_TENSORRT_LLM = BackendId("tensorrt_llm")

_FP16 = Quantization(scheme="fp16", bits=16)
_AWQ = Quantization(scheme="awq", bits=4)
_GPTQ = Quantization(scheme="gptq", bits=4)

_QWEN_VL = ModelFamily("qwen_vl")
_LLAMA_VISION = ModelFamily("llama_vision")

QWEN_VL_ENTRIES: tuple[ModelDescriptor, ...] = (
    ModelDescriptor(
        # 8.29B params, 32_768-token native context (matches the text
        # Qwen2.5-7B-Instruct entry in chat.py). No llama_cpp row: the
        # vision descriptor does not advertise it.
        name=PublishedModelName("Qwen/Qwen2.5-VL-7B-Instruct"),
        family=_QWEN_VL,
        parameter_count=8_290_000_000,
        context_window=32_768,
        serving=frozenset(
            {
                BackendSupport(
                    backend=_VLLM, quantizations=frozenset({_FP16}), min_vram_bytes=20
                ),
                BackendSupport(
                    backend=_VLLM, quantizations=frozenset({_AWQ, _GPTQ}), min_vram_bytes=5
                ),
            }
        ),
    ),
    ModelDescriptor(
        # 73.4B params, 32_768-token native context.
        name=PublishedModelName("Qwen/Qwen2.5-VL-72B-Instruct"),
        family=_QWEN_VL,
        parameter_count=73_400_000_000,
        context_window=32_768,
        serving=frozenset(
            {
                BackendSupport(
                    backend=_VLLM, quantizations=frozenset({_FP16}), min_vram_bytes=177
                ),
                BackendSupport(
                    backend=_VLLM, quantizations=frozenset({_AWQ, _GPTQ}), min_vram_bytes=45
                ),
                BackendSupport(
                    backend=_TENSORRT_LLM, quantizations=frozenset({_FP16}), min_vram_bytes=177
                ),
            }
        ),
    ),
)

LLAMA_VISION_ENTRIES: tuple[ModelDescriptor, ...] = (
    ModelDescriptor(
        # 10.6B params, 131_072-token native context (matches the other
        # Llama 3.2 entries in chat.py). No llama_cpp row: the vision
        # descriptor does not advertise it.
        name=PublishedModelName("meta-llama/Llama-3.2-11B-Vision-Instruct"),
        family=_LLAMA_VISION,
        parameter_count=10_600_000_000,
        context_window=131_072,
        serving=frozenset(
            {
                BackendSupport(
                    backend=_VLLM, quantizations=frozenset({_FP16}), min_vram_bytes=26
                ),
                BackendSupport(
                    backend=_VLLM, quantizations=frozenset({_AWQ, _GPTQ}), min_vram_bytes=7
                ),
            }
        ),
    ),
)

VISION_ENTRIES: tuple[ModelDescriptor, ...] = QWEN_VL_ENTRIES + LLAMA_VISION_ENTRIES
