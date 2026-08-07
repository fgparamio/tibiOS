"""Tests for `tibios_ray.testing.rerank_backend` — `FakeRerankBackend`, a
recording `RerankBackend` fake following `RecordingBackend`'s shape
(`testing/backend.py`).
"""

import asyncio

from tibios_ray.backends.adapter import BackendAdapter, BackendId
from tibios_ray.backends.rerank import RerankBackend, RerankResult
from tibios_ray.testing.rerank_backend import FakeRerankBackend


class _FakeServingPlan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


def test_satisfies_the_backend_adapter_protocol() -> None:
    adapter: BackendAdapter = FakeRerankBackend(BackendId("onnxruntime"))
    assert adapter.backend_id == BackendId("onnxruntime")


def test_satisfies_the_rerank_backend_protocol() -> None:
    backend: RerankBackend = FakeRerankBackend(BackendId("onnxruntime"))
    assert backend.backend_id == BackendId("onnxruntime")


def test_acquire_records_the_session_and_release_records_it_too() -> None:
    backend = FakeRerankBackend(BackendId("onnxruntime"))

    async def scenario():
        session = await backend.acquire(_FakeServingPlan(BackendId("onnxruntime")))
        await backend.release(session)
        return session

    session = asyncio.run(scenario())

    assert backend.acquired == [session]
    assert backend.released == [session]


def test_rerank_returns_the_configured_results_and_records_the_call() -> None:
    results = (RerankResult(index=0, score=0.9), RerankResult(index=1, score=0.1))
    backend = FakeRerankBackend(BackendId("onnxruntime"), results=results)

    async def scenario():
        session = await backend.acquire(_FakeServingPlan(BackendId("onnxruntime")))
        return await backend.rerank(session, "query", ["doc-a", "doc-b"])

    result = asyncio.run(scenario())

    assert result == results
    assert len(backend.rerank_calls) == 1
    assert backend.rerank_calls[0][1] == "query"
    assert backend.rerank_calls[0][2] == ["doc-a", "doc-b"]


def test_rerank_raises_the_injected_exception() -> None:
    error = RuntimeError("boom")
    backend = FakeRerankBackend(BackendId("onnxruntime"), rerank_raises=error)

    async def scenario() -> None:
        session = await backend.acquire(_FakeServingPlan(BackendId("onnxruntime")))
        await backend.rerank(session, "query", ["doc-a"])

    try:
        asyncio.run(scenario())
        raised = False
    except RuntimeError:
        raised = True

    assert raised


def test_release_raises_the_injected_exception() -> None:
    error = RuntimeError("boom")
    backend = FakeRerankBackend(BackendId("onnxruntime"), release_raises=error)

    async def scenario() -> None:
        session = await backend.acquire(_FakeServingPlan(BackendId("onnxruntime")))
        await backend.release(session)

    try:
        asyncio.run(scenario())
        raised = False
    except RuntimeError:
        raised = True

    assert raised
