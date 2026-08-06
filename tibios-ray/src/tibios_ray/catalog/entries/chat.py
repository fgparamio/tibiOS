"""Reference data for the Chat capability group (`design.md`, "Reference
data — the Chat family group").

Filing convenience only (design decision MC12) — the catalog itself is
keyed by family, not capability. `gemma` (slice 4) is also `vision`'s
entire answer for that family and is not restated in `entries/vision.py`.

`CHAT_ENTRIES` is this module's only exported entry point per family
group (MC14 — `entries/__init__.py`'s `ALL_ENTRIES`/`DEFAULT_CATALOG`
assembly is deferred to the final slice). This slice adds `qwen`,
`llama`, `deepseek`; slice 4 appends `gemma`, `mistral`, `kimi` to the
same tuple.

Every `min_vram_bytes` figure is stated data derived from MC13's formula
(`ceil_gib(parameter_count x bits/8 x 1.2)`), copied verbatim from
`design.md`'s worked Reference data table — not recomputed here.
`context_window` is the natively published window, not an extended one
(MC5/MC13's neighbouring decisions on `catalog/model.py`).
"""

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import ModelFamily
from tibios_ray.catalog.model import BackendSupport, ModelDescriptor
from tibios_ray.catalog.names import PublishedModelName
from tibios_ray.selection.policy import Quantization

_LLAMA_CPP = BackendId("llama_cpp")
_VLLM = BackendId("vllm")
_TENSORRT_LLM = BackendId("tensorrt_llm")

_Q4_K_M = Quantization(scheme="q4_k_m", bits=4)
_Q8_0 = Quantization(scheme="q8_0", bits=8)
_FP16 = Quantization(scheme="fp16", bits=16)
_FP8 = Quantization(scheme="fp8", bits=8)
_AWQ = Quantization(scheme="awq", bits=4)
_GPTQ = Quantization(scheme="gptq", bits=4)

_QWEN = ModelFamily("qwen")
_LLAMA = ModelFamily("llama")
_DEEPSEEK = ModelFamily("deepseek")

QWEN_ENTRIES: tuple[ModelDescriptor, ...] = (
    ModelDescriptor(
        # The deliberate five-row flagship (design.md): exercises every
        # BackendSupport shape the type permits — two tiers on one
        # backend, a multi-scheme tier, and the same tier on two backends.
        name=PublishedModelName("Qwen/Qwen3-8B"),
        family=_QWEN,
        parameter_count=8_200_000_000,
        context_window=32_768,
        serving=frozenset(
            {
                BackendSupport(
                    backend=_LLAMA_CPP, quantizations=frozenset({_Q4_K_M}), min_vram_bytes=5
                ),
                BackendSupport(
                    backend=_LLAMA_CPP, quantizations=frozenset({_Q8_0}), min_vram_bytes=10
                ),
                BackendSupport(
                    backend=_VLLM, quantizations=frozenset({_FP16}), min_vram_bytes=20
                ),
                BackendSupport(
                    backend=_VLLM, quantizations=frozenset({_AWQ, _GPTQ}), min_vram_bytes=5
                ),
                BackendSupport(
                    backend=_TENSORRT_LLM, quantizations=frozenset({_FP16}), min_vram_bytes=20
                ),
            }
        ),
    ),
    ModelDescriptor(
        name=PublishedModelName("Qwen/Qwen3-14B"),
        family=_QWEN,
        parameter_count=14_800_000_000,
        context_window=32_768,
        serving=frozenset(
            {
                BackendSupport(
                    backend=_LLAMA_CPP, quantizations=frozenset({_Q4_K_M}), min_vram_bytes=9
                ),
                BackendSupport(
                    backend=_VLLM, quantizations=frozenset({_FP16}), min_vram_bytes=36
                ),
                BackendSupport(
                    backend=_VLLM, quantizations=frozenset({_AWQ, _GPTQ}), min_vram_bytes=9
                ),
            }
        ),
    ),
    ModelDescriptor(
        name=PublishedModelName("Qwen/Qwen3-32B"),
        family=_QWEN,
        parameter_count=32_800_000_000,
        context_window=32_768,
        serving=frozenset(
            {
                BackendSupport(
                    backend=_VLLM, quantizations=frozenset({_FP16}), min_vram_bytes=79
                ),
                BackendSupport(
                    backend=_VLLM, quantizations=frozenset({_AWQ, _GPTQ}), min_vram_bytes=20
                ),
                BackendSupport(
                    backend=_TENSORRT_LLM, quantizations=frozenset({_FP16}), min_vram_bytes=79
                ),
            }
        ),
    ),
    ModelDescriptor(
        name=PublishedModelName("Qwen/Qwen3-30B-A3B"),
        family=_QWEN,
        parameter_count=30_500_000_000,
        context_window=32_768,
        serving=frozenset(
            {
                BackendSupport(
                    backend=_VLLM, quantizations=frozenset({_FP16}), min_vram_bytes=74
                ),
                BackendSupport(
                    backend=_VLLM, quantizations=frozenset({_AWQ, _GPTQ}), min_vram_bytes=19
                ),
            }
        ),
    ),
    ModelDescriptor(
        name=PublishedModelName("Qwen/Qwen2.5-7B-Instruct"),
        family=_QWEN,
        parameter_count=7_600_000_000,
        context_window=32_768,
        serving=frozenset(
            {
                BackendSupport(
                    backend=_LLAMA_CPP, quantizations=frozenset({_Q4_K_M}), min_vram_bytes=5
                ),
                BackendSupport(
                    backend=_VLLM, quantizations=frozenset({_FP16}), min_vram_bytes=19
                ),
            }
        ),
    ),
)

LLAMA_ENTRIES: tuple[ModelDescriptor, ...] = (
    ModelDescriptor(
        # Canonical form (design.md): NOT `Meta-Llama-3.1-8B-Instruct`,
        # whose vendor-echoed org token derives to `meta_llama` — see
        # `test_names.py`'s documented non-derivable-exclusion cases.
        name=PublishedModelName("meta-llama/Llama-3.1-8B-Instruct"),
        family=_LLAMA,
        parameter_count=8_030_000_000,
        context_window=131_072,
        serving=frozenset(
            {
                BackendSupport(
                    backend=_LLAMA_CPP, quantizations=frozenset({_Q4_K_M}), min_vram_bytes=5
                ),
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
        name=PublishedModelName("meta-llama/Llama-3.3-70B-Instruct"),
        family=_LLAMA,
        parameter_count=70_600_000_000,
        context_window=131_072,
        serving=frozenset(
            {
                BackendSupport(
                    backend=_VLLM, quantizations=frozenset({_FP16}), min_vram_bytes=170
                ),
                BackendSupport(
                    backend=_VLLM, quantizations=frozenset({_AWQ, _GPTQ}), min_vram_bytes=43
                ),
                BackendSupport(
                    backend=_TENSORRT_LLM, quantizations=frozenset({_FP16}), min_vram_bytes=170
                ),
            }
        ),
    ),
    ModelDescriptor(
        name=PublishedModelName("meta-llama/Llama-3.2-3B-Instruct"),
        family=_LLAMA,
        parameter_count=3_210_000_000,
        context_window=131_072,
        serving=frozenset(
            {
                BackendSupport(
                    backend=_LLAMA_CPP, quantizations=frozenset({_Q4_K_M}), min_vram_bytes=2
                ),
                BackendSupport(
                    backend=_VLLM, quantizations=frozenset({_FP16}), min_vram_bytes=8
                ),
            }
        ),
    ),
)

DEEPSEEK_ENTRIES: tuple[ModelDescriptor, ...] = (
    ModelDescriptor(
        # No llama_cpp row: a 671B model is a multi-node deployment;
        # claiming single-GPU GGUF support would be catalog fiction.
        name=PublishedModelName("deepseek-ai/DeepSeek-V3"),
        family=_DEEPSEEK,
        parameter_count=671_000_000_000,
        context_window=163_840,
        serving=frozenset(
            {
                BackendSupport(
                    backend=_VLLM, quantizations=frozenset({_FP8}), min_vram_bytes=805
                ),
                BackendSupport(
                    backend=_VLLM, quantizations=frozenset({_AWQ, _GPTQ}), min_vram_bytes=403
                ),
                BackendSupport(
                    backend=_TENSORRT_LLM, quantizations=frozenset({_FP8}), min_vram_bytes=805
                ),
            }
        ),
    ),
    ModelDescriptor(
        # Excludes deepseek-ai/DeepSeek-R1-Distill-Qwen-32B deliberately —
        # see test_names.py's documented non-derivable-exclusion cases
        # (a cross-lineage distill has no single truthful family).
        name=PublishedModelName("deepseek-ai/DeepSeek-R1"),
        family=_DEEPSEEK,
        parameter_count=671_000_000_000,
        context_window=163_840,
        serving=frozenset(
            {
                BackendSupport(
                    backend=_VLLM, quantizations=frozenset({_FP8}), min_vram_bytes=805
                ),
                BackendSupport(
                    backend=_TENSORRT_LLM, quantizations=frozenset({_FP8}), min_vram_bytes=805
                ),
            }
        ),
    ),
)

# Union so far — slice 4 appends GEMMA_ENTRIES/MISTRAL_ENTRIES/KIMI_ENTRIES
# to this same tuple (MC14: entries/__init__.py's assembly is deferred to
# the final slice, but chat.py's own union lands incrementally).
CHAT_ENTRIES: tuple[ModelDescriptor, ...] = QWEN_ENTRIES + LLAMA_ENTRIES + DEEPSEEK_ENTRIES
