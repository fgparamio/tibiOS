"""`tensorrt-llm-text-backend` spec, Requirement "Engine Compilation Is
Never Invoked by the Runtime" — Scenario "No compilation call exists in
the Backend's call path": `engines/tensorrt.py`'s source must never
reference an offline-compilation entry point or a subprocess escape
hatch (design.md "Invariant 2", mirroring `test_no_engine_imports.py`'s
static-inspection style).

A source-text scan, not an AST-import scan (`test_no_engine_imports.py`
already covers imports): the forbidden tokens here are identifiers and
CLI-tool names that could appear as an attribute access, a string
literal, or a comment — none of which a plain `ast.Import` walk would
catch.
"""

import inspect
from pathlib import Path

import tibios_ray.engines.tensorrt as tensorrt_module

# design.md "Testing Strategy", Invariant 2 row.
_FORBIDDEN_TOKENS = (
    "trtllm-build",
    "build_config",
    "BuildConfig",
    "quantize",
    "subprocess",
)


def test_source_contains_no_compilation_entry_point() -> None:
    source = Path(inspect.getfile(tensorrt_module)).read_text()

    offenders = [token for token in _FORBIDDEN_TOKENS if token in source]

    assert not offenders, f"compilation entry point token(s) found: {offenders}"
