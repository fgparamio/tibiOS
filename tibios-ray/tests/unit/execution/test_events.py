"""Tests for `tibios_ray.execution.events` — the `ExecutionEvent` tagged
union (design decision D7).
"""

import dataclasses

import pytest

from tibios_ray.execution.events import (
    CheckpointCreated,
    EndOfStream,
    MetricsSnapshot,
    OutputChunk,
    Progress,
    Warning,
)


class TestOutputChunk:
    def test_carries_discriminant_and_data(self) -> None:
        chunk = OutputChunk(data=b"hello", sequence=0)
        assert chunk.type == "output_chunk"
        assert chunk.data == b"hello"
        assert chunk.sequence == 0

    def test_is_frozen(self) -> None:
        chunk = OutputChunk(data=b"hello", sequence=0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            chunk.sequence = 1  # type: ignore[misc]


class TestProgress:
    def test_carries_discriminant_and_fraction(self) -> None:
        progress = Progress(fraction_complete=0.5)
        assert progress.type == "progress"
        assert progress.fraction_complete == 0.5
        assert progress.message is None

    def test_is_frozen(self) -> None:
        progress = Progress(fraction_complete=0.5)
        with pytest.raises(dataclasses.FrozenInstanceError):
            progress.fraction_complete = 0.9  # type: ignore[misc]


class TestWarning:
    def test_carries_discriminant_and_message(self) -> None:
        warning = Warning(message="disk almost full")
        assert warning.type == "warning"
        assert warning.message == "disk almost full"

    def test_is_frozen(self) -> None:
        warning = Warning(message="disk almost full")
        with pytest.raises(dataclasses.FrozenInstanceError):
            warning.message = "changed"  # type: ignore[misc]


class TestCheckpointCreated:
    def test_carries_discriminant_and_checkpoint_id(self) -> None:
        event = CheckpointCreated(checkpoint_id="ckpt-1")
        assert event.type == "checkpoint_created"
        assert event.checkpoint_id == "ckpt-1"

    def test_is_frozen(self) -> None:
        event = CheckpointCreated(checkpoint_id="ckpt-1")
        with pytest.raises(dataclasses.FrozenInstanceError):
            event.checkpoint_id = "ckpt-2"  # type: ignore[misc]


class TestMetricsSnapshot:
    def test_carries_discriminant_and_metrics(self) -> None:
        snapshot = MetricsSnapshot(metrics={"tokens_per_second": 42.0})
        assert snapshot.type == "metrics_snapshot"
        assert snapshot.metrics == {"tokens_per_second": 42.0}

    def test_is_frozen(self) -> None:
        snapshot = MetricsSnapshot(metrics={})
        with pytest.raises(dataclasses.FrozenInstanceError):
            snapshot.metrics = {"x": 1.0}  # type: ignore[misc]


class TestEndOfStream:
    def test_carries_discriminant_and_optional_reason(self) -> None:
        end = EndOfStream()
        assert end.type == "end_of_stream"
        assert end.reason is None

    def test_is_frozen(self) -> None:
        end = EndOfStream()
        with pytest.raises(dataclasses.FrozenInstanceError):
            end.reason = "cancelled"  # type: ignore[misc]


class TestExecutionEventUnion:
    def test_all_six_variants_are_distinguishable_by_discriminant(self) -> None:
        events = [
            OutputChunk(data=b"x", sequence=0),
            Progress(fraction_complete=0.1),
            Warning(message="w"),
            CheckpointCreated(checkpoint_id="c"),
            MetricsSnapshot(metrics={}),
            EndOfStream(),
        ]
        discriminants = {event.type for event in events}
        assert discriminants == {
            "output_chunk",
            "progress",
            "warning",
            "checkpoint_created",
            "metrics_snapshot",
            "end_of_stream",
        }

    def test_match_exhaustively_dispatches_on_discriminant(self) -> None:
        def describe(event: object) -> str:
            match event:
                case OutputChunk():
                    return "output_chunk"
                case Progress():
                    return "progress"
                case Warning():
                    return "warning"
                case CheckpointCreated():
                    return "checkpoint_created"
                case MetricsSnapshot():
                    return "metrics_snapshot"
                case EndOfStream():
                    return "end_of_stream"
                case _:
                    raise AssertionError("unreachable")

        assert describe(OutputChunk(data=b"x", sequence=0)) == "output_chunk"
        assert describe(EndOfStream()) == "end_of_stream"
