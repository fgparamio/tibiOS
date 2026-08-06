"""Tests for `tibios_ray.capabilities.chat` — the Chat Capability Provider
(`capability-providers` spec: "Descriptor Catalog Correctness and
Stability", "Chat advertises realistic flags").

Only catalog data is asserted here — one full descriptor equality plus
flag values. Structural/behavioral conformance (identity stability,
element typing, FLC shape, `execute()` always raising, end-to-end
dispatch) is covered generically by `test_provider_conformance.py`
(design decision CP7) so this file stays small.
"""

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.chat import CHAT_GENERATE_DESCRIPTOR, ChatProvider
from tibios_ray.capabilities.descriptor import CapabilityDescriptor, CapabilityFlags, ModelFamily
from tibios_ray.capabilities.names import CapabilityName


class TestChatProvider:
    def test_descriptor_matches_the_spec_table_exactly(self) -> None:
        provider = ChatProvider()

        assert provider.descriptor == CapabilityDescriptor(
            capability=CapabilityName("chat.generate"),
            families=frozenset(
                {
                    ModelFamily("qwen"),
                    ModelFamily("llama"),
                    ModelFamily("deepseek"),
                    ModelFamily("gemma"),
                    ModelFamily("mistral"),
                    ModelFamily("kimi"),
                }
            ),
            backends=frozenset(
                {
                    BackendId("llama_cpp"),
                    BackendId("tensorrt_llm"),
                    BackendId("vllm"),
                }
            ),
            flags=CapabilityFlags(streaming=True, tools=True, json=True, reasoning=True),
        )

    def test_descriptor_is_the_module_level_constant(self) -> None:
        provider = ChatProvider()

        assert provider.descriptor is CHAT_GENERATE_DESCRIPTOR

    def test_flags_are_all_true(self) -> None:
        flags = ChatProvider().descriptor.flags

        assert flags.streaming is True
        assert flags.tools is True
        assert flags.json is True
        assert flags.reasoning is True
