"""Tests for `tibios_ray.catalog.entries.chat` — the Chat capability
group's reference data (`design.md` "Reference data — the Chat family
group").

Slice 3 delivered `qwen`/`llama`/`deepseek`; slice 4 (this file's
extension) appends `gemma`/`mistral`/`kimi` to the same `CHAT_ENTRIES`
tuple (MC14 — `entries/__init__.py` assembly is deferred to slice 8, so
this module builds its own local `ModelCatalog(CHAT_ENTRIES)` fixture
rather than importing `DEFAULT_CATALOG`).

Per family: family coverage (at least one entry reachable through
`ModelCatalog.models`), one full `ModelDescriptor` equality as a
stability assertion against a hand-built expected value, and the
derivation round-trip `entry.family == family_of(entry.name)` for every
entry in this slice.

`gemma`'s three rows are also the entire `gemma` answer for
`vision.understand` (MC8/MC12, `design.md`'s `gemma` reference-data
subsection) — that cross-capability consistency is asserted once, for
every family, in slice 8's `test_catalog_consistency.py`, not here. This
module only asserts `entries/chat.py`'s own data, same as slice 3.
"""

import pytest

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import ModelFamily
from tibios_ray.catalog.catalog import ModelCatalog
from tibios_ray.catalog.entries.chat import (
    CHAT_ENTRIES,
    DEEPSEEK_ENTRIES,
    GEMMA_ENTRIES,
    KIMI_ENTRIES,
    LLAMA_ENTRIES,
    MISTRAL_ENTRIES,
    QWEN_ENTRIES,
)
from tibios_ray.catalog.model import BackendSupport, ModelDescriptor
from tibios_ray.catalog.names import PublishedModelName, family_of
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


def _catalog() -> ModelCatalog:
    return ModelCatalog(CHAT_ENTRIES)


def _find(entries: tuple[ModelDescriptor, ...], name: str) -> ModelDescriptor:
    for entry in entries:
        if entry.name.value == name:
            return entry
    raise AssertionError(f"no entry named {name!r} in {[e.name.value for e in entries]}")


class TestFamilyCoverage:
    def test_qwen_has_at_least_one_entry(self) -> None:
        assert _catalog().models(ModelFamily("qwen"))

    def test_llama_has_at_least_one_entry(self) -> None:
        assert _catalog().models(ModelFamily("llama"))

    def test_deepseek_has_at_least_one_entry(self) -> None:
        assert _catalog().models(ModelFamily("deepseek"))

    def test_gemma_has_at_least_one_entry(self) -> None:
        assert _catalog().models(ModelFamily("gemma"))

    def test_mistral_has_at_least_one_entry(self) -> None:
        assert _catalog().models(ModelFamily("mistral"))

    def test_kimi_has_at_least_one_entry(self) -> None:
        assert _catalog().models(ModelFamily("kimi"))

    def test_qwen_has_five_entries(self) -> None:
        # Qwen/Qwen3-8B, Qwen3-14B, Qwen3-32B, Qwen3-30B-A3B, Qwen2.5-7B-Instruct
        assert len(QWEN_ENTRIES) == 5

    def test_llama_has_three_entries(self) -> None:
        assert len(LLAMA_ENTRIES) == 3

    def test_deepseek_has_two_entries(self) -> None:
        assert len(DEEPSEEK_ENTRIES) == 2

    def test_gemma_has_three_entries(self) -> None:
        # gemma-3-4b-it, gemma-3-12b-it, gemma-3-27b-it
        assert len(GEMMA_ENTRIES) == 3

    def test_mistral_has_two_entries(self) -> None:
        assert len(MISTRAL_ENTRIES) == 2

    def test_kimi_has_one_entry(self) -> None:
        # moonshotai/Kimi-VL-A3B-Instruct is out of scope: no Provider
        # advertises `kimi_vl`.
        assert len(KIMI_ENTRIES) == 1


class TestDerivationRoundTrip:
    @pytest.mark.parametrize(
        "entry", CHAT_ENTRIES, ids=[entry.name.value for entry in CHAT_ENTRIES]
    )
    def test_entry_family_matches_family_of(self, entry: ModelDescriptor) -> None:
        assert entry.family == family_of(entry.name)


class TestStabilityAssertions:
    def test_qwen3_8b_flagship_full_equality(self) -> None:
        # The deliberate five-row flagship (design.md): two tiers on
        # llama_cpp, a multi-scheme tier on vllm, and the same fp16 tier
        # repeated on vllm and tensorrt_llm.
        expected = ModelDescriptor(
            name=PublishedModelName("Qwen/Qwen3-8B"),
            family=ModelFamily("qwen"),
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
                        backend=_VLLM,
                        quantizations=frozenset({_AWQ, _GPTQ}),
                        min_vram_bytes=5,
                    ),
                    BackendSupport(
                        backend=_TENSORRT_LLM,
                        quantizations=frozenset({_FP16}),
                        min_vram_bytes=20,
                    ),
                }
            ),
        )

        assert _find(QWEN_ENTRIES, "Qwen/Qwen3-8B") == expected

    def test_llama_3_1_8b_instruct_full_equality(self) -> None:
        expected = ModelDescriptor(
            name=PublishedModelName("meta-llama/Llama-3.1-8B-Instruct"),
            family=ModelFamily("llama"),
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
                        backend=_VLLM,
                        quantizations=frozenset({_AWQ, _GPTQ}),
                        min_vram_bytes=5,
                    ),
                }
            ),
        )

        assert _find(LLAMA_ENTRIES, "meta-llama/Llama-3.1-8B-Instruct") == expected

    def test_deepseek_v3_full_equality(self) -> None:
        expected = ModelDescriptor(
            name=PublishedModelName("deepseek-ai/DeepSeek-V3"),
            family=ModelFamily("deepseek"),
            parameter_count=671_000_000_000,
            context_window=163_840,
            serving=frozenset(
                {
                    BackendSupport(
                        backend=_VLLM, quantizations=frozenset({_FP8}), min_vram_bytes=805
                    ),
                    BackendSupport(
                        backend=_VLLM,
                        quantizations=frozenset({_AWQ, _GPTQ}),
                        min_vram_bytes=403,
                    ),
                    BackendSupport(
                        backend=_TENSORRT_LLM,
                        quantizations=frozenset({_FP8}),
                        min_vram_bytes=805,
                    ),
                }
            ),
        )

        assert _find(DEEPSEEK_ENTRIES, "deepseek-ai/DeepSeek-V3") == expected

    def test_deepseek_entries_have_no_llama_cpp_row(self) -> None:
        # A 671B model is a multi-node deployment — claiming single-GPU
        # GGUF support would be catalog fiction (design.md, `deepseek`).
        for entry in DEEPSEEK_ENTRIES:
            assert all(row.backend != _LLAMA_CPP for row in entry.serving)

    def test_gemma_3_12b_it_full_equality(self) -> None:
        expected = ModelDescriptor(
            name=PublishedModelName("google/gemma-3-12b-it"),
            family=ModelFamily("gemma"),
            parameter_count=12_200_000_000,
            context_window=131_072,
            serving=frozenset(
                {
                    BackendSupport(
                        backend=_LLAMA_CPP, quantizations=frozenset({_Q4_K_M}), min_vram_bytes=8
                    ),
                    BackendSupport(
                        backend=_VLLM, quantizations=frozenset({_FP16}), min_vram_bytes=30
                    ),
                    BackendSupport(
                        backend=_VLLM,
                        quantizations=frozenset({_AWQ, _GPTQ}),
                        min_vram_bytes=8,
                    ),
                }
            ),
        )

        assert _find(GEMMA_ENTRIES, "google/gemma-3-12b-it") == expected

    def test_mistral_7b_instruct_v0_3_full_equality(self) -> None:
        expected = ModelDescriptor(
            name=PublishedModelName("mistralai/Mistral-7B-Instruct-v0.3"),
            family=ModelFamily("mistral"),
            parameter_count=7_250_000_000,
            context_window=32_768,
            serving=frozenset(
                {
                    BackendSupport(
                        backend=_LLAMA_CPP, quantizations=frozenset({_Q4_K_M}), min_vram_bytes=5
                    ),
                    BackendSupport(
                        backend=_VLLM, quantizations=frozenset({_FP16}), min_vram_bytes=18
                    ),
                }
            ),
        )

        assert _find(MISTRAL_ENTRIES, "mistralai/Mistral-7B-Instruct-v0.3") == expected

    def test_kimi_k2_instruct_full_equality(self) -> None:
        expected = ModelDescriptor(
            name=PublishedModelName("moonshotai/Kimi-K2-Instruct"),
            family=ModelFamily("kimi"),
            parameter_count=1_000_000_000_000,
            context_window=131_072,
            serving=frozenset(
                {
                    BackendSupport(
                        backend=_VLLM, quantizations=frozenset({_FP8}), min_vram_bytes=1200
                    ),
                    BackendSupport(
                        backend=_VLLM,
                        quantizations=frozenset({_AWQ, _GPTQ}),
                        min_vram_bytes=600,
                    ),
                    BackendSupport(
                        backend=_TENSORRT_LLM,
                        quantizations=frozenset({_FP8}),
                        min_vram_bytes=1200,
                    ),
                }
            ),
        )

        assert _find(KIMI_ENTRIES, "moonshotai/Kimi-K2-Instruct") == expected
