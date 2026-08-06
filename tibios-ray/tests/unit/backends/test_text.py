"""Tests for `tibios_ray.backends.text` — `TextGenerationBackend`, the
streaming text-generation execution Protocol (llama.cpp, vLLM,
TensorRT-LLM in Phase 4). Extends `BackendAdapter` with a narrow
streaming method; no unified `infer()` (design decision D4).
"""

import asyncio
import dataclasses
from collections.abc import AsyncIterator

import pytest

from tibios_ray.backends.adapter import BackendId, BackendSession
from tibios_ray.backends.text import TextChunk, TextGenerationBackend, TextRequest


class FakeTextBackend:
    def __init__(self) -> None:
        self._backend_id = BackendId("llama_cpp")

    @property
    def backend_id(self) -> BackendId:
        return self._backend_id

    def supports(self, plan: object) -> bool:  # pragma: no cover - unused here
        return True

    async def acquire(self, plan: object) -> BackendSession:
        return BackendSession(backend_id=self._backend_id, session_id="sess-text")

    async def release(self, session: BackendSession) -> None:  # pragma: no cover - unused
        return None

    async def generate(
        self, session: BackendSession, request: TextRequest
    ) -> AsyncIterator[TextChunk]:
        words = request.prompt.split()
        for index, word in enumerate(words[: request.max_tokens]):
            yield TextChunk(text=word, finished=index == len(words) - 1)


class TestTextRequest:
    def test_holds_its_fields_with_stop_defaulting_empty(self) -> None:
        request = TextRequest(prompt="hello world", max_tokens=10)
        assert request.prompt == "hello world"
        assert request.max_tokens == 10
        assert request.temperature == 1.0
        assert request.stop == ()

    def test_is_frozen(self) -> None:
        request = TextRequest(prompt="hi", max_tokens=1)
        with pytest.raises(dataclasses.FrozenInstanceError):
            request.max_tokens = 2  # type: ignore[misc]


class TestTextChunk:
    def test_holds_text_and_defaults_not_finished(self) -> None:
        chunk = TextChunk(text="hi")
        assert chunk.text == "hi"
        assert chunk.finished is False

    def test_is_frozen(self) -> None:
        chunk = TextChunk(text="hi")
        with pytest.raises(dataclasses.FrozenInstanceError):
            chunk.text = "bye"  # type: ignore[misc]


def test_fake_text_backend_satisfies_the_protocol() -> None:
    backend: TextGenerationBackend = FakeTextBackend()
    assert backend.backend_id == BackendId("llama_cpp")


def test_generate_streams_chunks_derived_from_the_request() -> None:
    backend = FakeTextBackend()

    async def scenario() -> list[TextChunk]:
        session = await backend.acquire(object())
        request = TextRequest(prompt="hi there", max_tokens=2)
        return [chunk async for chunk in backend.generate(session, request)]

    chunks = asyncio.run(scenario())
    assert [c.text for c in chunks] == ["hi", "there"]
    assert chunks[-1].finished is True


def test_generate_respects_max_tokens_truncation() -> None:
    backend = FakeTextBackend()

    async def scenario() -> list[TextChunk]:
        session = await backend.acquire(object())
        request = TextRequest(prompt="one two three four", max_tokens=1)
        return [chunk async for chunk in backend.generate(session, request)]

    chunks = asyncio.run(scenario())
    assert [c.text for c in chunks] == ["one"]
