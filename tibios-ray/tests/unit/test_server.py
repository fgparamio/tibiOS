"""Tests for `tibios_ray.server` — the grpc-free process entry point.

`main()` composes `worker.build_runtime()` with `transport.serve()`; this
module imports zero `grpc`/`_pb2` symbol itself (design decision D13,
enforced recursively by `tests/unit/transport/test_transport_isolation.py`).
The real socket round trip belongs to `transport/server.py`'s own test and
`tests/integration/test_grpc_surface.py` — this test only proves the
composition and address selection, via a stub `transport.serve`.
"""

import asyncio

import tibios_ray.server as server_module
from tibios_ray.runtime.worker_runtime import WorkerRuntime


def test_main_serves_the_built_runtime_on_the_default_address(monkeypatch) -> None:
    calls: list[tuple[object, str]] = []

    async def fake_serve(runtime: object, address: str) -> None:
        calls.append((runtime, address))

    monkeypatch.setattr(server_module.transport, "serve", fake_serve)
    monkeypatch.delenv("TIBIOS_RAY_ADDRESS", raising=False)

    server_module.main()

    assert len(calls) == 1
    runtime, address = calls[0]
    assert isinstance(runtime, WorkerRuntime)
    assert address == server_module.DEFAULT_ADDRESS


def test_main_honours_the_address_environment_override(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_serve(runtime: object, address: str) -> None:
        calls.append(address)

    monkeypatch.setattr(server_module.transport, "serve", fake_serve)
    monkeypatch.setenv("TIBIOS_RAY_ADDRESS", "127.0.0.1:1234")

    server_module.main()

    assert calls == ["127.0.0.1:1234"]


def test_serve_coroutine_is_awaitable_without_asyncio_run(monkeypatch) -> None:
    # Sanity check that `_serve()` itself is a plain coroutine function usable
    # from `asyncio.run` — `main()`'s only job.
    async def fake_serve(runtime: object, address: str) -> None:
        return None

    monkeypatch.setattr(server_module.transport, "serve", fake_serve)
    asyncio.run(server_module._serve())
