"""Tests for `tibios_ray.runtime.registry` — the `CapabilityRegistry`
(`capability-registry` spec: "Capability Provider Interface", "Aggregated
Capability Advertisement"; `design.md` design decision D6: immutable,
ctor-built, no `register()` mutation method).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

import pytest

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import CapabilityDescriptor, CapabilityFlags, ModelFamily
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.execution.context import ExecutionContext
from tibios_ray.execution.report import ExecutionPhase, ExecutionReport
from tibios_ray.runtime.errors import (
    DuplicateCapabilityError,
    EmptyCatalogError,
    UnknownCapabilityError,
)
from tibios_ray.runtime.registry import CapabilityRegistry


@dataclass(frozen=True, slots=True, kw_only=True)
class _StubProvider:
    """A minimal conforming Capability Provider for registry tests only —
    never executed here, just registered/resolved/cataloged."""

    _descriptor: CapabilityDescriptor
    label: str = "stub"

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return self._descriptor

    async def execute(self, context: ExecutionContext) -> ExecutionReport:
        return ExecutionReport(
            phase=ExecutionPhase.COMPLETED,
            duration=timedelta(),
            resource_usage={},
            metrics={},
            trace_id="unused",
        )


def _provider(
    capability: str,
    *,
    families: frozenset[ModelFamily] | None = None,
    backends: frozenset[BackendId] | None = None,
) -> _StubProvider:
    return _StubProvider(
        _descriptor=CapabilityDescriptor(
            capability=CapabilityName(capability),
            families=families if families is not None else frozenset({ModelFamily("deepseek")}),
            backends=backends if backends is not None else frozenset({BackendId("llama_cpp")}),
            flags=CapabilityFlags(streaming=True),
        )
    )


def test_registers_and_resolves_conforming_providers() -> None:
    chat = _provider("chat.generate")
    embedding = _provider("embedding.generate")
    registry = CapabilityRegistry([chat, embedding])

    assert registry.resolve(CapabilityName("chat.generate")) is chat
    assert registry.resolve(CapabilityName("embedding.generate")) is embedding


def test_empty_provider_sequence_is_a_valid_registry() -> None:
    registry = CapabilityRegistry([])

    assert registry.catalog().descriptors == frozenset()


def test_resolve_unknown_capability_raises_unknown_capability_error() -> None:
    registry = CapabilityRegistry([_provider("chat.generate")])

    with pytest.raises(UnknownCapabilityError):
        registry.resolve(CapabilityName("vision.understand"))


def test_duplicate_capability_is_rejected_at_construction() -> None:
    first = _provider("chat.generate")
    second = _provider("chat.generate")

    with pytest.raises(DuplicateCapabilityError):
        CapabilityRegistry([first, second])


def test_provider_with_empty_families_and_backends_is_rejected_at_construction() -> None:
    empty_catalog_provider = _provider(
        "chat.generate", families=frozenset(), backends=frozenset()
    )

    with pytest.raises(EmptyCatalogError):
        CapabilityRegistry([empty_catalog_provider])


def test_provider_with_only_families_advertised_is_accepted() -> None:
    families_only = _provider(
        "chat.generate", families=frozenset({ModelFamily("qwen")}), backends=frozenset()
    )

    registry = CapabilityRegistry([families_only])

    assert registry.resolve(CapabilityName("chat.generate")) is families_only


def test_provider_with_only_backends_advertised_is_accepted() -> None:
    backends_only = _provider(
        "chat.generate", families=frozenset(), backends=frozenset({BackendId("vllm")})
    )

    registry = CapabilityRegistry([backends_only])

    assert registry.resolve(CapabilityName("chat.generate")) is backends_only


def test_catalog_returns_the_aggregated_union_of_all_descriptors() -> None:
    chat = _provider("chat.generate")
    embedding = _provider("embedding.generate", families=frozenset({ModelFamily("bge")}))
    registry = CapabilityRegistry([chat, embedding])

    catalog = registry.catalog()

    assert catalog.descriptors == frozenset({chat.descriptor, embedding.descriptor})


def test_catalog_hardcodes_no_provider_names_or_models() -> None:
    providers: Sequence[_StubProvider] = [
        _provider("chat.generate"),
        _provider("rerank.documents", families=frozenset({ModelFamily("bge-reranker")})),
    ]
    registry = CapabilityRegistry(providers)

    catalog = registry.catalog()

    assert {d.capability.value for d in catalog.descriptors} == {
        "chat.generate",
        "rerank.documents",
    }
