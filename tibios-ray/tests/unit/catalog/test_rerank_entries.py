"""Tests for `tibios_ray.catalog.entries.rerank` — the Rerank capability
group's reference data (`design.md` line 400, "Remaining groups").

Slice 5 (this file): `bge_reranker`, `jina_reranker`. Same pattern as
`test_embedding_entries.py`: no worked Reference data table exists for
these families, so footprint figures are derived here from MC13's
formula (`ceil_gib(parameter_count x bits/8 x 1.2)`), not copied
verbatim.

Per family: family coverage, one full `ModelDescriptor` equality as a
stability assertion, and the derivation round-trip
`entry.family == family_of(entry.name)` for every entry in this slice
(MC14 — local `ModelCatalog(RERANK_ENTRIES)` fixture, `DEFAULT_CATALOG`
assembly deferred to slice 8).

Every `BackendSupport` row here uses `onnxruntime` — the only backend
`capabilities/rerank.py`'s `RERANK_DOCUMENTS_DESCRIPTOR` advertises for
these families (`capability-providers` spec, "Embedding/Rerank advertise
none").
"""

import pytest

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import ModelFamily
from tibios_ray.catalog.catalog import ModelCatalog
from tibios_ray.catalog.entries.rerank import (
    BGE_RERANKER_ENTRIES,
    JINA_RERANKER_ENTRIES,
    RERANK_ENTRIES,
)
from tibios_ray.catalog.model import BackendSupport, ModelDescriptor
from tibios_ray.catalog.names import PublishedModelName, family_of
from tibios_ray.selection.policy import Quantization

_ONNXRUNTIME = BackendId("onnxruntime")

_INT8 = Quantization(scheme="int8", bits=8)
_FP32 = Quantization(scheme="fp32", bits=32)


def _catalog() -> ModelCatalog:
    return ModelCatalog(RERANK_ENTRIES)


def _find(entries: tuple[ModelDescriptor, ...], name: str) -> ModelDescriptor:
    for entry in entries:
        if entry.name.value == name:
            return entry
    raise AssertionError(f"no entry named {name!r} in {[e.name.value for e in entries]}")


class TestFamilyCoverage:
    def test_bge_reranker_has_at_least_one_entry(self) -> None:
        assert _catalog().models(ModelFamily("bge_reranker"))

    def test_jina_reranker_has_at_least_one_entry(self) -> None:
        assert _catalog().models(ModelFamily("jina_reranker"))

    def test_bge_reranker_has_one_entry(self) -> None:
        assert len(BGE_RERANKER_ENTRIES) == 1

    def test_jina_reranker_has_one_entry(self) -> None:
        assert len(JINA_RERANKER_ENTRIES) == 1


class TestDerivationRoundTrip:
    @pytest.mark.parametrize(
        "entry", RERANK_ENTRIES, ids=[entry.name.value for entry in RERANK_ENTRIES]
    )
    def test_entry_family_matches_family_of(self, entry: ModelDescriptor) -> None:
        assert entry.family == family_of(entry.name)


class TestOnlyOnnxruntimeBackend:
    # capabilities/rerank.py advertises only onnxruntime for every
    # family in this module — entries must not claim any other backend.
    @pytest.mark.parametrize(
        "entry", RERANK_ENTRIES, ids=[entry.name.value for entry in RERANK_ENTRIES]
    )
    def test_entry_serving_rows_are_onnxruntime_only(self, entry: ModelDescriptor) -> None:
        assert all(row.backend == _ONNXRUNTIME for row in entry.serving)


class TestStabilityAssertions:
    def test_bge_reranker_v2_m3_full_equality(self) -> None:
        # 568M params, same XLM-RoBERTa-large backbone as bge-m3
        # (cross-encoder head), 8192-token context.
        # int8: ceil_gib(568_000_000 * 1 * 1.2) = ceil_gib(681_600_000) = 1
        # fp32: ceil_gib(568_000_000 * 4 * 1.2) = ceil_gib(2_726_400_000) = 3
        expected = ModelDescriptor(
            name=PublishedModelName("BAAI/bge-reranker-v2-m3"),
            family=ModelFamily("bge_reranker"),
            parameter_count=568_000_000,
            context_window=8192,
            serving=frozenset(
                {
                    BackendSupport(
                        backend=_ONNXRUNTIME, quantizations=frozenset({_INT8}), min_vram_gb=1
                    ),
                    BackendSupport(
                        backend=_ONNXRUNTIME, quantizations=frozenset({_FP32}), min_vram_gb=3
                    ),
                }
            ),
        )

        assert _find(BGE_RERANKER_ENTRIES, "BAAI/bge-reranker-v2-m3") == expected

    def test_jina_reranker_v2_base_multilingual_full_equality(self) -> None:
        # 278M params, 1024-token context.
        # int8: ceil_gib(278_000_000 * 1 * 1.2) = ceil_gib(333_600_000) = 1
        # fp32: ceil_gib(278_000_000 * 4 * 1.2) = ceil_gib(1_334_400_000) = 2
        expected = ModelDescriptor(
            name=PublishedModelName("jinaai/jina-reranker-v2-base-multilingual"),
            family=ModelFamily("jina_reranker"),
            parameter_count=278_000_000,
            context_window=1024,
            serving=frozenset(
                {
                    BackendSupport(
                        backend=_ONNXRUNTIME, quantizations=frozenset({_INT8}), min_vram_gb=1
                    ),
                    BackendSupport(
                        backend=_ONNXRUNTIME, quantizations=frozenset({_FP32}), min_vram_gb=2
                    ),
                }
            ),
        )

        assert _find(
            JINA_RERANKER_ENTRIES, "jinaai/jina-reranker-v2-base-multilingual"
        ) == expected
