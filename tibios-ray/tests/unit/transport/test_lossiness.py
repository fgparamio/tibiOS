"""3b.13 — the domain->wire lossiness drop list (design decision D16) is
**closed**: for each domain type, the set of fields with no wire home
equals the documented D16 rows exactly. Adding an undocumented dropped
field must break this test rather than silently widening the drop list.

`type` (the PEP 695 tagged-union discriminator on the `ExecutionEvent`
member dataclasses, D7) is excluded from consideration everywhere below:
it selects the wire `oneof` arm itself and is never a candidate for a
"dropped field" — it has no domain meaning beyond routing.
"""

import dataclasses

from tibios_ray.execution.events import EndOfStream, Warning
from tibios_ray.execution.report import ExecutionPulse, ExecutionReport

_DISCRIMINATOR = {"type"}


def _fields(cls: type) -> set[str]:
    return {f.name for f in dataclasses.fields(cls)} - _DISCRIMINATOR


class TestExecutionReportDropList:
    def test_dropped_fields_match_d16_exactly(self) -> None:
        mapped = {"phase", "duration", "trace_id", "failure"}
        dropped = _fields(ExecutionReport) - mapped

        assert dropped == {"resource_usage", "metrics", "logs"}


class TestExecutionPulseDropList:
    def test_dropped_fields_match_d16_exactly(self) -> None:
        mapped = {"phase", "healthy"}
        dropped = _fields(ExecutionPulse) - mapped

        assert dropped == {"detail"}


class TestWarningDropList:
    def test_dropped_fields_match_d16_exactly(self) -> None:
        mapped = {"message"}
        dropped = _fields(Warning) - mapped

        assert dropped == {"code"}


class TestEndOfStreamDropList:
    def test_dropped_fields_match_d16_exactly(self) -> None:
        mapped: set[str] = set()
        dropped = _fields(EndOfStream) - mapped

        assert dropped == {"reason"}
