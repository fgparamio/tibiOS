"""`WorkerRuntime` — drives the Worker Contract lifecycle for every
execution and dispatches exclusively through the `CapabilityRegistry`
(`worker-runtime` spec: "Worker Runtime Owns the Execution Lifecycle",
"Dispatch Only via Capability Registry").

This is the **sole sanctioned exception** to the binding rule that
"Worker" may never name an internal identifier inside tibios-ray
(`worker-runtime` spec: "'Worker' Naming Is Reserved to the Contract
Entity") — `WorkerRuntime` directly drives the Worker Contract lifecycle
(Received -> Prepared -> Running -> Completed/Failed, emitting Execution
Events throughout, producing one Execution Report at the end, per
``18-worker-model.md``), so naming it after that contract is correct, not
a violation. See `tests/unit/runtime/test_naming_audit.py` for the
permanent guard that nothing else in this codebase may be named "Worker".

Dispatch happens only via `CapabilityRegistry.resolve(context.capability)`
— `WorkerRuntime` never holds or imports a direct reference to a concrete
Capability Provider. An unknown or malformed capability, or any exception
a Capability Provider raises, is translated into a Failed
`ExecutionReport` here — it never escapes as a bare exception across the
Worker Contract boundary.

Cancellation is cooperative (design decision D5, `execution/channel.py`):
the same `ExecutionContext` — carrying the `CancellationToken` — flows
unchanged from `WorkerRuntime.execute()` into `Provider.execute()`, so a
Capability Provider observes cancellation itself and performs
acknowledge -> cleanup -> final events -> Report. `WorkerRuntime` never
wraps that call in a mechanism (e.g. `asyncio.wait_for`) that could raise
`asyncio.CancelledError` into the Provider's task — doing so would unwind
the stack and skip all four required steps. `WorkerRuntime`'s own
contribution to "closing the Channel" (`worker-runtime` spec's
cancellation scenario) is emitting the terminal `EndOfStream` event after
every dispatch outcome — success, failure, or cancellation alike.
"""

import uuid
from datetime import timedelta
from time import monotonic

from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.execution.context import ExecutionContext
from tibios_ray.execution.events import EndOfStream
from tibios_ray.execution.report import ExecutionPhase, ExecutionReport
from tibios_ray.runtime.errors import DispatchError
from tibios_ray.runtime.registry import CapabilityRegistry


def _failed_report(error: Exception, started_at: float) -> ExecutionReport:
    return ExecutionReport(
        phase=ExecutionPhase.FAILED,
        duration=timedelta(seconds=monotonic() - started_at),
        resource_usage={},
        metrics={},
        trace_id=uuid.uuid4().hex,
        failure=str(error),
    )


class WorkerRuntime:
    """Drives Received -> Prepared -> Running -> Completed/Failed for one
    execution, dispatching only via `CapabilityRegistry.resolve()` — never
    holding a direct reference to a concrete Capability Provider."""

    def __init__(self, registry: CapabilityRegistry) -> None:
        self._registry = registry

    async def execute(self, context: ExecutionContext) -> ExecutionReport:
        report = await self._dispatch(context)
        await context.channel.emit(EndOfStream(reason=report.failure))
        return report

    async def _dispatch(self, context: ExecutionContext) -> ExecutionReport:
        started_at = monotonic()
        try:
            provider = self._registry.resolve(CapabilityName(context.capability))
        except (ValueError, DispatchError) as error:
            return _failed_report(error, started_at)

        try:
            return await provider.execute(context)
        except Exception as error:  # never let a Provider failure escape the boundary
            return _failed_report(error, started_at)
