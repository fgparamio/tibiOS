"""Conformance guard for the `worker-grpc-transport` spec's Requirement
"Generated Code Is Isolated To The Transport Package":

> GIVEN the tibios-ray source tree outside `src/tibios_ray/transport/`
> WHEN scanned recursively for `grpc` or `_pb2` imports (plain imports
> and `importlib.import_module` string imports alike)
> THEN zero matches are found

Retargeted from `tests/unit/backends/test_no_engine_imports.py`
(`design.md` D13 / "Testing Strategy" — Isolation guard): same static
`ast`-based scan, same two import shapes, same `rglob` recursion so a
hypothetical nested module cannot hide from it. The forbidden set here
is not a fixed module list — it is "`grpc`, any `grpc_tools` symbol, or
any module whose name contains `_pb2`" — because the generated modules
are named per-proto (`worker_pb2`, `identity_pb2`, `worker_pb2_grpc`,
...) and a fixed allowlist would need updating every time `../proto`
grows a file.
"""

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[3] / "src" / "tibios_ray"
TRANSPORT_PACKAGE = SRC_ROOT / "transport"

_FORBIDDEN_EXACT = frozenset({"grpc", "grpc_tools"})


def _is_forbidden(module_name: str) -> bool:
    top_level = module_name.split(".")[0]
    return top_level in _FORBIDDEN_EXACT or "_pb2" in module_name


def _imported_modules(source_file: Path) -> set[str]:
    """Every module a file imports, via plain `import`/`from import` AND
    via `importlib.import_module("<literal>")` string calls — matching
    the shapes `test_no_engine_imports.py` already covers."""
    tree = ast.parse(source_file.read_text(), filename=str(source_file))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "import_module"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "importlib"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            modules.add(node.args[0].value)
    return modules


def _scan_for_transport_imports_outside_transport(
    package: Path, *, exclude: Path
) -> dict[str, set[str]]:
    """Recursively scans every `*.py` file under `package`, **excluding**
    anything under `exclude` (the transport package), and returns `{path
    relative to package: offending modules}` for every file importing
    `grpc`, `grpc_tools`, or any `*_pb2*` module."""
    offenders: dict[str, set[str]] = {}
    for source_file in package.rglob("*.py"):
        if exclude in source_file.parents:
            continue
        imported = _imported_modules(source_file)
        offending = {m for m in imported if _is_forbidden(m)}
        if offending:
            offenders[str(source_file.relative_to(package))] = offending
    return offenders


def test_src_tree_has_python_source_files_to_check() -> None:
    # Guards against a silently-empty glob making the next test vacuous.
    source_files = [p for p in SRC_ROOT.rglob("*.py") if TRANSPORT_PACKAGE not in p.parents]
    assert len(source_files) >= 20


def test_no_module_outside_transport_imports_grpc_or_pb2_symbols() -> None:
    offenders = _scan_for_transport_imports_outside_transport(
        SRC_ROOT, exclude=TRANSPORT_PACKAGE
    )
    assert not offenders, f"forbidden transport import(s) found: {offenders}"


def test_scanner_recurses_into_nested_packages(tmp_path: Path) -> None:
    """Recursion becomes an assertion, not a hope, mirroring the
    `backend-adapter` guard's synthetic nested-package test."""
    transport = tmp_path / "transport"
    transport.mkdir()
    nested = tmp_path / "sub" / "pkg"
    nested.mkdir(parents=True)
    (tmp_path / "__init__.py").write_text("")
    (tmp_path / "sub" / "__init__.py").write_text("")
    (nested / "__init__.py").write_text("")
    (nested / "bad.py").write_text("import grpc\n")

    offenders = _scan_for_transport_imports_outside_transport(tmp_path, exclude=transport)

    assert offenders == {str(Path("sub") / "pkg" / "bad.py"): {"grpc"}}


def test_scanner_finds_no_offenders_in_a_clean_nested_package(tmp_path: Path) -> None:
    transport = tmp_path / "transport"
    transport.mkdir()
    nested = tmp_path / "sub" / "pkg"
    nested.mkdir(parents=True)
    (tmp_path / "__init__.py").write_text("")
    (tmp_path / "sub" / "__init__.py").write_text("")
    (nested / "__init__.py").write_text("")
    (nested / "fine.py").write_text("import os\n")

    assert _scan_for_transport_imports_outside_transport(tmp_path, exclude=transport) == {}


def test_scanner_excludes_files_inside_transport_package(tmp_path: Path) -> None:
    transport = tmp_path / "transport"
    transport.mkdir()
    (transport / "servicer.py").write_text("import grpc\n")

    assert _scan_for_transport_imports_outside_transport(tmp_path, exclude=transport) == {}


def test_scanner_flags_importlib_string_based_pb2_imports(tmp_path: Path) -> None:
    """A string-based `importlib.import_module("...worker_pb2")` load is
    the same evasion `test_no_engine_imports.py` guards `backends/`
    against; the transport guard must flag it too."""
    transport = tmp_path / "transport"
    transport.mkdir()
    (tmp_path / "sneaky.py").write_text(
        'import importlib\n\n'
        'importlib.import_module("tibios_ray.transport._generated.tibios.worker.v1.worker_pb2")\n'
    )

    offenders = _scan_for_transport_imports_outside_transport(tmp_path, exclude=transport)

    assert offenders == {
        "sneaky.py": {"tibios_ray.transport._generated.tibios.worker.v1.worker_pb2"}
    }


def test_scanner_flags_plain_grpc_tools_import(tmp_path: Path) -> None:
    transport = tmp_path / "transport"
    transport.mkdir()
    (tmp_path / "sneaky.py").write_text("from grpc_tools import protoc\n")

    offenders = _scan_for_transport_imports_outside_transport(tmp_path, exclude=transport)

    assert offenders == {"sneaky.py": {"grpc_tools"}}
