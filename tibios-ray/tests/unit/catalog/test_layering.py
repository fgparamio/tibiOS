"""Structural layering guards for `catalog/` (`design.md`'s "Testing
Strategy / Structural guards" table, slice 1 row):

- **Layering out**: nothing under `catalog/` may import
  `tibios_ray.execution` or `tibios_ray.runtime` — the catalog is inward
  reference data, never wired into the execution path.
- **Layering in**: nothing outside `catalog/` (and its tests) may import
  `tibios_ray.catalog` — this change adds zero production callers, and
  this guard makes that claim mechanical from the first commit onward.
- **Package-root imports**: no module *under* `catalog/` may import
  `tibios_ray.catalog` itself (CP8's circular-init hazard rule, reused
  verbatim from the archived `capability-providers` change).

Static `ast` inspection, not a string grep, so re-exports, aliases, and
multi-level imports are all caught the same way (mirrors
`tests/unit/backends/test_no_engine_imports.py` and
`tests/unit/runtime/test_naming_audit.py`).
"""

import ast
from pathlib import Path

import tibios_ray

_SRC_ROOT = Path(tibios_ray.__file__).resolve().parent
_CATALOG_PACKAGE = _SRC_ROOT / "catalog"

_FORBIDDEN_OUTWARD_MODULES = frozenset({"tibios_ray.execution", "tibios_ray.runtime"})
_CATALOG_PACKAGE_MODULE = "tibios_ray.catalog"


def _imported_dotted_modules(source_file: Path) -> set[str]:
    """Every dotted module name a file imports, at every prefix depth —
    `import tibios_ray.execution.ids` yields both `tibios_ray.execution`
    and `tibios_ray.execution.ids`, so a guard checking for the shorter
    name still catches a deeper import."""
    tree = ast.parse(source_file.read_text(), filename=str(source_file))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                modules.update(".".join(parts[: i + 1]) for i in range(len(parts)))
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            parts = node.module.split(".")
            modules.update(".".join(parts[: i + 1]) for i in range(len(parts)))
    return modules


def test_catalog_package_has_python_source_files_to_check() -> None:
    # Guards against a silently-empty glob making the next tests vacuous.
    assert _CATALOG_PACKAGE.is_dir()
    source_files = list(_CATALOG_PACKAGE.glob("*.py"))
    assert len(source_files) >= 3  # __init__, errors, names


def test_catalog_source_imports_no_execution_or_runtime_module() -> None:
    for source_file in _CATALOG_PACKAGE.glob("*.py"):
        imported = _imported_dotted_modules(source_file)
        offending = imported & _FORBIDDEN_OUTWARD_MODULES
        assert not offending, f"{source_file.name} imports forbidden module(s): {offending}"


def test_no_module_outside_catalog_imports_catalog() -> None:
    offenders: dict[str, set[str]] = {}
    for source_file in _SRC_ROOT.rglob("*.py"):
        if _CATALOG_PACKAGE in source_file.parents:
            continue
        imported = _imported_dotted_modules(source_file)
        offending = {
            m
            for m in imported
            if m == _CATALOG_PACKAGE_MODULE or m.startswith(_CATALOG_PACKAGE_MODULE + ".")
        }
        if offending:
            offenders[str(source_file.relative_to(_SRC_ROOT))] = offending

    assert not offenders, (
        "found import(s) of tibios_ray.catalog outside catalog/ — this change adds "
        f"zero production callers: {offenders}"
    )


def _imports_package_root_exactly(source_file: Path) -> bool:
    """Whether `source_file` literally names `tibios_ray.catalog` — the
    package root — as an import target: `import tibios_ray.catalog`,
    `from tibios_ray.catalog import X`, or `from tibios_ray import
    catalog`. Deliberately NOT a prefix match: `from
    tibios_ray.catalog.errors import X` names the `errors` submodule
    directly and is the permitted pattern used throughout
    `capabilities/`; only reaching through the package root itself is
    CP8's circular-init hazard."""
    tree = ast.parse(source_file.read_text(), filename=str(source_file))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == _CATALOG_PACKAGE_MODULE for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module == _CATALOG_PACKAGE_MODULE:
                return True
            if node.module == "tibios_ray" and any(
                alias.name == "catalog" for alias in node.names
            ):
                return True
    return False


def test_no_module_under_catalog_imports_the_catalog_package_root() -> None:
    offenders = [
        str(source_file.relative_to(_SRC_ROOT))
        for source_file in _CATALOG_PACKAGE.rglob("*.py")
        if _imports_package_root_exactly(source_file)
    ]

    assert not offenders, (
        f"module(s) under catalog/ import tibios_ray.catalog itself (CP8's "
        f"circular-init hazard): {offenders}"
    )
