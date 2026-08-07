"""Conformance guard for the `worker-grpc-transport` spec's Requirement
"Regenerating From ../proto Produces Byte-Identical Checked-In Code"
(`design.md` D11 "Drift guard").

Loads `scripts/generate_proto.py` via
`importlib.util.spec_from_file_location` rather than duplicating its
logic — the script is the single source of truth for both the CLI shim
and this test. Regenerates into `tmp_path`, then compares every
generated file against the checked-in tree byte for byte.

Skips with an explicit reason if `../proto` (the frozen cross-repo
contract) or `grpc_tools` is unavailable — this guard cannot run in an
environment missing either, and a skip is more honest than a false
green or a hard failure unrelated to drift.

Byte-identity is intentionally chosen over semantic descriptor
comparison here (design.md: "semantic comparison ... catches strictly
less ... its failure message tells you nothing actionable"). The
version-sensitivity that byte-identity trades away is covered instead by
the companion `test_descriptor_shape.py` guard.
"""

import filecmp
import importlib.util
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
GENERATE_PROTO_SCRIPT = REPO_ROOT / "scripts" / "generate_proto.py"
CHECKED_IN_GENERATED = REPO_ROOT / "src" / "tibios_ray" / "transport" / "_generated"


def _load_generate_proto_module() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("generate_proto", GENERATE_PROTO_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _grpc_tools_available() -> bool:
    return importlib.util.find_spec("grpc_tools") is not None


def _skip_reason() -> str | None:
    if not (REPO_ROOT.parent / "proto").is_dir():
        return "../proto is not available in this checkout — drift guard needs the frozen contract"
    if not _grpc_tools_available():
        return "grpc_tools is not installed — drift guard needs it to regenerate"
    return None


def _tracked_files(root: Path) -> set[Path]:
    """Every file under `root`, relative to it, excluding `__pycache__` —
    interpreter bytecode caches are a side effect of importing the
    package during test collection, not part of the checked-in tree."""
    return {
        p.relative_to(root)
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }


def test_checked_in_generated_tree_is_non_empty() -> None:
    # Guards against the comparison below being vacuously true because
    # nothing was ever checked in (the `test_backends_package_has_python_
    # source_files_to_check` precedent).
    generated_files = [
        p for p in _tracked_files(CHECKED_IN_GENERATED) if p.suffix in {".py", ".pyi"}
    ]
    assert len(generated_files) >= 8


def test_regenerating_from_proto_is_byte_identical_to_checked_in_tree(tmp_path: Path) -> None:
    skip_reason = _skip_reason()
    if skip_reason is not None:
        pytest.skip(skip_reason)

    module = _load_generate_proto_module()
    regenerated = tmp_path / "_generated"
    module.regenerate(regenerated)

    checked_in_files = _tracked_files(CHECKED_IN_GENERATED)
    regenerated_files = _tracked_files(regenerated)

    assert checked_in_files == regenerated_files, (
        "regenerated file set differs from the checked-in tree — "
        f"missing: {checked_in_files - regenerated_files}, "
        f"extra: {regenerated_files - checked_in_files}"
    )

    mismatches = [
        str(relative)
        for relative in sorted(checked_in_files)
        if not filecmp.cmp(
            CHECKED_IN_GENERATED / relative, regenerated / relative, shallow=False
        )
    ]
    assert not mismatches, (
        f"checked-in generated code has drifted from ../proto — re-run "
        f"`uv run python scripts/generate_proto.py` — mismatched files: {mismatches}"
    )
