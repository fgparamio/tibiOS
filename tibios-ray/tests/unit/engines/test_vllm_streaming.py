"""`vllm-text-backend` spec, Requirements "Native-Async Streaming, No
Thread Bridge" and "Streaming Output Is Transport-Agnostic" (design
decisions VL5/VL10) — `generate()` consumes the engine's `AsyncGenerator`
directly, with no pump thread, bounded queue, or polling loop bridging
it to the event loop (the exact opposite of `llamacpp-text-backend`'s
`test_llamacpp_streaming.py`, which exists *because* llama.cpp is
blocking). `finished` is sourced straight from `output.finished` — no
one-token lookahead (LC8 is not inherited, VL10).

Tests inject their own `sampling_params_factory` so none of this
depends on `default_sampling_params_factory` (task 2.3, tested
separately in `test_vllm_sampling_params.py`).
"""

import asyncio

from stub_async_llm import (
    StubAsyncLLM,
    StubCompletionOutput,
    StubRequestOutput,
    make_stub_engine_factory,
)

from tibios_ray.backends.adapter import BackendId, BackendSession
from tibios_ray.backends.text import TextChunk, TextRequest
from tibios_ray.engines.vllm import VllmTextBackend


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


_PLAN = _Plan(BackendId("vllm"))


def _no_op_params_factory(request: TextRequest) -> object:
    return object()


def _backend_with_stub(
    outputs: tuple[StubRequestOutput, ...] = (),
) -> tuple[VllmTextBackend, list[StubAsyncLLM]]:
    made: list[StubAsyncLLM] = []

    async def factory(model: str) -> StubAsyncLLM:
        stub = StubAsyncLLM(outputs=outputs)
        made.append(stub)
        return stub

    backend = VllmTextBackend(
        model="m", engine_factory=factory, sampling_params_factory=_no_op_params_factory
    )
    return backend, made


async def _drain(
    backend: VllmTextBackend, session: BackendSession, request: TextRequest
) -> list[TextChunk]:
    return [chunk async for chunk in backend.generate(session, request)]


def test_generate_streams_stub_outputs_in_production_order() -> None:
    outputs = (
        StubRequestOutput(outputs=(_completion("a"),), finished=False),
        StubRequestOutput(outputs=(_completion("b"),), finished=False),
        StubRequestOutput(outputs=(_completion("c"),), finished=True),
    )
    backend, _ = _backend_with_stub(outputs)

    async def scenario() -> list[TextChunk]:
        session = await backend.acquire(_PLAN)
        return await _drain(backend, session, TextRequest(prompt="hi", max_tokens=3))

    chunks = asyncio.run(scenario())
    assert chunks == [
        TextChunk(text="a", finished=False),
        TextChunk(text="b", finished=False),
        TextChunk(text="c", finished=True),
    ]


def test_generate_call_path_has_no_thread_or_queue_or_polling() -> None:
    # Static proof, not a runtime one: `generate()`'s source must not
    # reference any thread-bridge machinery — this is the mechanical
    # check that VL5's inversion (no lock, no bridge) actually landed,
    # not just "happened to work" on this stub.
    import inspect

    from tibios_ray.engines.vllm import VllmTextBackend as _Backend

    source = inspect.getsource(_Backend.generate)
    for forbidden in ("Thread", "asyncio.Queue", "while True", "poll"):
        assert forbidden not in source, f"{forbidden!r} found in generate() source"


def test_generate_takes_no_lock() -> None:
    outputs = (StubRequestOutput(outputs=(_completion("only"),), finished=True),)
    backend, made = _backend_with_stub(outputs)

    async def scenario() -> tuple[list[TextChunk], list[TextChunk]]:
        session_a = await backend.acquire(_PLAN)
        session_b = await backend.acquire(_PLAN)
        # Two concurrent generate() calls on two sessions sharing one
        # engine — if generate() held a residency-scoped lock this
        # would deadlock or serialize; asyncio.gather proves neither.
        chunks_a, chunks_b = await asyncio.wait_for(
            asyncio.gather(
                _drain(backend, session_a, TextRequest(prompt="a", max_tokens=1)),
                _drain(backend, session_b, TextRequest(prompt="b", max_tokens=1)),
            ),
            timeout=2.0,
        )
        return chunks_a, chunks_b

    chunks_a, chunks_b = asyncio.run(scenario())
    assert chunks_a == [TextChunk(text="only", finished=True)]
    assert chunks_b == [TextChunk(text="only", finished=True)]
    assert len(made) == 1  # one shared engine


def test_terminal_semantics_multi_output_exactly_one_trailing_finished() -> None:
    outputs = (
        StubRequestOutput(outputs=(_completion("a"),), finished=False),
        StubRequestOutput(outputs=(_completion("b"),), finished=False),
        StubRequestOutput(outputs=(_completion("c"),), finished=True),
    )
    backend, _ = _backend_with_stub(outputs)

    async def scenario() -> list[TextChunk]:
        session = await backend.acquire(_PLAN)
        return await _drain(backend, session, TextRequest(prompt="hi", max_tokens=3))

    chunks = asyncio.run(scenario())
    assert [c.finished for c in chunks] == [False, False, True]
    assert chunks[-1].finished is True


def test_terminal_semantics_single_finished_output() -> None:
    outputs = (StubRequestOutput(outputs=(_completion("only"),), finished=True),)
    backend, _ = _backend_with_stub(outputs)

    async def scenario() -> list[TextChunk]:
        session = await backend.acquire(_PLAN)
        return await _drain(backend, session, TextRequest(prompt="hi", max_tokens=1))

    chunks = asyncio.run(scenario())
    assert chunks == [TextChunk(text="only", finished=True)]


def test_terminal_semantics_exhaustion_without_finished_synthesizes_terminator() -> None:
    # VL10's defensive rule: a stub that never sets finished=True still
    # produces exactly one synthetic TextChunk("", finished=True).
    outputs = (StubRequestOutput(outputs=(_completion("a"),), finished=False),)
    backend, _ = _backend_with_stub(outputs)

    async def scenario() -> list[TextChunk]:
        session = await backend.acquire(_PLAN)
        return await _drain(backend, session, TextRequest(prompt="hi", max_tokens=1))

    chunks = asyncio.run(scenario())
    assert chunks == [
        TextChunk(text="a", finished=False),
        TextChunk(text="", finished=True),
    ]


def test_terminal_semantics_drops_empty_non_terminal_delta() -> None:
    outputs = (
        StubRequestOutput(outputs=(_completion("a"),), finished=False),
        StubRequestOutput(outputs=(_completion(""),), finished=False),
        StubRequestOutput(outputs=(_completion("b"),), finished=True),
    )
    backend, _ = _backend_with_stub(outputs)

    async def scenario() -> list[TextChunk]:
        session = await backend.acquire(_PLAN)
        return await _drain(backend, session, TextRequest(prompt="hi", max_tokens=3))

    chunks = asyncio.run(scenario())
    assert chunks == [
        TextChunk(text="a", finished=False),
        TextChunk(text="b", finished=True),
    ]


def test_streams_not_buffers() -> None:
    # Stub parks (on an asyncio.Event, not a sleep) right after
    # yielding its first output — if generate() buffered the whole
    # response before yielding anything, the consumer could not have
    # its first chunk while the producer is still parked.
    pause_event = asyncio.Event()
    made: list[StubAsyncLLM] = []

    async def factory(model: str) -> StubAsyncLLM:
        stub = StubAsyncLLM(
            outputs=(
                StubRequestOutput(outputs=(_completion("chunk-1"),), finished=False),
                StubRequestOutput(outputs=(_completion("chunk-2"),), finished=True),
            ),
            pause_before_index=1,
            pause_event=pause_event,
        )
        made.append(stub)
        return stub

    backend = VllmTextBackend(
        model="m", engine_factory=factory, sampling_params_factory=_no_op_params_factory
    )

    async def scenario() -> list[TextChunk]:
        session = await backend.acquire(_PLAN)
        agen = backend.generate(session, TextRequest(prompt="hi", max_tokens=2))

        # chunk 1 arrives without the producer ever touching chunk 2 —
        # pull-based, zero lookahead (the opposite of LC8).
        first = await agen.__anext__()

        # Requesting chunk 2 is what actually asks the stub for its
        # next item — that is where it parks. Running it as a task
        # (not a bare `await`) is what proves the consumer already has
        # chunk 1 in hand *while* the producer is still mid-flight on
        # chunk 2, not that the whole exchange merely completed fast.
        async def _next() -> TextChunk:
            return await agen.__anext__()

        second_task = asyncio.create_task(_next())
        await asyncio.wait_for(made[0].paused.wait(), 1.0)
        assert made[0].paused.is_set()
        assert not second_task.done()
        assert not pause_event.is_set()

        pause_event.set()
        second = await asyncio.wait_for(second_task, 1.0)
        return [first, second]

    chunks = asyncio.run(scenario())
    assert chunks == [
        TextChunk(text="chunk-1", finished=False),
        TextChunk(text="chunk-2", finished=True),
    ]


def test_loop_stays_alive_while_stub_is_parked() -> None:
    pause_event = asyncio.Event()
    made: list[StubAsyncLLM] = []

    async def factory(model: str) -> StubAsyncLLM:
        stub = StubAsyncLLM(
            outputs=(StubRequestOutput(outputs=(_completion("only"),), finished=True),),
            pause_before_index=0,
            pause_event=pause_event,
        )
        made.append(stub)
        return stub

    backend = VllmTextBackend(
        model="m", engine_factory=factory, sampling_params_factory=_no_op_params_factory
    )

    async def scenario() -> tuple[list[TextChunk], bool]:
        session = await backend.acquire(_PLAN)
        request = TextRequest(prompt="hi", max_tokens=1)
        collected: list[TextChunk] = []
        progressed = False

        async def consume() -> None:
            async for chunk in backend.generate(session, request):
                collected.append(chunk)

        async def bump() -> None:
            nonlocal progressed
            await asyncio.wait_for(made[0].paused.wait(), 2.0)
            progressed = True
            pause_event.set()

        await asyncio.wait_for(asyncio.gather(consume(), bump()), timeout=5.0)
        return collected, progressed

    collected, progressed = asyncio.run(scenario())
    assert progressed
    assert collected == [TextChunk(text="only", finished=True)]


def _completion(text: str) -> StubCompletionOutput:
    return StubCompletionOutput(text=text)


def test_engine_construction_still_deduplicates_via_make_stub_engine_factory() -> None:
    # Regression guard: the streaming tests above hand-roll their
    # factory (they need bespoke stub configuration), but the shared
    # helper from `stub_async_llm.py` must still work unchanged.
    factory, made = make_stub_engine_factory()
    backend = VllmTextBackend(
        model="m", engine_factory=factory, sampling_params_factory=_no_op_params_factory
    )

    async def scenario() -> None:
        await backend.acquire(_PLAN)
        await backend.acquire(_PLAN)

    asyncio.run(scenario())
    assert len(made) == 1
