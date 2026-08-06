"""Conformance guard for the `backend-adapter` spec's Requirement
"Backend Adapter Contract Is Engine-Agnostic":

> GIVEN the Phase 1 `src/tibios_ray/backends/` source
> WHEN inspected for imports of llama.cpp, TensorRT-LLM, vLLM, ONNX
> Runtime, or Faster-Whisper SDKs
> THEN none are found — only the abstract contract type exists

Static import inspection via `ast`, not a string grep, so re-exports,
aliases, and multi-level imports (`import onnxruntime.something`) are all
caught the same way.
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
    tree = ast.parse(source_file.read_text(), filename=str(source_file))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module.split(".")[0])
    return modules


def test_backends_package_has_python_source_files_to_check() -> None:
    # Guards against a silently-empty glob making the next test vacuous.
    source_files = list(BACKENDS_PACKAGE.glob("*.py"))
    assert len(source_files) >= 6  # __init__, adapter, text, embedding, rerank, speech


def test_backends_source_imports_no_concrete_engine_sdk() -> None:
    for source_file in BACKENDS_PACKAGE.glob("*.py"):
        imported = _imported_top_level_modules(source_file)
        offending = imported & FORBIDDEN_ENGINE_MODULES
        assert not offending, f"{source_file.name} imports forbidden engine SDK(s): {offending}"
