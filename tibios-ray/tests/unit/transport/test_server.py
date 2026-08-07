"""Tests for `tibios_ray.transport.server` — `serve()` (design decision
D12: the `grpc.aio.server()` is created and served on the event loop that
calls `serve()`; no cross-loop handoff).

The real client/server RPC round trip is `tests/integration/
test_grpc_surface.py`'s job — this module only proves `serve()` starts a
server on its caller's event loop and shuts down cleanly on cancellation.
"""

import asyncio

import pytest

from tibios_ray.capabilities.descriptor import CapabilityDescriptor, ModelFamily
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.runtime.registry import CapabilityRegistry
from tibios_ray.runtime.worker_runtime import WorkerRuntime
from tibios_ray.testing.provider import StubProvider
from tibios_ray.transport.server import serve


def _runtime() -> WorkerRuntime:
    provider = StubProvider(
        capability_descriptor=CapabilityDescriptor(
            capability=CapabilityName("chat.generate"),
            families=frozenset({ModelFamily("qwen")}),
        )
    )
    return WorkerRuntime(CapabilityRegistry([provider]))


def test_serve_starts_on_the_calling_event_loop_and_stops_on_cancellation() -> None:
    """4b.11 / D12: `serve()` builds and starts a `grpc.aio.server()` on
    the event loop that calls it — proven by driving it as a task on
    *this* loop and observing it still running (not raced ahead on some
    other loop) until cancelled, at which point it shuts down cleanly."""

    async def scenario() -> None:
        task = asyncio.ensure_future(serve(_runtime(), "127.0.0.1:0"))
        await asyncio.sleep(0.05)  # let start() complete and reach wait_for_termination()
        assert not task.done()

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
