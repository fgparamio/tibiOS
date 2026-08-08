"""`tensorrt-llm-text-backend` spec, Requirement "Uniform Cancellation on
Every Exit Path" (design decision D36) — abandoning or cancelling a
`generate()` stream MUST issue an explicit `handle.abort()` from an
await-free `finally` (never a direct `await` there — a fresh `await`
under task cancellation can be re-cancelled immediately, silently
skipping the abort), on `aclose()`, an early `break`-then-close, and
task cancellation alike. Clean completion (full exhaustion) must NOT
call `abort()` — there is no `aclose()` counterpart on the handle to
call either way (unlike `vllm.py`'s separate `stream.aclose()`), so
nothing needs finalizing once the SDK itself reports `finished=True`.

Mirrors `test_vllm_cancellation.py`, minus the always-call-`aclose()`
half VL12 required there — D36 explicitly has no equivalent here.
"""

import asyncio
from collections.abc import AsyncGenerator
from typing import cast

from stub_trtllm import StubLLM, StubRequestOutput

from tibios_ray.backends.adapter import BackendId
from tibios_ray.backends.text import TextChunk, TextRequest
from tibios_ray.engines.tensorrt import TensorrtLlmTextBackend


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


_PLAN = _Plan(BackendId("tensorrt_llm"))


def _no_op_params_factory(request: TextRequest) -> object:
    return object()


def _backend_with_stub(
    output: StubRequestOutput,
) -> tuple[TensorrtLlmTextBackend, list[StubLLM]]:
    made: list[StubLLM] = []

    async def factory(engine_path: str) -> StubLLM:
        stub = StubLLM(model=engine_path)
        stub.queue_output(output)
        made.append(stub)
        return stub

    backend = TensorrtLlmTextBackend(
        engine_path="/engines/m",
        engine_factory=factory,
        sampling_params_factory=_no_op_params_factory,
    )
    return backend, made


def test_abandonment_via_aclose_triggers_abort_exactly_once() -> None:
    pause_event = asyncio.Event()
    handle = StubRequestOutput(diffs=("a", "b"), pause_before_index=1, pause_event=pause_event)
    backend, _ = _backend_with_stub(handle)

    async def scenario() -> None:
        session = await backend.acquire(_PLAN)
        request = TextRequest(prompt="hi", max_tokens=2)
        # `generate()`'s Protocol return type is the narrower
        # `AsyncIterator[TextChunk]` (no `aclose()`); `cast` expresses
        # that the concrete object is an async generator (LC11-pincer
        # precedent, `test_llamacpp_abandonment.py`).
        agen = cast("AsyncGenerator[TextChunk, None]", backend.generate(session, request))

        await agen.__anext__()  # consume chunk "a"; handle is now parked before "b"
        await agen.aclose()

        await asyncio.wait_for(handle.abort_called.wait(), 1.0)

    asyncio.run(scenario())
    assert handle.abort_calls == 1


def test_abort_survives_task_cancellation_mid_stream() -> None:
    pause_event = asyncio.Event()
    handle = StubRequestOutput(diffs=("a", "b"), pause_before_index=1, pause_event=pause_event)
    backend, _ = _backend_with_stub(handle)

    async def scenario() -> None:
        session = await backend.acquire(_PLAN)
        request = TextRequest(prompt="hi", max_tokens=2)
        collected: list[str] = []

        async def consume() -> None:
            async for chunk in backend.generate(session, request):
                collected.append(chunk.text)

        task = asyncio.create_task(consume())
        await asyncio.wait_for(handle.paused.wait(), 1.0)  # genuinely mid-stream
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        # A direct `await` in generate()'s `finally` would be re-
        # cancelled here and never reach abort() — the scheduled-task
        # design (D36/VL11 inherited) is what makes this assertion
        # possible at all.
        await asyncio.wait_for(handle.abort_called.wait(), 1.0)

    asyncio.run(scenario())
    assert handle.abort_calls == 1


def test_break_then_close_triggers_abort_exactly_once() -> None:
    # A bare `break` does not deterministically unwind a CPython async
    # generator; an explicit `aclose()` after the loop is what actually
    # exercises `generate()`'s own `finally` here — a second
    # abandonment shape distinct from cancelling a running task.
    pause_event = asyncio.Event()
    handle = StubRequestOutput(diffs=("a", "b"), pause_before_index=1, pause_event=pause_event)
    backend, _ = _backend_with_stub(handle)

    async def scenario() -> list[TextChunk]:
        session = await backend.acquire(_PLAN)
        request = TextRequest(prompt="hi", max_tokens=2)
        agen = cast("AsyncGenerator[TextChunk, None]", backend.generate(session, request))

        collected: list[TextChunk] = []
        async for chunk in agen:
            collected.append(chunk)
            break  # abandon after exactly one chunk, handle parked before "b"
        await agen.aclose()

        await asyncio.wait_for(handle.abort_called.wait(), 1.0)
        return collected

    collected = asyncio.run(scenario())
    assert collected == [TextChunk(text="a", finished=False)]
    assert handle.abort_calls == 1


def test_no_abort_on_clean_completion() -> None:
    handle = StubRequestOutput(diffs=("a",))
    backend, _ = _backend_with_stub(handle)

    async def scenario() -> None:
        session = await backend.acquire(_PLAN)
        request = TextRequest(prompt="hi", max_tokens=1)
        async for _ in backend.generate(session, request):
            pass
        # Let any (incorrectly) scheduled finalize task actually run
        # before asserting.
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    asyncio.run(scenario())
    assert handle.abort_calls == 0


def test_finalize_suppresses_abort_exceptions() -> None:
    # D36's suppress(Exception), VL12's principle inherited: a failed
    # cleanup must never surface as a Worker-visible error.
    boom = RuntimeError("boom")
    pause_event = asyncio.Event()
    handle = StubRequestOutput(
        diffs=("a", "b"), pause_before_index=1, pause_event=pause_event, abort_error=boom
    )
    backend, _ = _backend_with_stub(handle)

    async def scenario() -> None:
        session = await backend.acquire(_PLAN)
        request = TextRequest(prompt="hi", max_tokens=2)
        agen = cast("AsyncGenerator[TextChunk, None]", backend.generate(session, request))
        await agen.__anext__()
        await agen.aclose()
        await asyncio.wait_for(handle.abort_called.wait(), 1.0)
        # release() must complete cleanly despite abort() having raised
        # inside the scheduled finalize task.
        await asyncio.wait_for(backend.release(session), 2.0)

    asyncio.run(scenario())  # no exception propagates out of scenario()
    assert handle.abort_calls == 1


def test_release_finalizes_a_stranded_stream_and_generate_does_not_double_abort() -> None:
    # VL13/VL14 inherited: release() must finalize any of *this
    # session's* streams never drained to completion, and the eventual
    # `aclose()` of that same abandoned generator must find the entry
    # already claimed and must not schedule a second finalize.
    pause_event = asyncio.Event()
    handle = StubRequestOutput(diffs=("a", "b"), pause_before_index=1, pause_event=pause_event)
    backend, made = _backend_with_stub(handle)

    async def scenario() -> None:
        session = await backend.acquire(_PLAN)
        request = TextRequest(prompt="hi", max_tokens=2)
        agen = cast("AsyncGenerator[TextChunk, None]", backend.generate(session, request))
        await agen.__anext__()  # stream left stranded mid-flight, never closed by hand

        # release() itself must finalize the stranded stream and join
        # it before shutdown() runs — no manual aclose()/abort() here.
        await asyncio.wait_for(backend.release(session), 2.0)
        assert made[0].shutdown_calls == 1
        assert handle.abort_calls == 1

        # Standing in for the eventual GC of the abandoned generator —
        # must find `entry.live` already emptied by release() above and
        # must NOT schedule a second finalize.
        await agen.aclose()
        await _drain_background_tasks()

    asyncio.run(scenario())
    assert handle.abort_calls == 1


async def _drain_background_tasks() -> None:
    # Flushes any tasks `_schedule_finalize` scheduled via
    # `loop.create_task` but that nothing else is awaiting — the
    # deterministic, zero-sleep way to give a *buggy* second finalize
    # task (were one scheduled) a chance to run before assertions run.
    current = asyncio.current_task()
    pending = [task for task in asyncio.all_tasks() if task is not current]
    if pending:
        await asyncio.wait(pending)
