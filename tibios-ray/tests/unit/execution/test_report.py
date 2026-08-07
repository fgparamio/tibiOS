"""Tests for `tibios_ray.execution.report` — `ExecutionReport`,
`ExecutionPulse`, `ExecutionPhase`.
"""

import dataclasses
from datetime import timedelta

import pytest

from tibios_ray.execution.report import ExecutionPhase, ExecutionPulse, ExecutionReport


class TestExecutionPhase:
    def test_has_the_worker_local_lifecycle_states(self) -> None:
        assert {phase.value for phase in ExecutionPhase} == {
            "received",
            "prepared",
            "running",
            "completed",
            "failed",
            "cancelled",
        }


class TestExecutionReport:
    def test_holds_its_fields(self) -> None:
        report = ExecutionReport(
            phase=ExecutionPhase.COMPLETED,
            duration=timedelta(seconds=12),
            resource_usage={"cpu_seconds": 3.5},
            metrics={"tokens": 128.0},
            trace_id="trace-1",
        )
        assert report.phase is ExecutionPhase.COMPLETED
        assert report.duration == timedelta(seconds=12)
        assert report.resource_usage == {"cpu_seconds": 3.5}
        assert report.metrics == {"tokens": 128.0}
        assert report.trace_id == "trace-1"
        assert report.logs == ()
        assert report.failure is None

    def test_never_carries_a_data_field_for_application_output(self) -> None:
        # Application output travels only through the ExecutionChannel —
        # the Report must not offer a place to smuggle it in.
        field_names = {f.name for f in dataclasses.fields(ExecutionReport)}
        assert "output" not in field_names
        assert "data" not in field_names

    def test_is_frozen(self) -> None:
        report = ExecutionReport(
            phase=ExecutionPhase.FAILED,
            duration=timedelta(seconds=1),
            resource_usage={},
            metrics={},
            trace_id="trace-2",
            failure="boom",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            report.failure = "changed"  # type: ignore[misc]


class TestExecutionPulse:
    def test_holds_its_fields(self) -> None:
        pulse = ExecutionPulse(phase=ExecutionPhase.RUNNING, healthy=True)
        assert pulse.phase is ExecutionPhase.RUNNING
        assert pulse.healthy is True
        assert pulse.detail is None

    def test_is_frozen(self) -> None:
        pulse = ExecutionPulse(phase=ExecutionPhase.RUNNING, healthy=True)
        with pytest.raises(dataclasses.FrozenInstanceError):
            pulse.healthy = False  # type: ignore[misc]
