"""Pyright-only fixture proving `WorkloadId`/`AllocationId` structurally
reject a bare `str` in their place, per the `execution-identity` spec
Scenario "WorkloadId and AllocationId are type-distinct from raw strings":
"the type checker rejects the substitution and no implicit conversion
occurs." Mirrors
`tests/unit/selection/pyright_fixtures/rejects_bare_family_string.py`'s
pattern exactly.

This module is never imported by pytest and asserts nothing at runtime
(the functions below are never called) — its only job is to be
type-checked by `uv run pyright`, included via `pyproject.toml`
`[tool.pyright] include = ["src", "tests"]`.

`# type: ignore[arg-type]` below suppresses the *expected* argument-type
error where a raw `str` is passed where a `WorkloadId`/`AllocationId` is
required. `pyproject.toml` sets `reportUnnecessaryTypeIgnoreComment = true`:
if either signature is ever loosened to also accept a bare `str`, the
underlying argument-type error disappears, the ignore comment becomes
unnecessary, and `uv run pyright` fails the build on
`reportUnnecessaryTypeIgnoreComment` — turning a silent architecture
regression into a hard CI failure instead of a comment nobody notices.
"""

from tibios_ray.execution.ids import AllocationId, WorkloadId


def _rejects_raw_string_for_workload_id(value: str) -> WorkloadId:
    return value  # type: ignore[return-value]


def _rejects_raw_string_for_allocation_id(value: str) -> AllocationId:
    return value  # type: ignore[return-value]


def _accepts_workload_id(workload_id: WorkloadId) -> WorkloadId:
    # Control case: the one shape each function actually accepts, with no
    # ignore comment — proves the fixtures above are testing a real
    # rejection, not a signature pyright would reject for any argument.
    return workload_id


def _accepts_allocation_id(allocation_id: AllocationId) -> AllocationId:
    return allocation_id
