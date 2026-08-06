"""Tests for `tibios_ray.catalog.model` — `BackendSupport` and
`ModelDescriptor` (`design.md` Key Contracts, design decision MC5).

MC5: `BackendSupport` is keyed by (backend, footprint tier), not by
backend alone — a `ModelDescriptor` may carry several `BackendSupport`
rows for the same `BackendId`, one per tier. The construction tests below
prove two such rows on one `ModelDescriptor` do not crosstalk.
"""

import dataclasses

import pytest

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import ModelFamily
from tibios_ray.catalog.model import BackendSupport, ModelDescriptor
from tibios_ray.catalog.names import PublishedModelName
from tibios_ray.selection.policy import Quantization

_LLAMA_CPP = BackendId("llama_cpp")
_VLLM = BackendId("vllm")
_Q4_K_M = Quantization(scheme="q4_k_m", bits=4)
_Q8_0 = Quantization(scheme="q8_0", bits=8)


class TestBackendSupportShape:
    def test_carries_backend_quantizations_min_vram_gb(self) -> None:
        fields = {f.name for f in dataclasses.fields(BackendSupport)}
        assert fields == {"backend", "quantizations", "min_vram_gb"}

    def test_is_frozen(self) -> None:
        support = BackendSupport(
            backend=_VLLM, quantizations=frozenset({_Q4_K_M}), min_vram_gb=5
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            support.min_vram_gb = 10  # type: ignore[misc]

    def test_is_kw_only_not_positional(self) -> None:
        with pytest.raises(TypeError):
            BackendSupport(_VLLM, frozenset({_Q4_K_M}), 5)  # type: ignore[misc]

    def test_equality_and_hash_are_by_value(self) -> None:
        first = BackendSupport(backend=_VLLM, quantizations=frozenset({_Q4_K_M}), min_vram_gb=5)
        second = BackendSupport(
            backend=_VLLM, quantizations=frozenset({_Q4_K_M}), min_vram_gb=5
        )
        assert first == second
        assert hash(first) == hash(second)


class TestModelDescriptorShape:
    def test_carries_expected_fields(self) -> None:
        fields = {f.name for f in dataclasses.fields(ModelDescriptor)}
        assert fields == {"name", "family", "parameter_count", "context_window", "serving"}

    def test_is_frozen(self) -> None:
        descriptor = _two_tier_descriptor()
        with pytest.raises(dataclasses.FrozenInstanceError):
            descriptor.parameter_count = 1  # type: ignore[misc]

    def test_is_kw_only_not_positional(self) -> None:
        name = PublishedModelName("Qwen/Qwen3-8B")
        family = ModelFamily("qwen")
        with pytest.raises(TypeError):
            ModelDescriptor(name, family, 8_200_000_000, 32_768, frozenset())  # type: ignore[call-arg]


def _two_tier_descriptor() -> ModelDescriptor:
    return ModelDescriptor(
        name=PublishedModelName("Qwen/Qwen3-8B"),
        family=ModelFamily("qwen"),
        parameter_count=8_200_000_000,
        context_window=32_768,
        serving=frozenset(
            {
                BackendSupport(
                    backend=_LLAMA_CPP, quantizations=frozenset({_Q4_K_M}), min_vram_gb=5
                ),
                BackendSupport(
                    backend=_LLAMA_CPP, quantizations=frozenset({_Q8_0}), min_vram_gb=10
                ),
            }
        ),
    )


class TestMC5FootprintVariesIndependentlyPerBackendTier:
    def test_two_tiers_on_one_backend_do_not_crosstalk(self) -> None:
        descriptor = _two_tier_descriptor()
        assert len(descriptor.serving) == 2

        by_min_vram = {row.min_vram_gb: row for row in descriptor.serving}
        assert by_min_vram[5].backend == _LLAMA_CPP
        assert by_min_vram[5].quantizations == frozenset({_Q4_K_M})
        assert by_min_vram[10].backend == _LLAMA_CPP
        assert by_min_vram[10].quantizations == frozenset({_Q8_0})
