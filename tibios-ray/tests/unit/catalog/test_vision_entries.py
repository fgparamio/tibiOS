"""Tests for `tibios_ray.catalog.entries.vision` — the Vision capability
group's reference data.

Two families only (design decision MC12): `qwen_vl`, `llama_vision`.
`gemma` is also `vision.understand`'s advertised family, but its three
entries live in `entries/chat.py` (slice 4) and are not restated here —
one lineage legitimately serves two capabilities, and the catalog is
keyed by family, not capability.

Unlike the Chat family group (slices 3-4), `design.md`'s worked
Reference data table does **not** cover `qwen_vl`/`llama_vision` — only
the family/model-name list (line 400, "Remaining groups"). Every
`min_vram_bytes` figure here is therefore *derived*, not copied, from
MC13's formula (`ceil_gib(parameter_count x bits/8 x 1.2)`), the same
decimal-GB (`bytes / 1e9`, ceiling) interpretation established in slice
5's `entries/embedding.py`/`entries/rerank.py`.

Per family: family coverage (at least one entry reachable through
`ModelCatalog.models`), one full `ModelDescriptor` equality as a
stability assertion against a hand-built expected value, and the
derivation round-trip `entry.family == family_of(entry.name)` for every
entry in this slice (MC14 — `entries/__init__.py` assembly is deferred
to slice 8, so this module builds its own local
`ModelCatalog(VISION_ENTRIES)` fixture rather than importing
`DEFAULT_CATALOG`).

Every `BackendSupport` row here uses `vllm` or `tensorrt_llm` only —
`capabilities/vision.py`'s `VISION_UNDERSTAND_DESCRIPTOR.backends` is
`{vllm, tensorrt_llm}`, with no `llama_cpp`, unlike Chat's `gemma`
entries (which do advertise `llama_cpp` elsewhere, under `chat.generate`
— MC8's union rule is what reconciles the two, not this module).
"""

import pytest

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import ModelFamily
from tibios_ray.catalog.catalog import ModelCatalog
from tibios_ray.catalog.entries.vision import (
    LLAMA_VISION_ENTRIES,
    QWEN_VL_ENTRIES,
    VISION_ENTRIES,
)
from tibios_ray.catalog.model import BackendSupport, ModelDescriptor
from tibios_ray.catalog.names import PublishedModelName, family_of
from tibios_ray.selection.policy import Quantization

_VLLM = BackendId("vllm")
_TENSORRT_LLM = BackendId("tensorrt_llm")
_LLAMA_CPP = BackendId("llama_cpp")

_FP16 = Quantization(scheme="fp16", bits=16)
_AWQ = Quantization(scheme="awq", bits=4)
_GPTQ = Quantization(scheme="gptq", bits=4)


def _catalog() -> ModelCatalog:
    return ModelCatalog(VISION_ENTRIES)


def _find(entries: tuple[ModelDescriptor, ...], name: str) -> ModelDescriptor:
    for entry in entries:
        if entry.name.value == name:
            return entry
    raise AssertionError(f"no entry named {name!r} in {[e.name.value for e in entries]}")


class TestFamilyCoverage:
    def test_qwen_vl_has_at_least_one_entry(self) -> None:
        assert _catalog().models(ModelFamily("qwen_vl"))

    def test_llama_vision_has_at_least_one_entry(self) -> None:
        assert _catalog().models(ModelFamily("llama_vision"))

    def test_qwen_vl_has_two_entries(self) -> None:
        # Qwen/Qwen2.5-VL-7B-Instruct, Qwen/Qwen2.5-VL-72B-Instruct
        assert len(QWEN_VL_ENTRIES) == 2

    def test_llama_vision_has_one_entry(self) -> None:
        assert len(LLAMA_VISION_ENTRIES) == 1

    def test_vision_entries_does_not_restate_gemma(self) -> None:
        # gemma's entries live in entries/chat.py (MC8/MC12) — this
        # module holds only qwen_vl and llama_vision.
        assert not _catalog().models(ModelFamily("gemma"))


class TestDerivationRoundTrip:
    @pytest.mark.parametrize(
        "entry", VISION_ENTRIES, ids=[entry.name.value for entry in VISION_ENTRIES]
    )
    def test_entry_family_matches_family_of(self, entry: ModelDescriptor) -> None:
        assert entry.family == family_of(entry.name)


class TestOnlyVllmOrTensorrtBackend:
    # VISION_UNDERSTAND_DESCRIPTOR.backends is {vllm, tensorrt_llm} —
    # no llama_cpp, unlike chat.py's gemma entries which do advertise
    # llama_cpp under chat.generate.
    @pytest.mark.parametrize(
        "entry", VISION_ENTRIES, ids=[entry.name.value for entry in VISION_ENTRIES]
    )
    def test_entry_serving_rows_never_use_llama_cpp(self, entry: ModelDescriptor) -> None:
        assert all(row.backend != _LLAMA_CPP for row in entry.serving)

    @pytest.mark.parametrize(
        "entry", VISION_ENTRIES, ids=[entry.name.value for entry in VISION_ENTRIES]
    )
    def test_entry_serving_rows_are_vllm_or_tensorrt_llm(self, entry: ModelDescriptor) -> None:
        assert all(row.backend in (_VLLM, _TENSORRT_LLM) for row in entry.serving)


class TestStabilityAssertions:
    def test_qwen2_5_vl_7b_instruct_full_equality(self) -> None:
        # 8.29B params, 32_768-token native context (matches the text
        # Qwen2.5-7B-Instruct entry in chat.py). No llama_cpp row: the
        # vision descriptor does not advertise it.
        # fp16: ceil_gib(8_290_000_000 * 2 * 1.2) = ceil_gib(19_896_000_000) = 20
        # awq/gptq: ceil_gib(8_290_000_000 * 0.5 * 1.2) = ceil_gib(4_974_000_000) = 5
        expected = ModelDescriptor(
            name=PublishedModelName("Qwen/Qwen2.5-VL-7B-Instruct"),
            family=ModelFamily("qwen_vl"),
            parameter_count=8_290_000_000,
            context_window=32_768,
            serving=frozenset(
                {
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

        assert _find(QWEN_VL_ENTRIES, "Qwen/Qwen2.5-VL-7B-Instruct") == expected

    def test_qwen2_5_vl_72b_instruct_full_equality(self) -> None:
        # 73.4B params, 32_768-token native context.
        # fp16: ceil_gib(73_400_000_000 * 2 * 1.2) = ceil_gib(176_160_000_000) = 177
        # awq/gptq: ceil_gib(73_400_000_000 * 0.5 * 1.2) = ceil_gib(44_040_000_000) = 45
        expected = ModelDescriptor(
            name=PublishedModelName("Qwen/Qwen2.5-VL-72B-Instruct"),
            family=ModelFamily("qwen_vl"),
            parameter_count=73_400_000_000,
            context_window=32_768,
            serving=frozenset(
                {
                    BackendSupport(
                        backend=_VLLM, quantizations=frozenset({_FP16}), min_vram_bytes=177
                    ),
                    BackendSupport(
                        backend=_VLLM,
                        quantizations=frozenset({_AWQ, _GPTQ}),
                        min_vram_bytes=45,
                    ),
                    BackendSupport(
                        backend=_TENSORRT_LLM,
                        quantizations=frozenset({_FP16}),
                        min_vram_bytes=177,
                    ),
                }
            ),
        )

        assert _find(QWEN_VL_ENTRIES, "Qwen/Qwen2.5-VL-72B-Instruct") == expected

    def test_llama_3_2_11b_vision_instruct_full_equality(self) -> None:
        # 10.6B params, 131_072-token native context (matches the other
        # Llama 3.2 entries in chat.py). No llama_cpp row: the vision
        # descriptor does not advertise it.
        # fp16: ceil_gib(10_600_000_000 * 2 * 1.2) = ceil_gib(25_440_000_000) = 26
        # awq/gptq: ceil_gib(10_600_000_000 * 0.5 * 1.2) = ceil_gib(6_360_000_000) = 7
        expected = ModelDescriptor(
            name=PublishedModelName("meta-llama/Llama-3.2-11B-Vision-Instruct"),
            family=ModelFamily("llama_vision"),
            parameter_count=10_600_000_000,
            context_window=131_072,
            serving=frozenset(
                {
                    BackendSupport(
                        backend=_VLLM, quantizations=frozenset({_FP16}), min_vram_bytes=26
                    ),
                    BackendSupport(
                        backend=_VLLM,
                        quantizations=frozenset({_AWQ, _GPTQ}),
                        min_vram_bytes=7,
                    ),
                }
            ),
        )

        assert _find(LLAMA_VISION_ENTRIES, "meta-llama/Llama-3.2-11B-Vision-Instruct") == expected
