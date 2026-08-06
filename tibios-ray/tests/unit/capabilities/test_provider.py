"""Tests for `tibios_ray.capabilities.provider` — the `CapabilityProvider`
Protocol (`capability-registry` spec: Capability Provider Interface).

Terminology (binding, `proposal.md`): a Capability Provider is never a
"Worker" — it implements a capability (e.g. `chat.generate`), not the
gRPC Worker Contract. This module defines no "Worker" identifier.
"""

import asyncio
from datetime import timedelta
from typing import assert_type

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import CapabilityDescriptor, CapabilityFlags, ModelFamily
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.capabilities.provider import CapabilityProvider
from tibios_ray.execution.report import ExecutionPhase, ExecutionReport
from tibios_ray.testing import FakeExecutionContext, StubProvider


def _stable_catalog_provider() -> StubProvider:
    """A minimal conforming Capability Provider — proves the descriptor
    property and `execute` shape are stable, not that real inference
    happens (Phase 2 builds the concrete Chat/Embedding/etc. Providers,
    not this phase)."""
    return StubProvider(
        capability_descriptor=CapabilityDescriptor(
            capability=CapabilityName("chat.generate"),
            families=frozenset({ModelFamily("deepseek")}),
            backends=frozenset({BackendId("llama_cpp")}),
            flags=CapabilityFlags(streaming=True),
        ),
        report=ExecutionReport(
            phase=ExecutionPhase.COMPLETED,
            duration=timedelta(seconds=1),
            resource_usage={},
            metrics={},
            trace_id="trace-1",
        ),
    )


def _accepts_capability_provider(provider: CapabilityProvider) -> None:
    assert_type(provider, CapabilityProvider)


def test_fake_provider_satisfies_the_capability_provider_protocol() -> None:
    provider = _stable_catalog_provider()
    _accepts_capability_provider(provider)


def test_descriptor_property_shape_is_stable_across_reads() -> None:
    provider = _stable_catalog_provider()
    first = provider.descriptor
    second = provider.descriptor
    assert first == second
    assert first.capability == CapabilityName("chat.generate")
    assert first.flags.streaming is True


def test_execute_returns_an_execution_report() -> None:
    provider = _stable_catalog_provider()

    async def scenario() -> ExecutionReport:
        return await provider.execute(FakeExecutionContext())

    report = asyncio.run(scenario())

    assert isinstance(report, ExecutionReport)
    assert report.phase == ExecutionPhase.COMPLETED
    assert report.trace_id == "trace-1"
