"""Recording `RerankBackend` fake (`tibios_ray.backends.rerank`).

Extends `RecordingBackend` (`testing/backend.py`) with the `rerank()`
execution method `RerankBackend` adds. Same shape as
`FakeTextBackend`/`FakeEmbeddingBackend`: records every
acquired/released session, injectable to raise a caller-supplied
exception at `acquire`, `rerank`, or `release`.
"""

from collections.abc import Sequence

from tibios_ray.backends.adapter import BackendId, BackendSession, ServingPlanLike
from tibios_ray.backends.rerank import RerankResult
from tibios_ray.testing.backend import RecordingBackend


class FakeRerankBackend(RecordingBackend):
    """A conforming `RerankBackend` recording every acquired/released
    session and every `rerank()` call, injectable to raise at `acquire`,
    `rerank`, or `release`."""

    def __init__(
        self,
        backend_id: BackendId,
        *,
        results: Sequence[RerankResult] = (),
        acquire_raises: Exception | None = None,
        rerank_raises: Exception | None = None,
        release_raises: Exception | None = None,
    ) -> None:
        super().__init__(backend_id)
        self._results = tuple(results)
        self._acquire_raises = acquire_raises
        self._rerank_raises = rerank_raises
        self._release_raises = release_raises
        self.acquired: list[BackendSession] = []
        self.rerank_calls: list[tuple[BackendSession, str, Sequence[str]]] = []

    async def acquire(self, plan: ServingPlanLike) -> BackendSession:
        if self._acquire_raises is not None:
            raise self._acquire_raises
        session = await super().acquire(plan)
        self.acquired.append(session)
        return session

    async def release(self, session: BackendSession) -> None:
        if self._release_raises is not None:
            raise self._release_raises
        await super().release(session)

    async def rerank(
        self, session: BackendSession, query: str, documents: Sequence[str]
    ) -> Sequence[RerankResult]:
        self.rerank_calls.append((session, query, documents))
        if self._rerank_raises is not None:
            raise self._rerank_raises
        return self._results
