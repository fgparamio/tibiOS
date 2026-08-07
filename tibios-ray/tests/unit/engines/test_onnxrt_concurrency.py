"""`onnxruntime-backend` spec, Requirement "Residency Lifecycle Governs
Model Access Through Acquire and Release", Scenario "Concurrent acquires
for the same model all succeed" (design decision OR2, VL6 inherited) —
concurrent first `acquire()` calls must build exactly one session,
never two.

Barrier-based, not sleep-based (design.md "Testing Strategy"): the
injected `session_factory` — a plain **synchronous** callable, unlike
vLLM's async engine factory — parks on a `threading.Event` that the
test only sets after both `acquire()` coroutines are provably in
flight, so a missing lock would deterministically build two sessions,
not just "usually" one. `threading.Event`, not `asyncio.Event`: the
factory runs off the loop via `asyncio.to_thread` (design.md "Key
Contracts"), the exact mechanism `test_vllm_concurrency.py`'s async
factory does not need.
"""

import asyncio
import threading

from stub_onnx import StubInferenceSession, StubTokenizer

from tibios_ray.backends.adapter import BackendId
from tibios_ray.engines.onnxrt import ONNXRUNTIME_BACKEND_ID, OnnxEmbeddingBackend


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


_PLAN = _Plan(ONNXRUNTIME_BACKEND_ID)


def test_concurrent_first_acquires_build_exactly_one_session() -> None:
    made: list[StubInferenceSession] = []
    entered = threading.Event()
    release = threading.Event()
    enter_count = 0
    enter_lock = threading.Lock()

    def session_factory(model_path: str, providers: object) -> StubInferenceSession:
        nonlocal enter_count
        with enter_lock:
            enter_count += 1
            first = enter_count == 1
        if first:
            # First caller in signals it is inside the factory, then
            # parks on a real OS thread (this runs under
            # `asyncio.to_thread`) until the test releases it — giving
            # a concurrent second `acquire()` a chance to run and prove
            # it does NOT also reach the factory while the first is
            # still in flight.
            entered.set()
            release.wait(timeout=5.0)
        session = StubInferenceSession()
        made.append(session)
        return session

    def tokenizer_factory(tokenizer_path: str) -> StubTokenizer:
        return StubTokenizer()

    backend = OnnxEmbeddingBackend(
        model_path="model.onnx",
        tokenizer_path="tok",
        session_factory=session_factory,
        tokenizer_factory=tokenizer_factory,
    )

    async def scenario() -> tuple[str, str]:
        first_task = asyncio.create_task(backend.acquire(_PLAN))
        second_task = asyncio.create_task(backend.acquire(_PLAN))

        await asyncio.get_running_loop().run_in_executor(
            None, lambda: entered.wait(timeout=5.0)
        )
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
