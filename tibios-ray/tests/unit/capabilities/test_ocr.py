"""Tests for `tibios_ray.capabilities.ocr` — the OCR Capability Provider
(`capability-providers` spec: "Descriptor Catalog Correctness and
Stability").

Only catalog data is asserted here — one full descriptor equality plus
flag values. Structural/behavioral conformance (identity stability,
element typing, FLC shape, `execute()` always raising, end-to-end
dispatch) is covered generically by `test_provider_conformance.py`
(design decision CP7) so this file stays small.

Family here follows design.md's Family Label Convention: `PaddlePaddle/
PaddleOCR` -> `paddleocr` (rule 3 keeps the published `ocr` role token,
joined with the lineage token, no org prefix).
"""

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import CapabilityDescriptor, CapabilityFlags, ModelFamily
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.capabilities.ocr import OCR_EXTRACT_DESCRIPTOR, OcrProvider


class TestOcrProvider:
    def test_descriptor_matches_the_spec_table_exactly(self) -> None:
        provider = OcrProvider()

        assert provider.descriptor == CapabilityDescriptor(
            capability=CapabilityName("ocr.extract"),
            families=frozenset({ModelFamily("paddleocr")}),
            backends=frozenset({BackendId("onnxruntime")}),
            flags=CapabilityFlags(json=True),
        )

    def test_descriptor_is_the_module_level_constant(self) -> None:
        provider = OcrProvider()

        assert provider.descriptor is OCR_EXTRACT_DESCRIPTOR

    def test_flags_are_json_only(self) -> None:
        flags = OcrProvider().descriptor.flags

        assert flags == CapabilityFlags(json=True)
        assert flags.streaming is False
        assert flags.tools is False
        assert flags.json is True
        assert flags.reasoning is False
