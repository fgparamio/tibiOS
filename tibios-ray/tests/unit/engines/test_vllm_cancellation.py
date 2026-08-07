"""`vllm-text-backend` spec, Requirement "Uniform Cancellation Hides
Engine-Version Inconsistency" (design decisions VL11/VL12) —
abandonment or task cancellation of a `generate()` stream MUST issue
an explicit engine-level abort, scheduled from an await-free `finally`
(never a direct `await` there — that is LC5's failure mode with a
worse payload: a fresh `await` under task cancellation can be
re-cancelled immediately, silently skipping the abort). Clean
completion MUST NOT abort, but `stream.aclose()` still runs either way
— "always issue both, never rely on engine-side propagation" (VL12).
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


def _backend_with_paused_stub(
    pause_event: asyncio.Event,
) -> tuple[VllmTextBackend, list[StubAsyncLLM]]:
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
    return backend, made


def test_abandonment_via_aclose_triggers_abort_exactly_once_with_correct_request_id() -> None:
    pause_event = asyncio.Event()
    backend, made = _backend_with_paused_stub(pause_event)

    async def scenario() -> tuple[list[str], str]:
        session = await backend.acquire(_PLAN)
        request = TextRequest(prompt="hi", max_tokens=2)
        # `generate()`'s Protocol return type is the narrower
        # `AsyncIterator[TextChunk]` (no `aclose()`); `cast` expresses
        # that the concrete object is an async generator (LC11-pincer
        # precedent, test_llamacpp_abandonment.py).
        agen = cast("AsyncGenerator[TextChunk, None]", backend.generate(session, request))

        await agen.__anext__()  # consume chunk "a"; stub is now parked on chunk "b"
        await agen.aclose()

        await asyncio.wait_for(made[0].abort_called.wait(), 1.0)
        request_id = made[0].generate_calls[0]["request_id"]
        return made[0].abort_calls, request_id

    abort_calls, request_id = asyncio.run(scenario())
    assert abort_calls == [request_id]


def test_abort_survives_task_cancellation_mid_stream() -> None:
    pause_event = asyncio.Event()
    backend, made = _backend_with_paused_stub(pause_event)

    async def scenario() -> list[str]:
        session = await backend.acquire(_PLAN)
        request = TextRequest(prompt="hi", max_tokens=2)
        collected: list[str] = []

        async def consume() -> None:
            async for chunk in backend.generate(session, request):
                collected.append(chunk.text)

        task = asyncio.create_task(consume())
        await asyncio.wait_for(made[0].paused.wait(), 1.0)  # genuinely mid-stream
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # A direct `await` in generate()'s `finally` would be re-
        # cancelled here and never reach abort() — the scheduled-task
        # design (VL11) is what makes this assertion possible at all.
        await asyncio.wait_for(made[0].abort_called.wait(), 1.0)
        return made[0].abort_calls

    abort_calls = asyncio.run(scenario())
    assert len(abort_calls) == 1


def test_no_abort_on_clean_completion_but_close_still_runs() -> None:
    made: list[StubAsyncLLM] = []

    async def factory(model: str) -> StubAsyncLLM:
        stub = StubAsyncLLM(
            outputs=(StubRequestOutput(outputs=(StubCompletionOutput(text="a"),), finished=True),)
        )
        made.append(stub)
        return stub

    backend = VllmTextBackend(
        model="m", engine_factory=factory, sampling_params_factory=_no_op_params_factory
    )

    async def scenario() -> None:
        session = await backend.acquire(_PLAN)
        request = TextRequest(prompt="hi", max_tokens=1)
        async for _ in backend.generate(session, request):
            pass
        # Let the scheduled finalize task actually run before we assert.
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    asyncio.run(scenario())

    stub = made[0]
    assert stub.abort_calls == []
    request_id = stub.generate_calls[0]["request_id"]
    assert request_id in stub.closed_request_ids


def test_finalize_suppresses_abort_exceptions() -> None:
    # VL12: a failed cleanup must never surface as a Worker-visible
    # error. The stub's abort() raises; the background finalize task
    # must not propagate that into release()'s deterministic join.
    boom = RuntimeError("boom")
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
            abort_error=boom,
        )
        made.append(stub)
        return stub

    backend = VllmTextBackend(
        model="m", engine_factory=factory, sampling_params_factory=_no_op_params_factory
    )

    async def scenario() -> None:
        session = await backend.acquire(_PLAN)
        request = TextRequest(prompt="hi", max_tokens=2)
        agen = cast("AsyncGenerator[TextChunk, None]", backend.generate(session, request))
        await agen.__anext__()
        await agen.aclose()
        await asyncio.wait_for(made[0].abort_called.wait(), 1.0)
        # release() must complete cleanly despite abort() having raised
        # inside the scheduled finalize task.
        await asyncio.wait_for(backend.release(session), 2.0)

    asyncio.run(scenario())  # no exception propagates out of scenario()
    assert made[0].abort_calls == [made[0].generate_calls[0]["request_id"]]
