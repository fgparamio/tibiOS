"""Tests for `tibios_ray.capabilities.vision` — the Vision Capability
Provider (`capability-providers` spec: "Descriptor Catalog Correctness
and Stability").

Only catalog data is asserted here — one full descriptor equality plus
flag values. Structural/behavioral conformance (identity stability,
element typing, FLC shape, `execute()` always raising, end-to-end
dispatch) is covered generically by `test_provider_conformance.py`
(design decision CP7) so this file stays small.

Families here follow design.md's Family Label Convention deviation from
`proposal.md`'s shorthand: `gemma_vision` -> `gemma` (rule 3 keeps only
*published* tokens, and Google publishes no "Gemma Vision" lineage —
Gemma 3 is natively multimodal). `gemma` therefore legitimately appears
under both `chat.generate` and `vision.understand` — one lineage serves
both capabilities.
"""

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import CapabilityDescriptor, CapabilityFlags, ModelFamily
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.capabilities.vision import VISION_UNDERSTAND_DESCRIPTOR, VisionProvider


class TestVisionProvider:
    def test_descriptor_matches_the_spec_table_exactly(self) -> None:
        provider = VisionProvider()

        assert provider.descriptor == CapabilityDescriptor(
            capability=CapabilityName("vision.understand"),
            families=frozenset(
                {
                    ModelFamily("qwen_vl"),
                    ModelFamily("llama_vision"),
                    ModelFamily("gemma"),
                }
            ),
            backends=frozenset({BackendId("vllm"), BackendId("tensorrt_llm")}),
            flags=CapabilityFlags(streaming=True, json=True),
        )

    def test_descriptor_is_the_module_level_constant(self) -> None:
        provider = VisionProvider()

        assert provider.descriptor is VISION_UNDERSTAND_DESCRIPTOR

    def test_flags_are_streaming_and_json_only(self) -> None:
        flags = VisionProvider().descriptor.flags

        assert flags == CapabilityFlags(streaming=True, json=True)
        assert flags.streaming is True
        assert flags.tools is False
        assert flags.json is True
        assert flags.reasoning is False
