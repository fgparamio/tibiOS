"""Tests for `tibios_ray.backends.embedding` — `EmbeddingBackend`: batch
in / fixed-shape vectors out, no streaming (ONNX Runtime in Phase 4).
"""

import asyncio
import dataclasses
from collections.abc import Sequence

import pytest

from tibios_ray.backends.adapter import BackendId, BackendSession
from tibios_ray.backends.embedding import EmbeddingBackend, Vector


class FakeEmbeddingBackend:
    def __init__(self) -> None:
        self._backend_id = BackendId("onnxruntime")

    @property
    def backend_id(self) -> BackendId:
        return self._backend_id

    def supports(self, plan: object) -> bool:  # pragma: no cover - unused here
        return True

    async def acquire(self, plan: object) -> BackendSession:
        return BackendSession(backend_id=self._backend_id, session_id="sess-embed")

    async def release(self, session: BackendSession) -> None:  # pragma: no cover - unused
        return None

    async def embed(self, session: BackendSession, inputs: Sequence[str]) -> Sequence[Vector]:
        return [Vector(values=tuple(float(len(text)) for _ in range(2))) for text in inputs]


class TestVector:
    def test_holds_its_values(self) -> None:
        vector = Vector(values=(0.1, 0.2, 0.3))
        assert vector.values == (0.1, 0.2, 0.3)

    def test_is_frozen(self) -> None:
        vector = Vector(values=(0.1,))
        with pytest.raises(dataclasses.FrozenInstanceError):
            vector.values = (0.2,)  # type: ignore[misc]


def test_fake_embedding_backend_satisfies_the_protocol() -> None:
    backend: EmbeddingBackend = FakeEmbeddingBackend()
    assert backend.backend_id == BackendId("onnxruntime")


def test_embed_returns_one_vector_per_input_batch_no_streaming() -> None:
    backend = FakeEmbeddingBackend()

    async def scenario() -> Sequence[Vector]:
        session = await backend.acquire(object())
        return await backend.embed(session, ["hello", "worldwide"])

    vectors = asyncio.run(scenario())
    assert len(vectors) == 2
    assert vectors[0].values == (5.0, 5.0)
    assert vectors[1].values == (9.0, 9.0)


def test_embed_with_empty_input_returns_empty_batch() -> None:
    backend = FakeEmbeddingBackend()

    async def scenario() -> Sequence[Vector]:
        session = await backend.acquire(object())
        return await backend.embed(session, [])

    vectors = asyncio.run(scenario())
    assert vectors == []
