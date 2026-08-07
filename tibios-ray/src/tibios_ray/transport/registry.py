"""`InFlightRegistry` — the in-flight `WorkloadId` correlation table
(design decision D15).

Owns each in-flight execution's transport-minted `CancellationToken` and
its transport-observable phase. `WorkerRuntime` publishes no phase
transitions, so `PREPARED` is genuinely unobservable — no code path here
ever reports it; an entry starts at `RECEIVED` and the only transition
modeled is `RECEIVED` -> `RUNNING`.

`register` is synchronous — no `await` inside it — so a `Cancel` issued
immediately after `SubmitJob`, before the calling coroutine's first
`await`, always finds the `WorkloadId` already registered
(`worker-grpc-transport` O1). `lookup` raises `UnknownWorkloadError`
rather than returning `None` for an unregistered or already-deregistered
`WorkloadId` (O3); `register` raises `DuplicateWorkloadError` without
disturbing the existing entry for an already-registered `WorkloadId`
(O4); `deregister` removes the entry unconditionally, on success,
failure, or cancellation alike (O2).
"""

import asyncio
from dataclasses import dataclass, field

from tibios_ray.execution.channel import CancellationToken
from tibios_ray.execution.ids import WorkloadId
from tibios_ray.execution.report import ExecutionPhase, ExecutionReport
from tibios_ray.transport.errors import DuplicateWorkloadError, UnknownWorkloadError


@dataclass(slots=True)
class RegistryEntry:
    """One in-flight execution's correlation state: its cancellation
    token, its driving task, and its transport-observable phase."""

    token: CancellationToken
    task: "asyncio.Task[ExecutionReport]"
    phase: ExecutionPhase = field(default=ExecutionPhase.RECEIVED)


class InFlightRegistry:
    """The `WorkloadId` -> `RegistryEntry` correlation table S4b's
    servicer consults for `SubmitJob`/`Cancel`/`Pulse`."""

    def __init__(self) -> None:
        self._entries: dict[WorkloadId, RegistryEntry] = {}

    def register(
        self,
        workload_id: WorkloadId,
        token: CancellationToken,
        task: "asyncio.Task[ExecutionReport]",
    ) -> None:
        """Registers `workload_id` synchronously at phase `RECEIVED`.
        Raises `DuplicateWorkloadError` — without disturbing the
        existing entry — if `workload_id` is already registered (O4)."""
        if workload_id in self._entries:
            raise DuplicateWorkloadError(workload_id.value)
        self._entries[workload_id] = RegistryEntry(token=token, task=task)

    def mark_running(self, workload_id: WorkloadId) -> None:
        """Transitions a registered entry's phase to `RUNNING`. Raises
        `UnknownWorkloadError` if `workload_id` is not registered."""
        self.lookup(workload_id).phase = ExecutionPhase.RUNNING

    def deregister(self, workload_id: WorkloadId) -> None:
        """Removes the entry for `workload_id`, if present, unconditionally
        (O2) — a no-op if it is already absent."""
        self._entries.pop(workload_id, None)

    def lookup(self, workload_id: WorkloadId) -> RegistryEntry:
        """Raises `UnknownWorkloadError` rather than returning `None`
        for an unregistered or already-deregistered `workload_id` (O3)."""
        try:
            return self._entries[workload_id]
        except KeyError:
            raise UnknownWorkloadError(workload_id.value) from None
