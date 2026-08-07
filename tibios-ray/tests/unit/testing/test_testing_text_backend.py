"""Tests for `tibios_ray.testing.text_backend` — `FakeTextBackend`, a
recording `TextGenerationBackend` fake following `RecordingBackend`'s
shape (`testing/backend.py`).
"""

import asyncio

from tibios_ray.backends.adapter import BackendAdapter, BackendId, BackendSession
from tibios_ray.backends.text import TextChunk, TextGenerationBackend, TextRequest
from tibios_ray.testing.text_backend import FakeTextBackend


class _FakeServingPlan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


def test_satisfies_the_backend_adapter_protocol() -> None:
    adapter: BackendAdapter = FakeTextBackend(BackendId("llama_cpp"))
    assert adapter.backend_id == BackendId("llama_cpp")


def test_satisfies_the_text_generation_backend_protocol() -> None:
    backend: TextGenerationBackend = FakeTextBackend(BackendId("llama_cpp"))
    assert backend.backend_id == BackendId("llama_cpp")


def test_acquire_records_the_session_and_release_records_it_too() -> None:
    backend = FakeTextBackend(BackendId("llama_cpp"))

    async def scenario() -> BackendSession:
        session = await backend.acquire(_FakeServingPlan(BackendId("llama_cpp")))
        await backend.release(session)
        return session

    session = asyncio.run(scenario())

    assert backend.acquired == [session]
    assert backend.released == [session]


def test_generate_yields_the_configured_chunks_and_records_the_call() -> None:
    chunks = (TextChunk(text="Hel"), TextChunk(text="lo"), TextChunk(text="", finished=True))
    backend = FakeTextBackend(BackendId("llama_cpp"), chunks=chunks)

    async def scenario() -> list[TextChunk]:
        session = await backend.acquire(_FakeServingPlan(BackendId("llama_cpp")))
        request = TextRequest(prompt="hi", max_tokens=8)
        return [chunk async for chunk in backend.generate(session, request)]

    result = asyncio.run(scenario())

    assert result == list(chunks)
    assert len(backend.generate_calls) == 1


def test_acquire_raises_the_injected_exception_and_records_nothing() -> None:
    error = RuntimeError("boom")
    backend = FakeTextBackend(BackendId("llama_cpp"), acquire_raises=error)

    async def scenario() -> None:
        await backend.acquire(_FakeServingPlan(BackendId("llama_cpp")))

    try:
        asyncio.run(scenario())
        raised = False
    except RuntimeError:
        raised = True

    assert raised
    assert backend.acquired == []


def test_generate_raises_the_injected_exception() -> None:
    error = RuntimeError("boom")
    backend = FakeTextBackend(BackendId("llama_cpp"), generate_raises=error)

    async def scenario() -> None:
        session = await backend.acquire(_FakeServingPlan(BackendId("llama_cpp")))
        request = TextRequest(prompt="hi", max_tokens=8)
        async for _ in backend.generate(session, request):
            pass

    try:
        asyncio.run(scenario())
        raised = False
    except RuntimeError:
        raised = True

    assert raised


def test_release_raises_the_injected_exception() -> None:
    error = RuntimeError("boom")
    backend = FakeTextBackend(BackendId("llama_cpp"), release_raises=error)

    async def scenario() -> None:
        session = await backend.acquire(_FakeServingPlan(BackendId("llama_cpp")))
        await backend.release(session)

    try:
        asyncio.run(scenario())
        raised = False
    except RuntimeError:
        raised = True

    assert raised
