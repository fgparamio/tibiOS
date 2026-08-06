"""Tests for `tibios_ray.testing.provider` — `StubProvider`, the shared
`CapabilityProvider` fake consolidating the ad-hoc `_StubProvider`/
`_StableCatalogProvider` doubles hand-rolled across Phase 4-5's test
modules (Phase 6, `testing/`).
"""

import asyncio
from datetime import timedelta

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import CapabilityDescriptor, CapabilityFlags, ModelFamily
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.capabilities.provider import CapabilityProvider
from tibios_ray.execution.report import ExecutionPhase, ExecutionReport
from tibios_ray.testing.context import FakeExecutionContext
from tibios_ray.testing.provider import StubProvider


def _descriptor(capability: str) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        capability=CapabilityName(capability),
        families=frozenset({ModelFamily("deepseek")}),
        backends=frozenset({BackendId("llama_cpp")}),
        flags=CapabilityFlags(streaming=True),
    )


def test_satisfies_the_capability_provider_protocol() -> None:
    provider: CapabilityProvider = StubProvider(capability_descriptor=_descriptor("chat.generate"))
    assert provider.descriptor.capability == CapabilityName("chat.generate")


def test_descriptor_property_returns_the_configured_descriptor() -> None:
    descriptor = _descriptor("chat.generate")
    provider = StubProvider(capability_descriptor=descriptor)
    assert provider.descriptor is descriptor


def test_execute_returns_a_default_completed_report_when_no_hook_given() -> None:
    provider = StubProvider(capability_descriptor=_descriptor("chat.generate"))

    report = asyncio.run(provider.execute(FakeExecutionContext()))

    assert isinstance(report, ExecutionReport)
    assert report.phase == ExecutionPhase.COMPLETED


def test_execute_returns_the_configured_report_when_no_hook_given() -> None:
    report = ExecutionReport(
        phase=ExecutionPhase.FAILED,
        duration=timedelta(),
        resource_usage={},
        metrics={},
        trace_id="configured",
        failure="boom",
    )
    provider = StubProvider(capability_descriptor=_descriptor("chat.generate"), report=report)

    result = asyncio.run(provider.execute(FakeExecutionContext()))

    assert result is report


def test_execute_delegates_to_on_execute_hook_when_given() -> None:
    async def hook(context: object) -> ExecutionReport:
        return ExecutionReport(
            phase=ExecutionPhase.COMPLETED,
            duration=timedelta(),
            resource_usage={},
            metrics={},
            trace_id="from-hook",
        )

    provider = StubProvider(capability_descriptor=_descriptor("chat.generate"), on_execute=hook)

    report = asyncio.run(provider.execute(FakeExecutionContext()))

    assert report.trace_id == "from-hook"
