"""Worker Contract vocabulary: ``ExecutionContext``, ``ExecutionChannel``,
``ExecutionEvent``, ``ExecutionReport``, ``ExecutionPulse``.

See ``../tibios-core/docs/architecture/18-worker-model.md`` and
``openspec/changes/ray-worker-runtime/design.md``.

This package has zero dependencies on any other ``tibios_ray`` package —
it is the foundation every other layer (``runtime/``, ``capabilities/``,
``selection/``, ``backends/``) depends on, never the reverse.
"""

from tibios_ray.execution.channel import CancellationToken, ExecutionChannel
from tibios_ray.execution.context import (
    AllocationContract,
    ExecutionContext,
    ResolvedModelRef,
)
from tibios_ray.execution.events import (
    CheckpointCreated,
    EndOfStream,
    ExecutionEvent,
    MetricsSnapshot,
    OutputChunk,
    Progress,
    Warning,
)
from tibios_ray.execution.ids import ContentHash, ObjectId, ObjectVersion
from tibios_ray.execution.report import ExecutionPhase, ExecutionPulse, ExecutionReport

__all__ = [
    "AllocationContract",
    "CancellationToken",
    "CheckpointCreated",
    "ContentHash",
    "EndOfStream",
    "ExecutionChannel",
    "ExecutionContext",
    "ExecutionEvent",
    "ExecutionPhase",
    "ExecutionPulse",
    "ExecutionReport",
    "MetricsSnapshot",
    "ObjectId",
    "ObjectVersion",
    "OutputChunk",
    "Progress",
    "ResolvedModelRef",
    "Warning",
]
