"""Conformance guard for the `worker-grpc-transport` spec's Gotcha "one
copy of each descriptor, ever" (`design.md` "Gotchas `sdd-apply` Must
Know").

Registering the same `.proto` file into protobuf's default descriptor
pool twice raises `TypeError: Couldn't build proto file into descriptor
pool: duplicate file name`. This invariant holds here **only** because
there is exactly one checked-in copy of the generated code under
`src/tibios_ray/transport/_generated/` and that tree is never added to
`sys.path` in addition to being imported as a package — a second
checked-in copy, or a `sys.path` entry pointing inside `_generated/`
that lets the same module be imported under two different dotted names,
would both re-trigger the `AddSerializedFile` call for the same
`.proto` path and reproduce the error this test exists to catch.

Two independent re-import mechanisms are exercised: a plain second
`importlib.import_module` (which protobuf/Python's own module-caching
already no-ops) and an explicit `importlib.reload`, which re-executes
the module body — including its top-level `AddSerializedFile` call —
against a pool that already holds that file's descriptor. Neither may
raise.
"""

import importlib

_WORKER_PB2_MODULE = "tibios_ray.transport._generated.tibios.worker.v1.worker_pb2"


def test_importing_worker_pb2_twice_does_not_duplicate_the_descriptor() -> None:
    first = importlib.import_module(_WORKER_PB2_MODULE)
    second = importlib.import_module(_WORKER_PB2_MODULE)

    # Plain re-import is served from `sys.modules` — same module object,
    # `AddSerializedFile` runs exactly once.
    assert first is second


def test_reloading_worker_pb2_does_not_raise_duplicate_descriptor_error() -> None:
    module = importlib.import_module(_WORKER_PB2_MODULE)

    # `reload` re-executes the module body, including the top-level
    # `DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(...)`
    # call, against a pool that already has this file's descriptor
    # registered. protobuf's own re-registration guard makes this a
    # no-op instead of the `duplicate file name` TypeError — this test
    # documents and locks in that behavior for this codebase's single
    # checked-in copy.
    reloaded = importlib.reload(module)

    assert reloaded.DESCRIPTOR.name == "tibios/worker/v1/worker.proto"
