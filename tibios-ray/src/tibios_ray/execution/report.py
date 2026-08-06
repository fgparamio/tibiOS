"""`ExecutionReport`/`ExecutionPulse` — operational vocabulary produced by
a Capability Provider.

Reports summarize execution; they never transport application output
(``18-worker-model.md``: "Execution produces events. Completion produces
a report."). Phase 1 models only the fields named in
``18-worker-model.md`` (open question tracked in ``design.md``).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum


class ExecutionPhase(Enum):
    """A Worker-local, fine-grained execution state machine — distinct
    from the Runtime-wide `WorkloadState` (``18-worker-model.md``); they
    share the word "Running" but are two separate state machines."""

    RECEIVED = "received"
    PREPARED = "prepared"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionReport:
    """Summarizes a completed (or failed) execution — status, duration,
    resource usage, metrics, trace identifiers, logs, failure. Never
    carries application output; that travels only through the
    `ExecutionChannel`."""

    phase: ExecutionPhase
    duration: timedelta
    resource_usage: Mapping[str, float]
    metrics: Mapping[str, float]
    trace_id: str
    logs: tuple[str, ...] = ()
    failure: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionPulse:
    """Health of a single in-progress execution — never process health.
    Deliberately not called a "heartbeat" (``18-worker-model.md``): one
    Capability Provider may execute many workloads, a Pulse belongs to
    one execution."""

    phase: ExecutionPhase
    healthy: bool
    detail: str | None = None
