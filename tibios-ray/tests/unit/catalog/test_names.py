"""Tests for `tibios_ray.catalog.names` — `PublishedModelName` and
`family_of`, the Family Label Convention (FLC) promoted from
`capabilities/`'s test-only regex to a real production function
(`design.md`, design decisions MC1-MC4).

The parametrized table below covers all fourteen archived FLC
derivations plus the six generalisation cases `design.md`'s "Verification
against all fourteen archived derivations" section worked through by
hand — every row here is copied from that table, not invented.
"""

import dataclasses
import re

import pytest

from tibios_ray.capabilities.descriptor import ModelFamily
from tibios_ray.catalog import names as names_module
from tibios_ray.catalog.errors import FamilyDerivationError
from tibios_ray.catalog.names import PublishedModelName, family_of

# Reused verbatim from `tests/unit/capabilities/test_provider_conformance.py`
# — production duplication of these regexes in `catalog/names.py` is a
# deliberate, accepted decision (design decision MC11): the two copies are
# kept in sync by this test failing the moment they diverge, not by a
# shared import.
_BANNED_TOKEN_PATTERN = re.compile(
    r"^(v?\d+(\.\d+)*|\d+[bmk]|q\d.*|fp\d+|bf\d+|awq|gptq|gguf|instruct|"
    r"chat|base|it|sft|dpo|small|medium|large|mini|xl)$"
)


class TestPublishedModelNameShape:
    def test_carries_a_single_value_field(self) -> None:
        fields = dataclasses.fields(PublishedModelName)
        assert [f.name for f in fields] == ["value"]

    def test_is_frozen(self) -> None:
        name = PublishedModelName("Qwen/Qwen3-8B")
        with pytest.raises(dataclasses.FrozenInstanceError):
            name.value = "other"  # type: ignore[misc]

    def test_equality_and_hash_are_by_value(self) -> None:
        assert PublishedModelName("Qwen/Qwen3-8B") == PublishedModelName("Qwen/Qwen3-8B")
        assert PublishedModelName("Qwen/Qwen3-8B") != PublishedModelName("Qwen/Qwen3-14B")
        assert hash(PublishedModelName("Qwen/Qwen3-8B")) == hash(
            PublishedModelName("Qwen/Qwen3-8B")
        )

    def test_is_positional_not_kw_only(self) -> None:
        # MC1: positional, like BackendId/ModelFamily/ObjectId — kw-only
        # is reserved for multi-field records.
        name = PublishedModelName("Qwen/Qwen3-8B")
        assert name.value == "Qwen/Qwen3-8B"


# Fourteen archived derivations, verbatim from design.md's table.
_ARCHIVED_DERIVATIONS: tuple[tuple[str, str], ...] = (
    ("Qwen/Qwen3-8B-Instruct", "qwen"),
    ("deepseek-ai/DeepSeek-V3", "deepseek"),
    ("Qwen/Qwen2.5-VL-7B-Instruct", "qwen_vl"),
    ("meta-llama/Llama-3.2-11B-Vision", "llama_vision"),
    ("google/gemma-3-12b-it", "gemma"),
    ("BAAI/bge-m3", "bge"),
    ("BAAI/bge-reranker-v2-m3", "bge_reranker"),
    ("nomic-ai/nomic-embed-text-v1.5", "nomic_embed"),
    ("jinaai/jina-embeddings-v3", "jina_embeddings"),
    ("jinaai/jina-reranker-v2-base-multilingual", "jina_reranker"),
    ("intfloat/multilingual-e5-large", "e5"),
    ("openai/whisper-large-v3", "whisper"),
    ("hexgrad/Kokoro-82M", "kokoro"),
    ("PaddlePaddle/PaddleOCR", "paddleocr"),
)

# Six generalisation cases design.md verified prove MC3/MC4 generalise
# beyond the archived set.
_GENERALISATION_DERIVATIONS: tuple[tuple[str, str], ...] = (
    ("Qwen/Qwen3-30B-A3B", "qwen"),
    ("moonshotai/Kimi-K2-Instruct", "kimi"),
    ("mistralai/Mistral-Small-3.2-24B-Instruct-2506", "mistral"),
    ("openai/whisper-large-v3-turbo", "whisper"),
    ("intfloat/e5-large-v2", "e5"),
    ("mistralai/Mixtral-8x7B-Instruct-v0.1", "mixtral"),
)

_ALL_DERIVATIONS = _ARCHIVED_DERIVATIONS + _GENERALISATION_DERIVATIONS


class TestFamilyOfDerivesTheArchivedLabels:
    @pytest.mark.parametrize(
        ("published", "expected_family"),
        _ALL_DERIVATIONS,
        ids=[published for published, _ in _ALL_DERIVATIONS],
    )
    def test_derives_expected_family(self, published: str, expected_family: str) -> None:
        result = family_of(PublishedModelName(published))

        assert result == ModelFamily(expected_family)

    @pytest.mark.parametrize(
        ("published", "_expected_family"),
        _ALL_DERIVATIONS,
        ids=[published for published, _ in _ALL_DERIVATIONS],
    )
    def test_derived_label_satisfies_flc_shape_and_has_no_banned_token(
        self, published: str, _expected_family: str
    ) -> None:
        # Property-style assertion (MC11): every produced label must
        # satisfy both the FLC shape regex and the banned-token check —
        # the same two predicates
        # `tests/unit/capabilities/test_provider_conformance.py` applies
        # to advertised labels.
        label = family_of(PublishedModelName(published)).value

        assert names_module._FLC_SHAPE.fullmatch(label), label
        for token in label.split("_"):
            assert not _BANNED_TOKEN_PATTERN.fullmatch(token), (
                f"family {label!r} contains banned token {token!r}"
            )


class TestFamilyOfIsPure:
    def test_two_calls_with_the_same_name_agree(self) -> None:
        name = PublishedModelName("Qwen/Qwen3-8B-Instruct")

        first = family_of(name)
        second = family_of(name)

        assert first == second


class TestFamilyOfRejectsNonDerivableNames:
    @pytest.mark.parametrize(
        "published",
        [
            "",
            "openai/",
            "large-v3",  # every token dropped: "large" table, "v3" version
            "7B",  # single size token, dropped
        ],
        ids=["empty", "org-prefix-only", "all-tokens-dropped", "bare-size-token"],
    )
    def test_raises_family_derivation_error(self, published: str) -> None:
        with pytest.raises(FamilyDerivationError) as exc_info:
            family_of(PublishedModelName(published))

        error = exc_info.value
        assert error.name == PublishedModelName(published)
        assert error.reason


class TestFamilyOfDocumentedNonDerivableExclusions:
    """`design.md`'s Open Questions: `meta-llama/Meta-Llama-3.1-8B-Instruct`
    and `deepseek-ai/DeepSeek-R1-Distill-Qwen-32B` **do** derive cleanly
    via `family_of` — they are deliberately excluded from the catalog's
    entry tables (slices 3-4) for reasons unrelated to derivability (a
    vendor-echoed org token; a cross-lineage distill with no single
    truthful family), not because `family_of` raises on them. Pinned here
    so a future contributor cannot "fix" this by adding either as a
    catalog entry believing `family_of` rejects them."""

    def test_meta_llama_vendor_echo_derives_cleanly(self) -> None:
        result = family_of(PublishedModelName("meta-llama/Meta-Llama-3.1-8B-Instruct"))

        assert result == ModelFamily("meta_llama")

    def test_deepseek_distill_cross_lineage_derives_cleanly(self) -> None:
        result = family_of(
            PublishedModelName("deepseek-ai/DeepSeek-R1-Distill-Qwen-32B")
        )

        assert result == ModelFamily("deepseek_qwen")
