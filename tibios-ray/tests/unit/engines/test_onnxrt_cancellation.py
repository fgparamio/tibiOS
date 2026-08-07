"""`onnxruntime-backend` spec, design decision OR11 — no cancellation
support. `asyncio.to_thread` cannot cancel a running thread: cancelling
the awaiting task lets `CancelledError` propagate immediately, but the
worker thread stays parked inside `run()` until the stub releases it,
runs to completion orphaned, and its result is simply discarded. The
session itself is never touched by cancellation (LC5's discipline: no
`finally` performs async work), so a fresh call on the same session
afterwards must still succeed.
"""

import asyncio
import threading

from stub_onnx import make_stub_session_factory, make_stub_tokenizer_factory

from tibios_ray.backends.adapter import BackendId
from tibios_ray.backends.embedding import Vector
from tibios_ray.engines.onnxrt import ONNXRUNTIME_BACKEND_ID, OnnxEmbeddingBackend


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


_PLAN = _Plan(ONNXRUNTIME_BACKEND_ID)


def test_cancellation_is_inert_and_the_session_remains_usable() -> None:
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

    async def scenario() -> list[Vector]:
        session = await backend.acquire(_PLAN)
        sessions[0].run_entered = entered
        sessions[0].run_block = block

        task = asyncio.create_task(backend.embed(session, ["hi"]))
        await asyncio.get_running_loop().run_in_executor(
            None, lambda: entered.wait(timeout=5.0)
        )
        task.cancel()

        raised: BaseException | None = None
        try:
            await task
        except asyncio.CancelledError as error:
            raised = error
        assert isinstance(raised, asyncio.CancelledError)

        # Release the orphaned worker thread — its (discarded) result
        # is never observed by this test, only that it does not corrupt
        # shared state.
        block.set()

        # A fresh call on the same, untouched session must still work.
        return list(await backend.embed(session, ["again"]))

    result = asyncio.run(scenario())

    assert result == [Vector(values=(0.1, 0.2))]
    assert len(sessions) == 1  # no rebuild: residency was never disturbed
