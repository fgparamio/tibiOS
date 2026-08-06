"""`llamacpp-text-backend` spec, Requirements "Streaming Output Is
Transport-Agnostic" and "Non-Blocking Thread-Bridge Streaming" —
`generate()`'s thread-bridge implementation (design decisions LC4-LC10).
"""

import asyncio
import threading

from stub_llama import StubLlama

from tibios_ray.backends.adapter import BackendId, BackendSession
from tibios_ray.backends.text import TextChunk, TextRequest
from tibios_ray.engines.llamacpp import LlamaCppTextBackend


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


_PLAN = _Plan(BackendId("llama_cpp"))


async def _drain(
    backend: LlamaCppTextBackend, session: BackendSession, request: TextRequest
) -> list[TextChunk]:
    return [chunk async for chunk in backend.generate(session, request)]


def test_streams_not_buffers() -> None:
    """LC8's one-token lookahead means the first chunk is not emitted
    until a second raw item has arrived (real token or exhaustion) —
    a one-item skew, not "wait for the whole completion". Both tokens
    here are produced instantly; only the *third* `next()` call — the
    one asking "is there more?" — blocks. By the time the consumer has
    its first `TextChunk`, the producer is already parked on that
    third call, proving the response was never buffered in full before
    something useful crossed the thread boundary."""
    block_event = threading.Event()
    stub = StubLlama(
        tokens=("chunk-1", "chunk-2"),
        block_before_index=2,
        block_event=block_event,
    )
    backend = LlamaCppTextBackend(model_path="model.gguf", factory=lambda path: stub)

    async def scenario() -> list[TextChunk]:
        session = await backend.acquire(_PLAN)
        request = TextRequest(prompt="hi", max_tokens=2)
        agen = backend.generate(session, request)

        first, _ = await asyncio.gather(
            agen.__anext__(),
            asyncio.to_thread(stub.parked.wait, 2.0),
        )
        assert stub.parked.is_set()
        assert not block_event.is_set()

        block_event.set()
        second = await agen.__anext__()
        return [first, second]

    chunks = asyncio.run(scenario())
    assert chunks == [
        TextChunk(text="chunk-1", finished=False),
        TextChunk(text="chunk-2", finished=True),
    ]


def test_loop_stays_alive() -> None:
    """If `generate()` blocked the event loop while the pump thread is
    parked, the concurrent `bump()` task below could never run and this
    test would deadlock — deterministic by construction, not by
    sleeps."""
    block_event = threading.Event()
    stub = StubLlama(tokens=("only",), block_before_index=0, block_event=block_event)
    backend = LlamaCppTextBackend(model_path="model.gguf", factory=lambda path: stub)

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
            await asyncio.to_thread(stub.parked.wait, 2.0)
            progressed = True
            block_event.set()

        await asyncio.wait_for(asyncio.gather(consume(), bump()), timeout=5.0)
        return collected, progressed

    collected, progressed = asyncio.run(scenario())
    assert progressed
    assert collected == [TextChunk(text="only", finished=True)]


def test_terminal_semantics() -> None:
    backend = LlamaCppTextBackend(
        model_path="model.gguf",
        factory=lambda path: StubLlama(tokens=("a", "b", "c")),
    )

    async def scenario() -> list[TextChunk]:
        session = await backend.acquire(_PLAN)
        request = TextRequest(prompt="hi", max_tokens=3)
        return await _drain(backend, session, request)

    chunks = asyncio.run(scenario())
    assert len(chunks) > 1
    assert [c.text for c in chunks] == ["a", "b", "c"]
    assert [c.finished for c in chunks] == [False, False, True]


def test_terminal_semantics_empty_completion_yields_one_finished_chunk() -> None:
    backend = LlamaCppTextBackend(
        model_path="model.gguf",
        factory=lambda path: StubLlama(tokens=()),
    )

    async def scenario() -> list[TextChunk]:
        session = await backend.acquire(_PLAN)
        request = TextRequest(prompt="hi", max_tokens=1)
        return await _drain(backend, session, request)

    chunks = asyncio.run(scenario())
    assert chunks == [TextChunk(text="", finished=True)]


def test_terminal_semantics_drops_empty_text_raw_chunks() -> None:
    backend = LlamaCppTextBackend(
        model_path="model.gguf",
        factory=lambda path: StubLlama(tokens=("a", "", "b", "")),
    )

    async def scenario() -> list[TextChunk]:
        session = await backend.acquire(_PLAN)
        request = TextRequest(prompt="hi", max_tokens=4)
        return await _drain(backend, session, request)

    chunks = asyncio.run(scenario())
    assert chunks == [
        TextChunk(text="a", finished=False),
        TextChunk(text="b", finished=True),
    ]


def test_parameter_mapping() -> None:
    stub = StubLlama(tokens=("ok",))
    backend = LlamaCppTextBackend(model_path="model.gguf", factory=lambda path: stub)

    async def scenario() -> None:
        session = await backend.acquire(_PLAN)
        request = TextRequest(
            prompt="translate: hola",
            max_tokens=42,
            temperature=0.3,
            stop=("</s>", "\n\n"),
        )
        await _drain(backend, session, request)

    asyncio.run(scenario())

    assert stub.create_completion_calls == [
        {
            "prompt": "translate: hola",
            "max_tokens": 42,
            "temperature": 0.3,
            "stop": ["</s>", "\n\n"],
            "stream": True,
        }
    ]


def test_exception_propagation() -> None:
    boom = RuntimeError("boom")
    stub = StubLlama(tokens=("a", "b"), error=boom, error_before_index=1)
    backend = LlamaCppTextBackend(model_path="model.gguf", factory=lambda path: stub)

    async def scenario() -> list[TextChunk]:
        session = await backend.acquire(_PLAN)
        request = TextRequest(prompt="hi", max_tokens=2)

        raised: BaseException | None = None
        try:
            async for _ in backend.generate(session, request):
                pass
        except RuntimeError as error:
            raised = error
        assert raised is boom

        # Prove the lock was released: a fresh generate() on the same
        # session must complete rather than hang.
        stub.error = None
        return await asyncio.wait_for(_drain(backend, session, request), timeout=2.0)

    chunks = asyncio.run(scenario())
    assert chunks == [
        TextChunk(text="a", finished=False),
        TextChunk(text="b", finished=True),
    ]
