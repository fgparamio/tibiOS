"""`vllm-text-backend` spec (design decision VL13) — the teardown-vs-
acquire race. `release()` of the last session and a concurrent
`acquire()` share the same lock and teardown does not release it
before clearing the slot, so there is no interleaving in which a
session borrows an engine that is being shut down: the concurrent
`acquire()` either completes entirely before the decrement (no
teardown) or entirely after the slot is cleared (fresh engine).

Falls out of tasks 1.6-1.8's shared lock — no new production code
(design.md "Slice Plan"). The stub's `shutdown()` blocks on a
`threading.Event`, proving the ordering structurally rather than by
timing.
"""

import asyncio
import threading

from stub_async_llm import StubAsyncLLM

from tibios_ray.backends.adapter import BackendId
from tibios_ray.engines.vllm import VllmTextBackend


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


_PLAN = _Plan(BackendId("vllm"))


def test_concurrent_release_last_and_acquire_are_strictly_ordered() -> None:
    shutdown_block = threading.Event()
    shutdown_started = threading.Event()
    made: list[StubAsyncLLM] = []

    async def factory(model: str) -> StubAsyncLLM:
        stub = StubAsyncLLM(
            shutdown_block_event=shutdown_block, shutdown_started_event=shutdown_started
        )
        made.append(stub)
        return stub

    backend = VllmTextBackend(model="m", engine_factory=factory)

    async def scenario() -> None:
        session = await backend.acquire(_PLAN)  # sole session -> release will teardown
        assert len(made) == 1

        release_task = asyncio.create_task(backend.release(session))
        # Wait until the stub's shutdown() is actually running (parked on
        # shutdown_block) before starting the concurrent acquire() —
        # proves acquire() genuinely contends with an in-flight teardown,
        # not a not-yet-started one.
        await asyncio.to_thread(shutdown_started.wait, 5.0)
        assert not release_task.done()  # still parked inside shutdown()

        acquire_task = asyncio.create_task(backend.acquire(_PLAN))
        # Give acquire() a chance to run; if it raced past the lock it
        # would now have constructed a second engine even though the
        # first shutdown has not returned.
        await asyncio.sleep(0)
        assert len(made) == 1  # acquire() is blocked behind release()'s lock

        shutdown_block.set()  # let the first shutdown() return
        await asyncio.wait_for(release_task, timeout=5.0)
        await asyncio.wait_for(acquire_task, timeout=5.0)

        assert made[0].shutdown_calls == 1
        assert len(made) == 2
        assert made[1] is not made[0]  # the new session is not the shut-down engine

    asyncio.run(scenario())
