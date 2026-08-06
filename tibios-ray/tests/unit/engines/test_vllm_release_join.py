"""`vllm-text-backend` spec, design decisions VL13/VL14 — `release()` is
the deterministic join point for scheduled-but-not-yet-joined finalize
tasks (VL11's background tasks): a zero-refcount `release()` MUST wait
for every pending `abort()`/`aclose()` to complete before calling
`engine.shutdown()`, so shutdown never races a stream still being torn
down.
"""

import asyncio
from collections.abc import AsyncGenerator
from typing import cast

from stub_async_llm import StubAsyncLLM, StubCompletionOutput, StubRequestOutput

from tibios_ray.backends.adapter import BackendId
from tibios_ray.backends.text import TextChunk, TextRequest
from tibios_ray.engines.vllm import VllmTextBackend


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


_PLAN = _Plan(BackendId("vllm"))


def _no_op_params_factory(request: TextRequest) -> object:
    return object()


def test_release_join_orders_abort_before_shutdown() -> None:
    pause_event = asyncio.Event()
    made: list[StubAsyncLLM] = []

    async def factory(model: str) -> StubAsyncLLM:
        stub = StubAsyncLLM(
            outputs=(
                StubRequestOutput(outputs=(StubCompletionOutput(text="a"),), finished=False),
                StubRequestOutput(outputs=(StubCompletionOutput(text="b"),), finished=True),
            ),
            pause_before_index=1,
            pause_event=pause_event,
        )
        made.append(stub)
        return stub

    backend = VllmTextBackend(
        model="m", engine_factory=factory, sampling_params_factory=_no_op_params_factory
    )

    async def scenario() -> list[str]:
        session = await backend.acquire(_PLAN)
        request = TextRequest(prompt="hi", max_tokens=2)
        agen = backend.generate(session, request)
        await agen.__anext__()  # stream left stranded mid-flight, never closed by hand
        # `release()` itself must finalize the stranded stream and join
        # it before shutdown() runs — no manual aclose()/abort() here.
        await asyncio.wait_for(backend.release(session), 2.0)
        return made[0].call_log

    call_log = asyncio.run(scenario())

    assert call_log == ["abort", "shutdown"]


def test_release_join_waits_for_pending_even_without_a_live_stream_of_its_own() -> None:
    # A session with no in-flight generate() of its own still must not
    # tear down the shared engine while another session's finalize task
    # is still pending (VL13: pending belongs to the runtime, not the
    # session).
    pause_event = asyncio.Event()
    made: list[StubAsyncLLM] = []

    async def factory(model: str) -> StubAsyncLLM:
        stub = StubAsyncLLM(
            outputs=(
                StubRequestOutput(outputs=(StubCompletionOutput(text="a"),), finished=False),
                StubRequestOutput(outputs=(StubCompletionOutput(text="b"),), finished=True),
            ),
            pause_before_index=1,
            pause_event=pause_event,
        )
        made.append(stub)
        return stub

    backend = VllmTextBackend(
        model="m", engine_factory=factory, sampling_params_factory=_no_op_params_factory
    )

    async def scenario() -> list[str]:
        session_a = await backend.acquire(_PLAN)
        session_b = await backend.acquire(_PLAN)  # same engine, refcount 2

        request = TextRequest(prompt="hi", max_tokens=2)
        agen = cast("AsyncGenerator[TextChunk, None]", backend.generate(session_a, request))
        await agen.__anext__()
        await agen.aclose()  # schedules a's finalize task, refcount still 2

        await asyncio.wait_for(made[0].abort_called.wait(), 1.0)
        await backend.release(session_a)  # refcount -> 1, no teardown yet
        await asyncio.wait_for(backend.release(session_b), 2.0)  # refcount -> 0, joins + shuts down
        return made[0].call_log

    call_log = asyncio.run(scenario())

    assert call_log == ["abort", "shutdown"]
