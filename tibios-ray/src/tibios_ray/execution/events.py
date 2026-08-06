"""`ExecutionEvent` — the typed stream a Capability Provider emits through
the Execution Channel (``18-worker-model.md``).

Modeled as a PEP 695 tagged union of frozen dataclasses (design decision
D7, ``design.md``) so `pyright` can check `match` exhaustiveness: adding a
new event kind without updating every consumer breaks loudly instead of
silently falling through.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True, kw_only=True)
class OutputChunk:
    """Application output produced during execution."""

    type: Literal["output_chunk"] = "output_chunk"
    data: bytes
    sequence: int


@dataclass(frozen=True, slots=True, kw_only=True)
class Progress:
    """Execution progress, independent of output."""

    type: Literal["progress"] = "progress"
    fraction_complete: float
    message: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Warning:
    """A non-fatal condition surfaced during execution."""

    type: Literal["warning"] = "warning"
    message: str
    code: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class CheckpointCreated:
    """A checkpoint was created. Checkpoint creation is a Capability
    Provider capability; checkpoint policy belongs to the Runtime
    (``18-worker-model.md``)."""

    type: Literal["checkpoint_created"] = "checkpoint_created"
    checkpoint_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MetricsSnapshot:
    """A point-in-time observability sample."""

    type: Literal["metrics_snapshot"] = "metrics_snapshot"
    metrics: Mapping[str, float]


@dataclass(frozen=True, slots=True, kw_only=True)
class EndOfStream:
    """Terminal marker: no further `ExecutionEvent`s will be emitted."""

    type: Literal["end_of_stream"] = "end_of_stream"
    reason: str | None = None


type ExecutionEvent = (
    OutputChunk | Progress | Warning | CheckpointCreated | MetricsSnapshot | EndOfStream
)
