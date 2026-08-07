"""Tests for `tibios_ray.worker` — the composition root.

`build_runtime()` is the single place that wires all seven Capability
Providers into one `CapabilityRegistry` and hands it to one
`WorkerRuntime`; `transport/server.py`'s `serve()` calls it, never the
other way around (design decision D13: `worker.py` imports zero `grpc`/
`_pb2` symbol — `tests/unit/transport/test_transport_isolation.py`
enforces that recursively).
"""

from tibios_ray.runtime.worker_runtime import WorkerRuntime
from tibios_ray.worker import build_runtime


def test_build_runtime_returns_a_worker_runtime() -> None:
    runtime = build_runtime()
    assert isinstance(runtime, WorkerRuntime)


def test_build_runtime_is_callable_repeatedly_with_independent_registries() -> None:
    # No shared mutable state across composition roots (D6: immutable,
    # ctor-built registry — no global singleton).
    assert build_runtime() is not build_runtime()
