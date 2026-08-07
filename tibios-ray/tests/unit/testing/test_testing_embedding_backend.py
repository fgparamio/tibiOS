"""Tests for `tibios_ray.testing.embedding_backend` — `FakeEmbeddingBackend`,
a recording `EmbeddingBackend` fake following `RecordingBackend`'s shape
(`testing/backend.py`).
"""

import asyncio

from tibios_ray.backends.adapter import BackendAdapter, BackendId
from tibios_ray.backends.embedding import EmbeddingBackend, Vector
from tibios_ray.testing.embedding_backend import FakeEmbeddingBackend


class _FakeServingPlan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


def test_satisfies_the_backend_adapter_protocol() -> None:
    adapter: BackendAdapter = FakeEmbeddingBackend(BackendId("onnxruntime"))
    assert adapter.backend_id == BackendId("onnxruntime")


def test_satisfies_the_embedding_backend_protocol() -> None:
    backend: EmbeddingBackend = FakeEmbeddingBackend(BackendId("onnxruntime"))
    assert backend.backend_id == BackendId("onnxruntime")


def test_acquire_records_the_session_and_release_records_it_too() -> None:
    backend = FakeEmbeddingBackend(BackendId("onnxruntime"))

    async def scenario():
        session = await backend.acquire(_FakeServingPlan(BackendId("onnxruntime")))
        await backend.release(session)
        return session

    session = asyncio.run(scenario())

    assert backend.acquired == [session]
    assert backend.released == [session]


def test_embed_returns_the_configured_vectors_and_records_the_call() -> None:
    vectors = (Vector(values=(0.1, 0.2)), Vector(values=(0.3, 0.4)))
    backend = FakeEmbeddingBackend(BackendId("onnxruntime"), vectors=vectors)

    async def scenario():
        session = await backend.acquire(_FakeServingPlan(BackendId("onnxruntime")))
        return await backend.embed(session, ["a", "b"])

    result = asyncio.run(scenario())

    assert result == vectors
    assert len(backend.embed_calls) == 1
    assert backend.embed_calls[0][1] == ["a", "b"]


def test_embed_raises_the_injected_exception() -> None:
    error = RuntimeError("boom")
    backend = FakeEmbeddingBackend(BackendId("onnxruntime"), embed_raises=error)

    async def scenario() -> None:
        session = await backend.acquire(_FakeServingPlan(BackendId("onnxruntime")))
        await backend.embed(session, ["a"])

    try:
        asyncio.run(scenario())
        raised = False
    except RuntimeError:
        raised = True

    assert raised


def test_release_raises_the_injected_exception() -> None:
    error = RuntimeError("boom")
    backend = FakeEmbeddingBackend(BackendId("onnxruntime"), release_raises=error)

    async def scenario() -> None:
        session = await backend.acquire(_FakeServingPlan(BackendId("onnxruntime")))
        await backend.release(session)

    try:
        asyncio.run(scenario())
        raised = False
    except RuntimeError:
        raised = True

    assert raised
