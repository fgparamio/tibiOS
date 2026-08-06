"""Structural layering guard for `engines/` (design.md "Technical
Approach": "Layer direction is unchanged: `runtime -> capabilities ->
selection -> backends`, plus the new edge `engines -> backends`
**only**"). Every `tibios_ray.*` import inside `src/tibios_ray/engines/
*.py` must be `tibios_ray.backends` (or a submodule of it) — never
`catalog`, `selection`, `capabilities`, or `runtime`. This is the
mechanical enforcement of LC12 ("an Engine never performs model
selection").

Static `ast` inspection, not a string grep — mirrors
`tests/unit/backends/test_no_engine_imports.py` and
`tests/unit/catalog/test_layering.py`.
"""

import ast
from pathlib import Path

import tibios_ray

_SRC_ROOT = Path(tibios_ray.__file__).resolve().parent
_ENGINES_PACKAGE = _SRC_ROOT / "engines"
# `tibios_ray.backends`: the one permitted outward edge (design.md
# "engines -> backends only"). `tibios_ray.engines`: intra-package
# re-exports (`__init__.py` importing its own `llamacpp` submodule) are
# not a layering violation — they carry no dependency on another layer.
_ALLOWED_TIBIOS_RAY_MODULES = ("tibios_ray.backends", "tibios_ray.engines")


def _imported_dotted_tibios_ray_modules(source_file: Path) -> set[str]:
    tree = ast.parse(source_file.read_text(), filename=str(source_file))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "tibios_ray" or alias.name.startswith("tibios_ray."):
                    modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module == "tibios_ray" or node.module.startswith("tibios_ray."):
                modules.add(node.module)
    return modules


def test_engines_package_has_python_source_files_to_check() -> None:
    # Guards against a silently-empty glob making the next test vacuous.
    assert _ENGINES_PACKAGE.is_dir()
    source_files = list(_ENGINES_PACKAGE.glob("*.py"))
    assert len(source_files) >= 2  # __init__, llamacpp


def test_engines_source_imports_only_from_tibios_ray_backends() -> None:
    offenders: dict[str, set[str]] = {}
    for source_file in _ENGINES_PACKAGE.glob("*.py"):
        imported = _imported_dotted_tibios_ray_modules(source_file)
        offending = {
            module
            for module in imported
            if not any(
                module == allowed or module.startswith(allowed + ".")
                for allowed in _ALLOWED_TIBIOS_RAY_MODULES
            )
        }
        if offending:
            offenders[source_file.name] = offending

    assert not offenders, f"engines/ imported outside tibios_ray.backends (LC12): {offenders}"
