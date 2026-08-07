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

PR 2 adds the execution-side proofs (OR3/OR7): unlike `acquire()`,
`_infer()`'s `session.run()` call is made with **no lock held at all**
(design decision OR3, the inversion of `test_llamacpp_concurrency.py`'s
per-session lock) — two concurrent `embed()` calls sharing one
residency's session must both be inside `run()` simultaneously, and
the call must genuinely run off the event loop (OR7).
"""

import asyncio
import threading

from stub_onnx import (
    StubInferenceSession,
    StubTokenizer,
    make_stub_session_factory,
    make_stub_tokenizer_factory,
)

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


def test_concurrent_run_on_one_shared_session_both_enter_before_either_exits() -> None:
    # OR2's shared residency means two `acquire()`s on one Backend both
    # point at the SAME `StubInferenceSession` — this is deliberately
    # "two sessions from one Backend" (design.md "Testing Strategy"),
    # not two independent sessions. A `threading.Barrier(2)` proves
    # *mutual* concurrent entry: a lock anywhere on the `_infer()` path
    # (OR3 says there must be none) makes the second `run()` call wait
    # for the first to finish, which never reaches the barrier's second
    # party, so `barrier.wait()` times out and raises.
    session_factory, sessions = make_stub_session_factory(
        input_names=("input_ids",), outputs=[[[0.1, 0.2]]]
    )
    tokenizer_factory, _ = make_stub_tokenizer_factory(encoded={"input_ids": [[1]]})
    backend = OnnxEmbeddingBackend(
        model_path="model.onnx",
        tokenizer_path="tok",
        session_factory=session_factory,
        tokenizer_factory=tokenizer_factory,
    )

    async def scenario() -> None:
        session_a = await backend.acquire(_PLAN)
        session_b = await backend.acquire(_PLAN)
        assert len(sessions) == 1  # shared residency: one underlying session

        sessions[0].run_barrier = threading.Barrier(2, timeout=5.0)

        await asyncio.wait_for(
            asyncio.gather(
                backend.embed(session_a, ["a"]),
                backend.embed(session_b, ["b"]),
            ),
            timeout=5.0,
        )

    asyncio.run(scenario())  # a lock on the path would time out the barrier

    assert len(sessions[0].run_calls) == 2


def test_run_does_not_block_the_event_loop() -> None:
    # OR7: while the worker thread is parked inside `run()`, the loop
    # must keep advancing other coroutines — proved deterministically
    # by counting `asyncio.sleep(0)` yields while `run()` is known to
    # be blocked (via `run_entered`), never by a timed sleep.
    entered = threading.Event()
    block = threading.Event()
    session_factory, sessions = make_stub_session_factory(
        input_names=("input_ids",), outputs=[[[0.1, 0.2]]]
    )
    tokenizer_factory, _ = make_stub_tokenizer_factory(encoded={"input_ids": [[1]]})
    backend = OnnxEmbeddingBackend(
        model_path="model.onnx",
        tokenizer_path="tok",
        session_factory=session_factory,
        tokenizer_factory=tokenizer_factory,
    )

    async def scenario() -> tuple[int, int]:
        session = await backend.acquire(_PLAN)
        sessions[0].run_entered = entered
        sessions[0].run_block = block

        task = asyncio.create_task(backend.embed(session, ["hi"]))

        await asyncio.get_running_loop().run_in_executor(
            None, lambda: entered.wait(timeout=5.0)
        )
        counter = 0
        for _ in range(50):
            await asyncio.sleep(0)
            counter += 1
        assert not task.done()  # run() is still parked on `block`

        block.set()
        result = await asyncio.wait_for(task, timeout=5.0)
        return counter, len(result)

    counter, result_len = asyncio.run(scenario())

    assert counter == 50
    assert result_len == 1
