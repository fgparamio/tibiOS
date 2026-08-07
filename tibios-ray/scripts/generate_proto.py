"""Regenerates the checked-in gRPC/protobuf code under
`src/tibios_ray/transport/_generated/` from the frozen `../proto/`
contract (`design.md` D11 — "Codegen mechanics").

Usage: `uv run python scripts/generate_proto.py`

This is a plain module, deliberately **not** a `[project.scripts]`
entry: `uv_build` exposes no build-hook API, and a console-script entry
would ship a dev-only tool inside the installed wheel. `regenerate()` is
the single source of truth both this CLI shim and
`tests/unit/transport/test_proto_drift.py` call — the test loads this
file via `importlib.util.spec_from_file_location` rather than
duplicating the logic.

Two gotchas load-bearing enough to repeat here (full rationale in
`design.md` "Gotchas `sdd-apply` Must Know"):

- The import rewrite below is **line-anchored** (`^from tibios\\.`
  only). `_pb2.py` embeds a serialized `FileDescriptorProto` as a bytes
  literal containing the string `tibios.worker.v1`; a global
  `tibios.` -> `...` substitution would corrupt that literal and fail
  at import time with an opaque descriptor-pool error.
- protoc emits **no** `__init__.py` anywhere in the output tree. Every
  directory level, including the `_generated/` root itself, gets one
  written here, deterministically, so it is part of the byte-identity
  drift comparison.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROTO_ROOT = REPO_ROOT.parent / "proto"

#: Package path the rewritten imports resolve against, no matter where
#: `regenerate()` is asked to write its output (a real checkout or a
#: `tmp_path` in the drift-guard test) — the import string that ships in
#: the checked-in tree is what must be byte-identical, and that string
#: names the *production* location, not the temp directory.
GENERATED_IMPORT_ROOT = "tibios_ray.transport._generated"

#: Every `.proto` file this repo consumes, relative to `PROTO_ROOT`.
#: `identity.proto` first: `worker.proto` imports it, but protoc does not
#: require a particular invocation order — listed in dependency order
#: for readability, not correctness.
PROTO_FILES = (
    "tibios/primitives/v1/identity.proto",
    "tibios/worker/v1/worker.proto",
)

_IMPORT_LINE = re.compile(r"^from tibios\.")
_GENERATED_FILE_GLOBS = ("*_pb2.py", "*_pb2.pyi", "*_pb2_grpc.py")


def regenerate(into: Path) -> None:
    """Runs protoc (via `grpc_tools`) against `PROTO_ROOT`, rewrites the
    package-absolute `tibios.` imports protoc emits so they resolve
    under `into`'s installed location, and writes deterministic
    `__init__.py` files at every directory level. `into` is fully wiped
    and recreated first, so a file renamed or removed in `../proto`
    cannot survive as a stale leftover.
    """
    import grpc_tools
    from grpc_tools import protoc

    if into.exists():
        shutil.rmtree(into)
    into.mkdir(parents=True)

    # `well_known_types_proto_path`: grpc_tools ships google/protobuf/*.proto
    # (duration.proto, etc.) bundled inside its own package data, since
    # protoc itself does not — worker.proto imports duration.proto, so this
    # second --proto_path is required, not optional.
    well_known_types_proto_path = Path(grpc_tools.__file__).resolve().parent / "_proto"

    proto_files = [str(PROTO_ROOT / rel) for rel in PROTO_FILES]
    args = [
        "protoc",
        f"--proto_path={PROTO_ROOT}",
        f"--proto_path={well_known_types_proto_path}",
        f"--python_out={into}",
        f"--pyi_out={into}",
        f"--grpc_python_out={into}",
        *proto_files,
    ]
    exit_code = protoc.main(args)
    if exit_code != 0:
        raise RuntimeError(f"protoc failed with exit code {exit_code}: {args}")

    _rewrite_imports(into)
    _write_init_files(into)


def _rewrite_imports(root: Path) -> None:
    """Rewrites only lines matching `^from tibios\\.` in every generated
    file, prefixing them to `from {GENERATED_IMPORT_ROOT}.tibios.`. Any
    other occurrence of `tibios.` on the line — including inside the
    serialized descriptor bytes literal — is left untouched."""
    for pattern in _GENERATED_FILE_GLOBS:
        for path in root.rglob(pattern):
            lines = path.read_text().splitlines(keepends=True)
            matched = 0
            rewritten = 0
            new_lines: list[str] = []
            for line in lines:
                if _IMPORT_LINE.match(line):
                    matched += 1
                    new_line = _IMPORT_LINE.sub(f"from {GENERATED_IMPORT_ROOT}.tibios.", line)
                    if new_line != line:
                        rewritten += 1
                    line = new_line
                new_lines.append(line)
            assert matched == rewritten, (
                f"{path}: import rewrite matched {matched} lines but changed {rewritten}"
            )
            path.write_text("".join(new_lines))


def _write_init_files(root: Path) -> None:
    """protoc emits no `__init__.py`; every directory level under (and
    including) `root` needs one, written deterministically so it
    participates in the byte-identity drift comparison."""
    directories = {root} | {p for p in root.rglob("*") if p.is_dir()}
    for directory in directories:
        (directory / "__init__.py").write_text("")


if __name__ == "__main__":
    target = REPO_ROOT / "src" / "tibios_ray" / "transport" / "_generated"
    regenerate(target)
    print(f"Regenerated {target}")
