"""`vllm-text-backend` spec, Requirement "Single-Flight Construction
Prevents Duplicate Engines" (design decision VL6) — the highest-severity
risk in the proposal: concurrent first `acquire()` calls must build
exactly one engine, never two (double VRAM).

Barrier-based, not sleep-based (design.md "Testing Strategy"): the
injected factory awaits an `asyncio.Event` set by a third task only
after both `acquire()` coroutines are provably in flight simultaneously
— so a missing lock would deterministically construct two engines,
not just "usually" one.
"""

import asyncio

from stub_async_llm import StubAsyncLLM

from tibios_ray.backends.adapter import BackendId
from tibios_ray.engines.vllm import VllmTextBackend


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


_PLAN = _Plan(BackendId("vllm"))


def test_concurrent_first_acquires_build_exactly_one_engine() -> None:
    made: list[StubAsyncLLM] = []
    entered = asyncio.Event()
    release = asyncio.Event()
    enter_count = 0

    async def factory(model: str) -> StubAsyncLLM:
        nonlocal enter_count
        enter_count += 1
        if enter_count == 1:
            # First caller in signals it is inside the factory, then
            # waits for the test to release it — giving the second
            # `acquire()` a chance to run and prove it does NOT also
            # reach the factory while the first is in flight.
            entered.set()
            await release.wait()
        stub = StubAsyncLLM()
        made.append(stub)
        return stub

    backend = VllmTextBackend(model="m", engine_factory=factory)

    async def scenario() -> tuple[str, str]:
        first_task = asyncio.create_task(backend.acquire(_PLAN))
        second_task = asyncio.create_task(backend.acquire(_PLAN))

        await asyncio.wait_for(entered.wait(), timeout=5.0)
        # Give the second acquire() a chance to run; if it were not
        # serialized by the lock it would now also be inside the
        # factory, incrementing enter_count to 2 before release fires.
        await asyncio.sleep(0)
        assert enter_count == 1

        release.set()
        first, second = await asyncio.wait_for(
            asyncio.gather(first_task, second_task), timeout=5.0
        )
        return first.session_id, second.session_id

    first_id, second_id = asyncio.run(scenario())

    assert first_id != second_id
    assert enter_count == 1
    assert len(made) == 1
