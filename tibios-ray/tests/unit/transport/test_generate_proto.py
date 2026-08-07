"""Conformance guard for the `worker-grpc-transport` spec's Gotcha
"line-anchored import rewrite" (`design.md` "Gotchas `sdd-apply` Must
Know" and `scripts/generate_proto.py`'s own module docstring).

Loads `scripts/generate_proto.py` via `importlib.util.spec_from_file_location`
(same technique `test_proto_drift.py` and the isolation guard use) rather
than duplicating `_rewrite_imports`'s logic, and exercises it against a
small synthetic sample file — not the real generated tree — mixing a
real `from tibios.` import line with an embedded `b"...tibios.worker.v1..."`
bytes literal, the exact shape protoc emits in `worker_pb2.py`.

`_rewrite_imports` itself asserts `matched == rewritten` before writing
each file back out; a successful call below (no `AssertionError`) is
this test's proof that the invariant held against the fixture.
"""

import importlib.util
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
GENERATE_PROTO_SCRIPT = REPO_ROOT / "scripts" / "generate_proto.py"

#: Mirrors the real shape of a protoc-generated `_pb2.py`: a
#: package-absolute `from tibios.` import line protoc emits for a
#: cross-file dependency, and a `DESCRIPTOR = ...AddSerializedFile(b"...")`
#: line whose bytes literal embeds the same substring, `tibios.`, that the
#: import line starts with — the exact collision a global substitution
#: would corrupt (see `worker_pb2.py:25,29`).
_SAMPLE_PB2_SOURCE = (
    "from tibios.primitives.v1 import identity_pb2 as "
    "tibios_dot_primitives_dot_v1_dot_identity__pb2\n"
    "from google.protobuf import duration_pb2 as google_dot_protobuf_dot_duration__pb2\n"
    "\n"
    "DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile("
    "b'\\n\\x1dtibios/worker/v1/worker.proto\\x12\\x10tibios.worker.v1"
    "\\x1a#tibios/primitives/v1/identity.proto')\n"
)


def _load_generate_proto_module() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("generate_proto", GENERATE_PROTO_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rewrite_imports_only_touches_the_import_line(tmp_path: Path) -> None:
    sample = tmp_path / "sample_pb2.py"
    sample.write_text(_SAMPLE_PB2_SOURCE)

    module = _load_generate_proto_module()
    # A successful call proves `matched == rewritten` held for this fixture —
    # `_rewrite_imports` asserts that invariant itself before writing back out.
    module._rewrite_imports(tmp_path)

    rewritten_lines = sample.read_text().splitlines(keepends=True)

    assert rewritten_lines[0] == (
        "from tibios_ray.transport._generated.tibios.primitives.v1 import "
        "identity_pb2 as tibios_dot_primitives_dot_v1_dot_identity__pb2\n"
    )


def test_rewrite_imports_does_not_touch_non_import_lines(tmp_path: Path) -> None:
    sample = tmp_path / "sample_pb2.py"
    sample.write_text(_SAMPLE_PB2_SOURCE)
    original_lines = _SAMPLE_PB2_SOURCE.splitlines(keepends=True)

    module = _load_generate_proto_module()
    module._rewrite_imports(tmp_path)

    rewritten_lines = sample.read_text().splitlines(keepends=True)

    # The unrelated `from google.protobuf import ...` line (does not match
    # `^from tibios\.`) is untouched byte-for-byte.
    assert rewritten_lines[1] == original_lines[1]

    # The embedded `FileDescriptorProto` bytes literal — containing the
    # same `tibios.` substring the import-line rewrite matches on — is
    # untouched byte-for-byte. A global substitution would corrupt it.
    assert rewritten_lines[3] == original_lines[3]
    assert "tibios.worker.v1" in original_lines[3]
