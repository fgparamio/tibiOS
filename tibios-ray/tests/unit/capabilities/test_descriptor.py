"""Tests for `tibios_ray.capabilities.descriptor` — `ModelFamily`,
`CapabilityFlags`, `CapabilityDescriptor`, `CapabilityCatalog`
(`capability-registry` spec: a Capability Provider advertises a catalog
of model families + backends + capability flags, never a hardcoded model
list).
"""

import dataclasses

import pytest

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import (
    CapabilityCatalog,
    CapabilityDescriptor,
    CapabilityFlags,
    ModelFamily,
)
from tibios_ray.capabilities.names import CapabilityName


class TestModelFamily:
    def test_holds_its_value(self) -> None:
        assert ModelFamily("deepseek").value == "deepseek"

    def test_is_frozen(self) -> None:
        family = ModelFamily("deepseek")
        with pytest.raises(dataclasses.FrozenInstanceError):
            family.value = "qwen"  # type: ignore[misc]

    def test_equality_is_by_value(self) -> None:
        assert ModelFamily("deepseek") == ModelFamily("deepseek")
        assert ModelFamily("deepseek") != ModelFamily("qwen")


class TestCapabilityFlags:
    def test_defaults_are_all_false(self) -> None:
        flags = CapabilityFlags()
        assert flags.streaming is False
        assert flags.tools is False
        assert flags.json is False
        assert flags.reasoning is False

    def test_holds_explicit_values(self) -> None:
        flags = CapabilityFlags(streaming=True, tools=True, json=False, reasoning=True)
        assert flags.streaming is True
        assert flags.tools is True
        assert flags.json is False
        assert flags.reasoning is True

    def test_is_frozen(self) -> None:
        flags = CapabilityFlags(streaming=True)
        with pytest.raises(dataclasses.FrozenInstanceError):
            flags.streaming = False  # type: ignore[misc]


class TestCapabilityDescriptor:
    def _descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            capability=CapabilityName("chat.generate"),
            families=frozenset({ModelFamily("deepseek"), ModelFamily("qwen")}),
            backends=frozenset({BackendId("llama_cpp"), BackendId("vllm")}),
            flags=CapabilityFlags(streaming=True, reasoning=True),
        )

    def test_holds_capability_families_backends_and_flags(self) -> None:
        descriptor = self._descriptor()
        assert descriptor.capability == CapabilityName("chat.generate")
        assert descriptor.families == frozenset({ModelFamily("deepseek"), ModelFamily("qwen")})
        assert descriptor.backends == frozenset({BackendId("llama_cpp"), BackendId("vllm")})
        assert descriptor.flags == CapabilityFlags(streaming=True, reasoning=True)

    def test_is_frozen(self) -> None:
        descriptor = self._descriptor()
        with pytest.raises(dataclasses.FrozenInstanceError):
            descriptor.capability = CapabilityName("embedding.generate")  # type: ignore[misc]

    def test_is_hashable_for_aggregation_in_a_catalog(self) -> None:
        # CapabilityCatalog aggregates descriptors as a frozenset — every
        # field must itself be hashable for that to be possible.
        assert hash(self._descriptor()) == hash(self._descriptor())


class TestCapabilityCatalog:
    def test_holds_the_union_of_registered_descriptors(self) -> None:
        chat = CapabilityDescriptor(
            capability=CapabilityName("chat.generate"),
            families=frozenset({ModelFamily("deepseek")}),
            backends=frozenset({BackendId("llama_cpp")}),
            flags=CapabilityFlags(streaming=True),
        )
        embedding = CapabilityDescriptor(
            capability=CapabilityName("embedding.generate"),
            families=frozenset({ModelFamily("bge")}),
            backends=frozenset({BackendId("onnxruntime")}),
            flags=CapabilityFlags(),
        )

        catalog = CapabilityCatalog(descriptors=frozenset({chat, embedding}))

        assert catalog.descriptors == frozenset({chat, embedding})
        assert {d.capability for d in catalog.descriptors} == {
            CapabilityName("chat.generate"),
            CapabilityName("embedding.generate"),
        }

    def test_is_frozen(self) -> None:
        catalog = CapabilityCatalog(descriptors=frozenset())
        with pytest.raises(dataclasses.FrozenInstanceError):
            catalog.descriptors = frozenset()  # type: ignore[misc]
