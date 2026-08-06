"""In-memory `ExecutionChannel` fake (`tibios_ray.execution.channel`).

Consolidates the ad-hoc `RecordingChannel`/`_RecordingChannel`/`_FakeChannel`/
`_NullChannel` doubles hand-rolled across Phase 1-5's test modules
(`tests/unit/execution/test_channel.py`, `tests/unit/execution/test_context.py`,
`tests/unit/capabilities/test_provider.py`, `tests/unit/runtime/test_worker_runtime.py`)
into one shared shape, already proven correct by all 152 pre-existing tests
written before this package existed. Records every emitted event in order —
the "in-memory channel, no real infrastructure required" half of
`18-worker-model.md`'s testability principle.
"""

from tibios_ray.execution.events import ExecutionEvent


class InMemoryExecutionChannel:
    """A conforming `ExecutionChannel` (Protocol, design decision D1) that
    records every emitted event, in order, for test assertions."""

    def __init__(self) -> None:
        self.emitted: list[ExecutionEvent] = []

    async def emit(self, event: ExecutionEvent) -> None:
        self.emitted.append(event)
