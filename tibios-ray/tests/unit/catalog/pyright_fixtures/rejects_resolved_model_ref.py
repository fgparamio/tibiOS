"""Pyright-only fixture closing the static half of design decision MC9:
`ModelCatalog.get` structurally rejects a `ResolvedModelRef` in place of
a `PublishedModelName`. Mirrors
`tests/unit/selection/pyright_fixtures/rejects_bare_family_string.py`'s
pattern exactly.

This module is never imported by pytest and asserts nothing at runtime
(the functions below are never called) — its only job is to be
type-checked by `uv run pyright`, included via `pyproject.toml`
`[tool.pyright] include = ["src", "tests"]`.

`# type: ignore[arg-type]` below suppresses the *expected* argument-type
error where a `ResolvedModelRef` is passed where `ModelCatalog.get`
requires a `PublishedModelName`. `pyproject.toml` sets
`reportUnnecessaryTypeIgnoreComment = true`: if `get`'s signature is ever
loosened to also accept a `ResolvedModelRef` (readmitting Object Store
identity into the catalog's query surface), the underlying argument-type
error disappears, the ignore comment becomes unnecessary, and
`uv run pyright` fails the build — turning a silent architecture
regression into a hard CI failure instead of a comment nobody notices.
"""

from tibios_ray.catalog.catalog import ModelCatalog
from tibios_ray.catalog.model import ModelDescriptor
from tibios_ray.catalog.names import PublishedModelName
from tibios_ray.execution.context import ResolvedModelRef


def _rejects_resolved_model_ref(
    catalog: ModelCatalog, resolved: ResolvedModelRef
) -> ModelDescriptor:
    return catalog.get(resolved)  # type: ignore[arg-type]


def _accepts_published_model_name(
    catalog: ModelCatalog, name: PublishedModelName
) -> ModelDescriptor:
    # Control case: the one shape `get` actually accepts, with no ignore
    # comment — proves the fixture above is testing a real rejection, not
    # a signature pyright would reject for any argument.
    return catalog.get(name)
