"""Conformance guard for the `backend-adapter` spec's Requirement
"Backend Adapter Contract Is Engine-Agnostic":

> GIVEN the `src/tibios_ray/backends/` source, including any nested
> subpackage
> WHEN inspected for imports of llama.cpp, TensorRT-LLM, vLLM, ONNX
> Runtime, or Faster-Whisper SDKs
> THEN none are found — only the abstract contract type exists

Static import inspection via `ast`, not a string grep, so re-exports,
aliases, and multi-level imports (`import onnxruntime.something`) are all
caught the same way. Two import shapes are scanned:

- `import <module>` / `from <module> import ...` (plain AST imports).
- `importlib.import_module("<literal>")` — the string-based import LC11
  (`llamacpp-backend` design.md) introduces into this codebase for lazy
  SDK loading. A plain AST import/importfrom scan cannot see a string
  argument, so since that pattern now exists to be copy-pasted straight
  into `backends/`, the guard flags it too (design.md "Recommended guard
  hardening").

The scanner walks the package tree recursively (`rglob`, not `glob`) so
a hypothetical nested adapter at `backends/engines/rogue.py` cannot hide
from it (`backend-adapter` spec, Scenario "The import guard inspects
backends/ recursively, not just top-level").
"""

import ast
from pathlib import Path

FORBIDDEN_ENGINE_MODULES = frozenset(
    {
        "llama_cpp",
        "tensorrt_llm",
        "vllm",
        "onnxruntime",
        "faster_whisper",
    }
)

BACKENDS_PACKAGE = Path(__file__).resolve().parents[3] / "src" / "tibios_ray" / "backends"


def _imported_top_level_modules(source_file: Path) -> set[str]:
    """Every top-level module a file imports, via plain `import`/`from
    import` AND via `importlib.import_module("<literal>")` string calls."""
    tree = ast.parse(source_file.read_text(), filename=str(source_file))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module.split(".")[0])
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
            modules.add(node.args[0].value.split(".")[0])
    return modules


def _scan_for_forbidden_engine_imports(package: Path) -> dict[str, set[str]]:
    """Recursively scans every `*.py` file under `package` and returns
    `{path relative to package: offending modules}` for every file
    importing a forbidden engine SDK. `rglob`, not `glob` — recursion is
    the entire point of this guard (see module docstring)."""
    offenders: dict[str, set[str]] = {}
    for source_file in package.rglob("*.py"):
        imported = _imported_top_level_modules(source_file)
        offending = imported & FORBIDDEN_ENGINE_MODULES
        if offending:
            offenders[str(source_file.relative_to(package))] = offending
    return offenders


def test_backends_package_has_python_source_files_to_check() -> None:
    # Guards against a silently-empty glob making the next test vacuous.
    source_files = list(BACKENDS_PACKAGE.rglob("*.py"))
    assert len(source_files) >= 6  # __init__, adapter, text, embedding, rerank, speech


def test_backends_source_imports_no_concrete_engine_sdk() -> None:
    offenders = _scan_for_forbidden_engine_imports(BACKENDS_PACKAGE)
    assert not offenders, f"forbidden engine SDK import(s) found: {offenders}"


def test_scanner_recurses_into_nested_packages(tmp_path: Path) -> None:
    """Recursion becomes an assertion, not a hope: builds a synthetic
    nested package mirroring the hypothetical `backends/engines/rogue.py`
    from the `backend-adapter` spec scenario, and proves the scanner
    finds an offender several directories deep."""
    nested = tmp_path / "sub" / "pkg"
    nested.mkdir(parents=True)
    (tmp_path / "__init__.py").write_text("")
    (tmp_path / "sub" / "__init__.py").write_text("")
    (nested / "__init__.py").write_text("")
    (nested / "bad.py").write_text("import llama_cpp\n")

    offenders = _scan_for_forbidden_engine_imports(tmp_path)

    assert offenders == {str(Path("sub") / "pkg" / "bad.py"): {"llama_cpp"}}


def test_scanner_finds_no_offenders_in_a_clean_nested_package(tmp_path: Path) -> None:
    # Companion to the recursion test above: proves the scanner does not
    # report false positives on an otherwise-clean tree, so the previous
    # test's non-empty result is meaningful, not a bug that always fires.
    nested = tmp_path / "sub" / "pkg"
    nested.mkdir(parents=True)
    (tmp_path / "__init__.py").write_text("")
    (tmp_path / "sub" / "__init__.py").write_text("")
    (nested / "__init__.py").write_text("")
    (nested / "fine.py").write_text("import os\n")

    assert _scan_for_forbidden_engine_imports(tmp_path) == {}


def test_scanner_flags_importlib_string_based_forbidden_imports(tmp_path: Path) -> None:
    """LC11 introduces `importlib.import_module("llama_cpp")` — a
    string-based import a plain AST import scan cannot see. Since the
    pattern now exists in this codebase to be copy-pasted, the guard
    must also flag it inside `backends/` (design.md "Recommended guard
    hardening")."""
    (tmp_path / "sneaky.py").write_text('import importlib\n\nimportlib.import_module("vllm")\n')

    offenders = _scan_for_forbidden_engine_imports(tmp_path)

    assert offenders == {"sneaky.py": {"vllm"}}
