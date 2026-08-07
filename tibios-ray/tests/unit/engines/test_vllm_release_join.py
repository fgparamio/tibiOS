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


async def _drain_background_tasks() -> None:
    # Flushes any tasks `_schedule_finalize` scheduled via
    # `loop.create_task` but that nothing else is awaiting — the
    # deterministic, zero-sleep way to give a *buggy* second finalize
    # task (were one scheduled) a chance to run before we inspect
    # `call_log`, without guessing how many `asyncio.sleep(0)` hops
    # it needs.
    current = asyncio.current_task()
    pending = [task for task in asyncio.all_tasks() if task is not current]
    if pending:
        await asyncio.wait(pending)


def test_release_then_close_of_abandoned_generator_does_not_double_abort() -> None:
    # verify-report WARNING #1 (2026-08-06): release() finalizing a
    # stranded entry.live stream, and the eventual GC/explicit-close of
    # the generate() generator it was stranded from, could each
    # independently call abort() — a double-abort race. The fix
    # (VL14) makes entry.live.pop() a single-owner claim ticket in
    # both release() and generate()'s own finally: whichever side pops
    # the request_id first is the only one that schedules a finalize.
    # This test reproduces the exact two-step sequence the fix
    # addresses: release() finalizes first, THEN the abandoned outer
    # generator is explicitly closed (standing in for its eventual
    # GC) — call_log must show exactly one "abort", never two.
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
        agen = cast("AsyncGenerator[TextChunk, None]", backend.generate(session, request))
        await agen.__anext__()  # stream left stranded mid-flight
        # release() finalizes the stranded stream — one abort, then
        # shutdown, exactly like test_release_join_orders_abort_before_shutdown.
        await asyncio.wait_for(backend.release(session), 2.0)
        # Now the abandoned outer generator is explicitly closed —
        # standing in for the GC path the bug report describes. Its
        # own finally must find entry.live already emptied by
        # release() above and must NOT schedule a second finalize.
        await agen.aclose()
        await _drain_background_tasks()
        return made[0].call_log

    call_log = asyncio.run(scenario())

    assert call_log == ["abort", "shutdown"]
    assert call_log.count("abort") == 1


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
