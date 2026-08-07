"""Structural guard for `worker-configuration` spec's Requirement
"Composition Root Is the Configuration Surface's Sole Consumer" (D19
guard row, `design.md`'s Testing Strategy table):

> Only `worker.py::build_runtime()` MUST read from the configuration
> surface. No Provider, Backend, or engine adapter MUST read the
> underlying configuration source (whatever it is) or the configuration
> surface directly.

Scope note: the requirement names three module categories —
"Provider" (`capabilities/`), "Backend" (`backends/`), "engine adapter"
(`engines/`) — and the frozen scenario narrows the mechanical check to
"the `capabilities/` and `backends/` module trees". This guard scans
every `*.py` under `src/tibios_ray/` *except* `worker.py` and
`config.py` themselves, plus `server.py`.

`server.py` is excluded deliberately, not silently: it is the process
entry point that calls `build_runtime()` (D29 — "`build_runtime()`
exactly once from `server.py:22`"), not a Provider/Backend/engine
adapter, and its existing `os.environ.get("TIBIOS_RAY_ADDRESS", …)`
read is `design.md`'s own cited, unchanged precedent for "the entire
current deployment surface" (D19 rationale) — a network address, not
per-engine artifact configuration. Excluding it here keeps this guard
mechanically true instead of failing on day one against code this
change does not touch.

Static `ast` inspection for two things, mirroring
`tests/unit/catalog/test_layering.py` and
`tests/unit/backends/test_no_engine_imports.py`:
- any `os.environ`/`os.getenv` access, or `from os import environ`/
  `from os import getenv`
- any import of `tibios_ray.config` (module or submember)
"""

import ast
from pathlib import Path

import tibios_ray

_SRC_ROOT = Path(tibios_ray.__file__).resolve().parent
_EXCLUDED_FILES = frozenset({"worker.py", "config.py", "server.py"})
_CONFIG_MODULE = "tibios_ray.config"


def _audited_source_files() -> list[Path]:
    return [
        path
        for path in sorted(_SRC_ROOT.rglob("*.py"))
        if path.name not in _EXCLUDED_FILES
    ]


def _reads_os_environ(source_file: Path) -> bool:
    tree = ast.parse(source_file.read_text(), filename=str(source_file))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr in {"environ", "getenv"}
            and isinstance(node.value, ast.Name)
            and node.value.id == "os"
        ):
            return True
        if isinstance(node, ast.ImportFrom) and node.module == "os":
            if any(alias.name in {"environ", "getenv"} for alias in node.names):
                return True
    return False


def _imports_config_module(source_file: Path) -> bool:
    tree = ast.parse(source_file.read_text(), filename=str(source_file))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(
                alias.name == _CONFIG_MODULE or alias.name.startswith(_CONFIG_MODULE + ".")
                for alias in node.names
            ):
                return True
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module == _CONFIG_MODULE or node.module.startswith(_CONFIG_MODULE + "."):
                return True
            if node.module == "tibios_ray" and any(
                alias.name == "config" for alias in node.names
            ):
                return True
    return False


def test_audited_source_files_is_non_empty() -> None:
    # Guards against a silently-empty glob making the next tests vacuous.
    assert len(_audited_source_files()) >= 10


def test_no_module_outside_worker_and_config_reads_os_environ() -> None:
    offenders = [
        str(source_file.relative_to(_SRC_ROOT))
        for source_file in _audited_source_files()
        if _reads_os_environ(source_file)
    ]

    assert not offenders, (
        "module(s) outside worker.py/config.py read os.environ directly "
        f"(worker-configuration spec, sole-consumer requirement): {offenders}"
    )


def test_no_module_outside_worker_imports_the_config_module() -> None:
    offenders = [
        str(source_file.relative_to(_SRC_ROOT))
        for source_file in _audited_source_files()
        if _imports_config_module(source_file)
    ]

    assert not offenders, (
        "module(s) outside worker.py import tibios_ray.config directly "
        f"(worker-configuration spec, sole-consumer requirement): {offenders}"
    )


def test_scanner_detects_direct_os_environ_access(tmp_path: Path) -> None:
    (tmp_path / "sneaky.py").write_text("import os\n\nos.environ.get('X')\n")
    assert _reads_os_environ(tmp_path / "sneaky.py") is True


def test_scanner_detects_from_os_import_environ(tmp_path: Path) -> None:
    (tmp_path / "sneaky.py").write_text("from os import environ\n\nenviron.get('X')\n")
    assert _reads_os_environ(tmp_path / "sneaky.py") is True


def test_scanner_finds_no_offender_in_a_clean_file(tmp_path: Path) -> None:
    (tmp_path / "fine.py").write_text("import os\n\nos.path.join('a', 'b')\n")
    assert _reads_os_environ(tmp_path / "fine.py") is False


def test_scanner_detects_config_module_import(tmp_path: Path) -> None:
    (tmp_path / "sneaky.py").write_text("from tibios_ray.config import WorkerConfig\n")
    assert _imports_config_module(tmp_path / "sneaky.py") is True


def test_scanner_finds_no_config_import_offender_in_a_clean_file(tmp_path: Path) -> None:
    (tmp_path / "fine.py").write_text("from tibios_ray.backends.adapter import BackendId\n")
    assert _imports_config_module(tmp_path / "fine.py") is False
