"""Tests for `tibios_ray.catalog.entries.embedding` — the Embedding
capability group's reference data (`design.md` line 400, "Remaining
groups").

Slice 5 (this file): `bge`, `nomic_embed`, `e5`, `jina_embeddings`.
Unlike the Chat family group (slices 3-4), `design.md` has no worked
Reference data table for these families — only the family/model-name
list. Footprint figures are therefore derived here from MC13's formula
(`ceil_gib(parameter_count x bits/8 x 1.2)`), not copied verbatim.

Per family: family coverage (at least one entry reachable through
`ModelCatalog.models`), one full `ModelDescriptor` equality as a
stability assertion against a hand-built expected value, and the
derivation round-trip `entry.family == family_of(entry.name)` for every
entry in this slice (MC14 — `entries/__init__.py` assembly is deferred
to slice 8, so this module builds its own local
`ModelCatalog(EMBEDDING_ENTRIES)` fixture rather than importing
`DEFAULT_CATALOG`).

Every `BackendSupport` row here uses `onnxruntime` — the only backend
`capabilities/embedding.py`'s `EMBEDDING_GENERATE_DESCRIPTOR` advertises
for these families (`capability-providers` spec, "Embedding/Rerank
advertise none").
"""

import pytest

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import ModelFamily
from tibios_ray.catalog.catalog import ModelCatalog
from tibios_ray.catalog.entries.embedding import (
    BGE_ENTRIES,
    E5_ENTRIES,
    EMBEDDING_ENTRIES,
    JINA_EMBEDDINGS_ENTRIES,
    NOMIC_EMBED_ENTRIES,
)
from tibios_ray.catalog.model import BackendSupport, ModelDescriptor
from tibios_ray.catalog.names import PublishedModelName, family_of
from tibios_ray.selection.policy import Quantization

_ONNXRUNTIME = BackendId("onnxruntime")

_INT8 = Quantization(scheme="int8", bits=8)
_FP32 = Quantization(scheme="fp32", bits=32)


def _catalog() -> ModelCatalog:
    return ModelCatalog(EMBEDDING_ENTRIES)


def _find(entries: tuple[ModelDescriptor, ...], name: str) -> ModelDescriptor:
    for entry in entries:
        if entry.name.value == name:
            return entry
    raise AssertionError(f"no entry named {name!r} in {[e.name.value for e in entries]}")


class TestFamilyCoverage:
    def test_bge_has_at_least_one_entry(self) -> None:
        assert _catalog().models(ModelFamily("bge"))

    def test_nomic_embed_has_at_least_one_entry(self) -> None:
        assert _catalog().models(ModelFamily("nomic_embed"))

    def test_e5_has_at_least_one_entry(self) -> None:
        assert _catalog().models(ModelFamily("e5"))

    def test_jina_embeddings_has_at_least_one_entry(self) -> None:
        assert _catalog().models(ModelFamily("jina_embeddings"))

    def test_bge_has_two_entries(self) -> None:
        # BAAI/bge-m3, BAAI/bge-large-en-v1.5
        assert len(BGE_ENTRIES) == 2

    def test_nomic_embed_has_one_entry(self) -> None:
        assert len(NOMIC_EMBED_ENTRIES) == 1

    def test_e5_has_two_entries(self) -> None:
        # intfloat/multilingual-e5-large, intfloat/e5-large-v2
        assert len(E5_ENTRIES) == 2

    def test_jina_embeddings_has_one_entry(self) -> None:
        assert len(JINA_EMBEDDINGS_ENTRIES) == 1


class TestDerivationRoundTrip:
    @pytest.mark.parametrize(
        "entry", EMBEDDING_ENTRIES, ids=[entry.name.value for entry in EMBEDDING_ENTRIES]
    )
    def test_entry_family_matches_family_of(self, entry: ModelDescriptor) -> None:
        assert entry.family == family_of(entry.name)


class TestOnlyOnnxruntimeBackend:
    # capabilities/embedding.py advertises only onnxruntime for every
    # family in this module — entries must not claim any other backend.
    @pytest.mark.parametrize(
        "entry", EMBEDDING_ENTRIES, ids=[entry.name.value for entry in EMBEDDING_ENTRIES]
    )
    def test_entry_serving_rows_are_onnxruntime_only(self, entry: ModelDescriptor) -> None:
        assert all(row.backend == _ONNXRUNTIME for row in entry.serving)


class TestStabilityAssertions:
    def test_bge_m3_full_equality(self) -> None:
        # 568M params, XLM-RoBERTa-large backbone, 8192-token context.
        # int8: ceil_gib(568_000_000 * 1 * 1.2) = ceil_gib(681_600_000) = 1
        # fp32: ceil_gib(568_000_000 * 4 * 1.2) = ceil_gib(2_726_400_000) = 3
        expected = ModelDescriptor(
            name=PublishedModelName("BAAI/bge-m3"),
            family=ModelFamily("bge"),
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
        )

        assert _find(BGE_ENTRIES, "BAAI/bge-m3") == expected

    def test_nomic_embed_text_v1_5_full_equality(self) -> None:
        # 137M params, Nomic BERT backbone, 8192-token context. int8 and
        # fp32 both round to 1 GiB at this parameter count, so they
        # share one BackendSupport row (design decision MC5's pattern:
        # `quantizations` on a row holds every scheme sharing one
        # `min_vram_bytes`).
        expected = ModelDescriptor(
            name=PublishedModelName("nomic-ai/nomic-embed-text-v1.5"),
            family=ModelFamily("nomic_embed"),
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
        )

        assert _find(NOMIC_EMBED_ENTRIES, "nomic-ai/nomic-embed-text-v1.5") == expected

    def test_multilingual_e5_large_full_equality(self) -> None:
        # 560M params, XLM-RoBERTa-large backbone, 512-token context.
        expected = ModelDescriptor(
            name=PublishedModelName("intfloat/multilingual-e5-large"),
            family=ModelFamily("e5"),
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
        )

        assert _find(E5_ENTRIES, "intfloat/multilingual-e5-large") == expected

    def test_jina_embeddings_v3_full_equality(self) -> None:
        # 572M params, XLM-RoBERTa backbone, 8192-token context.
        expected = ModelDescriptor(
            name=PublishedModelName("jinaai/jina-embeddings-v3"),
            family=ModelFamily("jina_embeddings"),
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
        )

        assert _find(JINA_EMBEDDINGS_ENTRIES, "jinaai/jina-embeddings-v3") == expected
