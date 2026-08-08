"""`tensorrt-llm-text-backend` spec, Requirement "Zero-Diff Integration —
No Backend-Specific Branching Outside Composition Root": `ChatProvider`
(`capabilities/chat.py`) and `PreferenceOrderPolicy`
(`selection/preference.py`) MUST require no code change to support
`tensorrt_llm` and MUST remain generic over `BackendId`. Neither module
may contain a conditional referencing `tensorrt_llm` or
`TensorrtLlmTextBackend` by name — `tensorrt_llm` may appear only as an
opaque `BackendId` value in configuration/composition code (e.g.
`chat.py`'s existing `CHAT_GENERATE_DESCRIPTOR.backends` catalog entry,
present before this change and untouched by it); the concrete class
name `TensorrtLlmTextBackend` must not appear in either module at all.

Static `ast` inspection, not a runtime one — mirrors
`test_no_quantization_reads.py`'s D23 guard and
`test_engines_layering.py`'s AST scan.
"""

import ast
from pathlib import Path

import tibios_ray

_SRC_ROOT = Path(tibios_ray.__file__).resolve().parent
_SCANNED_FILES = (
    _SRC_ROOT / "capabilities" / "chat.py",
    _SRC_ROOT / "selection" / "preference.py",
)
_FORBIDDEN_IN_CONDITIONALS = ("tensorrt_llm", "TensorrtLlmTextBackend")


def test_scanned_files_exist() -> None:
    # Guards against a silently-missing file making the next tests vacuous.
    for path in _SCANNED_FILES:
        assert path.is_file(), f"expected {path} to exist"


def test_neither_module_names_the_concrete_backend_class() -> None:
    # The concrete class itself must be namable nowhere but worker.py /
    # engines/__init__.py — not even in a comment, since that would
    # signal a coupling these two modules must never grow.
    offenders = {
        path.name: True
        for path in _SCANNED_FILES
        if "TensorrtLlmTextBackend" in path.read_text()
    }
    assert not offenders, f"named the concrete backend class: {offenders}"


def test_no_conditional_branches_on_tensorrt_llm_by_name() -> None:
    # `tensorrt_llm` as an opaque BackendId *value* (e.g. chat.py's
    # existing catalog entry) is fine anywhere; what must never exist is
    # a conditional (`if`/`match`) whose *test* expression references it
    # by name — that would be backend-specific branching.
    offenders: dict[str, int] = {}
    for path in _SCANNED_FILES:
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.If | ast.Match):
                continue
            test_expr = node.test if isinstance(node, ast.If) else node.subject
            condition_source = ast.dump(test_expr)
            if any(name in condition_source for name in _FORBIDDEN_IN_CONDITIONALS):
                offenders[path.name] = offenders.get(path.name, 0) + 1

    assert not offenders, (
        "capabilities/chat.py and selection/preference.py must stay "
        f"generic over BackendId — found backend-specific branching: {offenders}"
    )
