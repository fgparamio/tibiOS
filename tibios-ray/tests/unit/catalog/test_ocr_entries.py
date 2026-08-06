"""Tests for `tibios_ray.catalog.entries.ocr` — the OCR capability
group's reference data (`design.md` line 400, "Remaining groups").

One family only: `paddleocr` (`ocr.extract`) ← `PaddlePaddle/PaddleOCR`.

Unlike the Chat family group (slices 3-4), `design.md`'s worked
Reference data table does **not** cover `paddleocr` — only the
family/model-name list (line 400, "Remaining groups"). `min_vram_bytes`
is therefore *derived*, not copied, from MC13's formula
(`ceil_gib(parameter_count x bits/8 x 1.2)`), the same decimal-GB
(`bytes / 1e9`, ceiling) interpretation established in slice 5.

`parameter_count` here is the combined detection + classification +
recognition pipeline PaddleOCR ships as one system — publicly documented
at roughly 15M parameters total, an order of magnitude below every
transformer-based family in this catalog, consistent with PaddleOCR's
mobile-first design goals. `context_window` has no token-context
analogue for a detect-then-recognize pipeline; the closest natively
published figure is the recognition head's `max_text_length` config
value (25 characters per detected text line), which is what is stated
here.

Per family: family coverage (at least one entry reachable through
`ModelCatalog.models`), one full `ModelDescriptor` equality as a
stability assertion against a hand-built expected value, and the
derivation round-trip `entry.family == family_of(entry.name)` for every
entry in this slice (MC14 — `entries/__init__.py` assembly is deferred
to slice 8, so this module builds its own local
`ModelCatalog(OCR_ENTRIES)` fixture rather than importing
`DEFAULT_CATALOG`).

Every `BackendSupport` row here uses `onnxruntime` — the only backend
`capabilities/ocr.py`'s `OCR_EXTRACT_DESCRIPTOR` advertises for
`paddleocr`.
"""

import pytest

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import ModelFamily
from tibios_ray.catalog.catalog import ModelCatalog
from tibios_ray.catalog.entries.ocr import OCR_ENTRIES, PADDLEOCR_ENTRIES
from tibios_ray.catalog.model import BackendSupport, ModelDescriptor
from tibios_ray.catalog.names import PublishedModelName, family_of
from tibios_ray.selection.policy import Quantization

_ONNXRUNTIME = BackendId("onnxruntime")

_INT8 = Quantization(scheme="int8", bits=8)
_FP32 = Quantization(scheme="fp32", bits=32)


def _catalog() -> ModelCatalog:
    return ModelCatalog(OCR_ENTRIES)


def _find(entries: tuple[ModelDescriptor, ...], name: str) -> ModelDescriptor:
    for entry in entries:
        if entry.name.value == name:
            return entry
    raise AssertionError(f"no entry named {name!r} in {[e.name.value for e in entries]}")


class TestFamilyCoverage:
    def test_paddleocr_has_at_least_one_entry(self) -> None:
        assert _catalog().models(ModelFamily("paddleocr"))

    def test_paddleocr_has_one_entry(self) -> None:
        assert len(PADDLEOCR_ENTRIES) == 1

    def test_ocr_entries_equals_paddleocr_entries(self) -> None:
        # Single-family module — OCR_ENTRIES is not a union of several
        # groups the way SPEECH_ENTRIES/CHAT_ENTRIES are.
        assert OCR_ENTRIES == PADDLEOCR_ENTRIES


class TestDerivationRoundTrip:
    @pytest.mark.parametrize(
        "entry", OCR_ENTRIES, ids=[entry.name.value for entry in OCR_ENTRIES]
    )
    def test_entry_family_matches_family_of(self, entry: ModelDescriptor) -> None:
        assert entry.family == family_of(entry.name)


class TestOnlyOnnxruntimeBackend:
    @pytest.mark.parametrize(
        "entry", OCR_ENTRIES, ids=[entry.name.value for entry in OCR_ENTRIES]
    )
    def test_entry_serving_rows_are_onnxruntime_only(self, entry: ModelDescriptor) -> None:
        assert all(row.backend == _ONNXRUNTIME for row in entry.serving)


class TestStabilityAssertions:
    def test_paddleocr_full_equality(self) -> None:
        # ~15M params (det + cls + rec pipeline combined), 25-character
        # max_text_length (the recognition head's published config
        # value — the closest natively published analogue to a
        # token-context window for this pipeline shape). int8 and fp32
        # both round to 1 GiB at this parameter count, so they share
        # one BackendSupport row (MC5's pattern).
        # int8: ceil_gib(15_000_000 * 1 * 1.2) = ceil_gib(18_000_000) = 1
        # fp32: ceil_gib(15_000_000 * 4 * 1.2) = ceil_gib(72_000_000) = 1
        expected = ModelDescriptor(
            name=PublishedModelName("PaddlePaddle/PaddleOCR"),
            family=ModelFamily("paddleocr"),
            parameter_count=15_000_000,
            context_window=25,
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

        assert _find(PADDLEOCR_ENTRIES, "PaddlePaddle/PaddleOCR") == expected
