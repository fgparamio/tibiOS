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
from tibios_ray.execution.context import AllocationContract, ExecutionContext
from tibios_ray.execution.events import ExecutionEvent
from tibios_ray.execution.report import ExecutionPhase, ExecutionReport


class _NullChannel:
    async def emit(self, event: ExecutionEvent) -> None:
        return None


class _NeverCancelled:
    @property
    def is_cancelled(self) -> bool:
        return False

    async def wait(self) -> None:
        return None


def _execution_context() -> ExecutionContext:
    return ExecutionContext(
        capability="chat.generate",
        allocation_contract=AllocationContract(
            exclusive=True,
            renewable_lease=False,
            preemptible=False,
            migration_allowed=False,
            checkpoint_required=False,
            max_execution_duration=timedelta(minutes=5),
        ),
        dependencies={},
        channel=_NullChannel(),
        cancellation=_NeverCancelled(),
    )


class _StableCatalogProvider:
    """A minimal conforming Capability Provider — proves the descriptor
    property and `execute` shape are stable, not that real inference
    happens (Phase 2 builds the concrete Chat/Embedding/etc. Providers,
    not this phase)."""

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            capability=CapabilityName("chat.generate"),
            families=frozenset({ModelFamily("deepseek")}),
            backends=frozenset({BackendId("llama_cpp")}),
            flags=CapabilityFlags(streaming=True),
        )

    async def execute(self, context: ExecutionContext) -> ExecutionReport:
        return ExecutionReport(
            phase=ExecutionPhase.COMPLETED,
            duration=timedelta(seconds=1),
            resource_usage={},
            metrics={},
            trace_id="trace-1",
        )


def _accepts_capability_provider(provider: CapabilityProvider) -> None:
    assert_type(provider, CapabilityProvider)


def test_fake_provider_satisfies_the_capability_provider_protocol() -> None:
    provider = _StableCatalogProvider()
    _accepts_capability_provider(provider)


def test_descriptor_property_shape_is_stable_across_reads() -> None:
    provider = _StableCatalogProvider()
    first = provider.descriptor
    second = provider.descriptor
    assert first == second
    assert first.capability == CapabilityName("chat.generate")
    assert first.flags.streaming is True


def test_execute_returns_an_execution_report() -> None:
    provider = _StableCatalogProvider()

    async def scenario() -> ExecutionReport:
        return await provider.execute(_execution_context())

    report = asyncio.run(scenario())

    assert isinstance(report, ExecutionReport)
    assert report.phase == ExecutionPhase.COMPLETED
    assert report.trace_id == "trace-1"
