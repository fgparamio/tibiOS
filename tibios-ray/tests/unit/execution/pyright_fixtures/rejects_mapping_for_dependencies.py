"""Pyright-only fixture proving `ExecutionContext.dependencies` structurally
rejects a `Mapping`/`dict` in its place, per design decision D10:
"`dependencies` becomes `tuple[ResolvedModelRef, ...]` — ordered,
unkeyed." A `Mapping` argument is no longer the declared type. Mirrors
`tests/unit/execution/pyright_fixtures/rejects_raw_string_for_workload_id.py`'s
pattern exactly.

This module is never imported by pytest and asserts nothing at runtime
(the function below is never called) — its only job is to be
type-checked by `uv run pyright`, included via `pyproject.toml`
`[tool.pyright] include = ["src", "tests"]`.

`# type: ignore[arg-type]` below suppresses the *expected* argument-type
error where a `Mapping[str, ResolvedModelRef]` is passed where
`ExecutionContext.dependencies` requires a `tuple[ResolvedModelRef, ...]`.
`pyproject.toml` sets `reportUnnecessaryTypeIgnoreComment = true`: if
`dependencies` is ever loosened to also accept a `Mapping` (readmitting a
fabricated key), the underlying argument-type error disappears, the
ignore comment becomes unnecessary, and `uv run pyright` fails the build
on `reportUnnecessaryTypeIgnoreComment` — turning a silent architecture
regression into a hard CI failure instead of a comment nobody notices.
"""

from collections.abc import Mapping
from datetime import timedelta

from tibios_ray.execution.channel import CancellationToken, ExecutionChannel
from tibios_ray.execution.context import (
    AllocationContract,
    ExecutionContext,
    ObservabilityContext,
    ResolvedModelRef,
    SecurityContext,
)


def _rejects_mapping_for_dependencies(
    dependencies: Mapping[str, ResolvedModelRef],
    channel: ExecutionChannel,
    cancellation: CancellationToken,
) -> ExecutionContext:
    return ExecutionContext(
        capability="chat.generate",
        allocation_contract=AllocationContract(max_execution_duration=timedelta(minutes=5)),
        dependencies=dependencies,  # type: ignore[arg-type]
        security_context=SecurityContext(tenant_id="t", principal_id="p", grant_scope=()),
        observability_context=ObservabilityContext(trace_id="trace", span_id="span"),
        execution_parameters={},
        channel=channel,
        cancellation=cancellation,
    )


def _accepts_tuple_for_dependencies(
    dependencies: tuple[ResolvedModelRef, ...],
    channel: ExecutionChannel,
    cancellation: CancellationToken,
) -> ExecutionContext:
    # Control case: the one shape `dependencies` actually accepts, with no
    # ignore comment — proves the fixture above is testing a real
    # rejection, not a signature pyright would reject for any argument.
    return ExecutionContext(
        capability="chat.generate",
        allocation_contract=AllocationContract(max_execution_duration=timedelta(minutes=5)),
        dependencies=dependencies,
        security_context=SecurityContext(tenant_id="t", principal_id="p", grant_scope=()),
        observability_context=ObservabilityContext(trace_id="trace", span_id="span"),
        execution_parameters={},
        channel=channel,
        cancellation=cancellation,
    )
