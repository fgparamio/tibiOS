"""Stub `CapabilityProvider` (`tibios_ray.capabilities.provider`).

Consolidates the ad-hoc `_StubProvider`/`_StableCatalogProvider` doubles
hand-rolled across Phase 4-5's test modules
(`tests/unit/runtime/test_registry.py`, `tests/unit/capabilities/test_provider.py`)
into one shared, configurable shape: a fixed `CapabilityDescriptor` plus an
optional `on_execute` hook for scenarios that need to observe channel
emission, cancellation, or exception propagation through a real
`WorkerRuntime` dispatch — without hand-writing a new dataclass per scenario.

Never a "Worker" (`capabilities/provider.py`'s binding terminology:
`StubProvider` implements `CapabilityProvider`, not the gRPC Worker
Contract).
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import timedelta

from tibios_ray.capabilities.descriptor import CapabilityDescriptor
from tibios_ray.execution.context import ExecutionContext
from tibios_ray.execution.report import ExecutionPhase, ExecutionReport

ExecuteFn = Callable[[ExecutionContext], Awaitable[ExecutionReport]]


def _default_report() -> ExecutionReport:
    return ExecutionReport(
        phase=ExecutionPhase.COMPLETED,
        duration=timedelta(),
        resource_usage={},
        metrics={},
        trace_id="stub-trace",
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class StubProvider:
    """A minimal conforming `CapabilityProvider` (Protocol, design decision
    D1). Registers/resolves/catalogs like a real Provider; `execute` returns
    `report` unless `on_execute` is supplied for scenario-specific behavior
    (emitting events, observing cancellation, raising)."""

    capability_descriptor: CapabilityDescriptor
    report: ExecutionReport = field(default_factory=_default_report)
    on_execute: ExecuteFn | None = None

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return self.capability_descriptor

    async def execute(self, context: ExecutionContext) -> ExecutionReport:
        if self.on_execute is not None:
            return await self.on_execute(context)
        return self.report
