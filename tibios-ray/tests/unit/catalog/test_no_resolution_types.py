"""Resolution-type guards (design decision MC9): nothing from
`execution/ids.py` — `ObjectId`, `ObjectVersion`, `ContentHash`,
`ResolvedModelRef` — may appear as a field type on a public catalog
dataclass or in a `ModelCatalog` method's signature.

Generic type introspection, never a hardcoded `"ObjectId"` string check —
D3 made those types real dataclasses precisely so a *structural* check is
possible. This is the same enforcement style as
`tests/unit/selection/pyright_fixtures/rejects_bare_family_string.py`,
split here into a runtime half (this file, `dataclasses.fields` +
`typing.get_type_hints` + `inspect.signature`) and a static half
(`pyright_fixtures/rejects_resolved_model_ref.py`).

`catalog -> selection -> execution` is an accepted transitive *module*
edge (`selection.policy` is reused for `Quantization`) — see
`design.md`'s Architecture Overview. That is exactly why this guard is
written against the type *surface*, not the module import graph: a
module-graph-only check would flag the accepted `Quantization` reuse as a
false positive.
"""

import ast
import dataclasses
import inspect
import typing
from pathlib import Path

import tibios_ray
from tibios_ray.catalog.catalog import ModelCatalog
from tibios_ray.catalog.model import BackendSupport, ModelDescriptor
from tibios_ray.catalog.names import PublishedModelName

_PUBLIC_DATACLASSES = (PublishedModelName, BackendSupport, ModelDescriptor)
_FORBIDDEN_MODULE_PREFIX = "tibios_ray.execution"
_FORBIDDEN_QUERY_NAMES = frozenset({"choose", "best", "select", "plan"})
_CATALOG_PACKAGE = Path(tibios_ray.__file__).resolve().parent / "catalog"


def _leaf_types(annotation: object) -> set[type]:
    """Unwrap a type annotation through `frozenset`/`tuple`/`Mapping`
    (and any other generic) to the concrete leaf types it names."""
    origin = typing.get_origin(annotation)
    if origin is None:
        return {annotation} if isinstance(annotation, type) else set()
    leaves: set[type] = set()
    for arg in typing.get_args(annotation):
        if arg is Ellipsis:
            continue
        leaves |= _leaf_types(arg)
    return leaves


def _is_execution_typed(candidate: type) -> bool:
    return getattr(candidate, "__module__", "").startswith(_FORBIDDEN_MODULE_PREFIX)


class TestNoResolutionTypesInDataclassFields:
    def test_no_public_catalog_dataclass_field_is_execution_typed(self) -> None:
        offenders: list[tuple[str, str, set[type]]] = []
        for cls in _PUBLIC_DATACLASSES:
            hints = typing.get_type_hints(cls)
            for field in dataclasses.fields(cls):
                bad = {t for t in _leaf_types(hints[field.name]) if _is_execution_typed(t)}
                if bad:
                    offenders.append((cls.__name__, field.name, bad))
        assert not offenders, offenders


class TestNoResolutionTypesInModelCatalogSignatures:
    def test_no_public_method_parameter_or_return_is_execution_typed(self) -> None:
        offenders: list[tuple[str, str, set[type]]] = []
        for name, method in inspect.getmembers(ModelCatalog, predicate=inspect.isfunction):
            if name.startswith("_"):
                continue
            hints = typing.get_type_hints(method)
            signature = inspect.signature(method)
            for param_name in signature.parameters:
                if param_name == "self":
                    continue
                param_leaves = _leaf_types(hints.get(param_name, object))
                bad = {t for t in param_leaves if _is_execution_typed(t)}
                if bad:
                    offenders.append((name, param_name, bad))
            return_leaves = _leaf_types(hints.get("return", object))
            bad_return = {t for t in return_leaves if _is_execution_typed(t)}
            if bad_return:
                offenders.append((name, "return", bad_return))
        assert not offenders, offenders


class TestNoSelectionSurface:
    def test_no_public_modelcatalog_method_is_named_like_a_selection_query(self) -> None:
        method_names = {
            name for name, _ in inspect.getmembers(ModelCatalog, predicate=inspect.isfunction)
        }
        offenders = method_names & _FORBIDDEN_QUERY_NAMES
        assert not offenders, offenders

    def test_no_callable_defined_anywhere_in_catalog_is_named_like_a_selection_query(self) -> None:
        offenders: dict[str, set[str]] = {}
        for source_file in _CATALOG_PACKAGE.glob("*.py"):
            tree = ast.parse(source_file.read_text(), filename=str(source_file))
            names = {
                node.name
                for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            }
            bad = names & _FORBIDDEN_QUERY_NAMES
            if bad:
                offenders[source_file.name] = bad
        assert not offenders, offenders

    def test_modelcatalog_does_not_structurally_satisfy_model_selection_policy(self) -> None:
        # Import kept local: only this one test needs the selection
        # Protocol, and the reason is documentation, not a dependency
        # `catalog/` itself takes on (see module docstring).
        from tibios_ray.selection.policy import ModelSelectionPolicy

        policy_public_methods = {
            name for name in dir(ModelSelectionPolicy) if not name.startswith("_")
        }
        catalog_public_methods = {
            name for name, _ in inspect.getmembers(ModelCatalog, predicate=inspect.isfunction)
            if not name.startswith("_")
        }
        assert not policy_public_methods <= catalog_public_methods
