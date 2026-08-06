"""Tests for `tibios_ray.backends.rerank` — `RerankBackend`: mirrors
`EmbeddingBackend`'s shape (batch in, no streaming) for the
`rerank.documents` capability. Not in `design.md`'s illustrative Key
Contracts snippet, so this Protocol is inferred from the same D4 residency
pattern the other three modalities follow (see apply-progress deviation
note).
"""

import asyncio
import dataclasses
from collections.abc import Sequence

import pytest

from tibios_ray.backends.adapter import BackendId, BackendSession
from tibios_ray.backends.rerank import RerankBackend, RerankResult


class FakeRerankBackend:
    def __init__(self) -> None:
        self._backend_id = BackendId("onnxruntime")

    @property
    def backend_id(self) -> BackendId:
        return self._backend_id

    def supports(self, plan: object) -> bool:  # pragma: no cover - unused here
        return True

    async def acquire(self, plan: object) -> BackendSession:
        return BackendSession(backend_id=self._backend_id, session_id="sess-rerank")

    async def release(self, session: BackendSession) -> None:  # pragma: no cover - unused
        return None

    async def rerank(
        self, session: BackendSession, query: str, documents: Sequence[str]
    ) -> Sequence[RerankResult]:
        scored = [
            RerankResult(index=i, score=float(len(set(query.split()) & set(doc.split()))))
            for i, doc in enumerate(documents)
        ]
        return sorted(scored, key=lambda r: r.score, reverse=True)


class TestRerankResult:
    def test_holds_index_and_score(self) -> None:
        result = RerankResult(index=2, score=0.75)
        assert result.index == 2
        assert result.score == 0.75

    def test_is_frozen(self) -> None:
        result = RerankResult(index=0, score=0.1)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.score = 0.9  # type: ignore[misc]


def test_fake_rerank_backend_satisfies_the_protocol() -> None:
    backend: RerankBackend = FakeRerankBackend()
    assert backend.backend_id == BackendId("onnxruntime")


def test_rerank_orders_documents_by_relevance_to_query() -> None:
    backend = FakeRerankBackend()

    async def scenario() -> Sequence[RerankResult]:
        session = await backend.acquire(object())
        return await backend.rerank(
            session,
            "python testing",
            ["python is a language", "testing matters", "unrelated document"],
        )

    results = asyncio.run(scenario())
    assert results[0].index in {0, 1}
    assert results[-1].index == 2
    assert results[-1].score == 0.0


def test_rerank_with_no_documents_returns_empty() -> None:
    backend = FakeRerankBackend()

    async def scenario() -> Sequence[RerankResult]:
        session = await backend.acquire(object())
        return await backend.rerank(session, "query", [])

    assert asyncio.run(scenario()) == []
