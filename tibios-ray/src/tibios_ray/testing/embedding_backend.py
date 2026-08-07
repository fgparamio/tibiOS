"""Recording `EmbeddingBackend` fake (`tibios_ray.backends.embedding`).

Extends `RecordingBackend` (`testing/backend.py`) with the `embed()`
execution method `EmbeddingBackend` adds. Same shape as
`FakeTextBackend` (`testing/text_backend.py`): records every
acquired/released session, injectable to raise a caller-supplied
exception at `acquire`, `embed`, or `release`.
"""

from collections.abc import Sequence

from tibios_ray.backends.adapter import BackendId, BackendSession, ServingPlanLike
from tibios_ray.backends.embedding import Vector
from tibios_ray.testing.backend import RecordingBackend


class FakeEmbeddingBackend(RecordingBackend):
    """A conforming `EmbeddingBackend` recording every acquired/released
    session and every `embed()` call, injectable to raise at `acquire`,
    `embed`, or `release`."""

    def __init__(
        self,
        backend_id: BackendId,
        *,
        vectors: Sequence[Vector] = (),
        acquire_raises: Exception | None = None,
        embed_raises: Exception | None = None,
        release_raises: Exception | None = None,
    ) -> None:
        super().__init__(backend_id)
        self._vectors = tuple(vectors)
        self._acquire_raises = acquire_raises
        self._embed_raises = embed_raises
        self._release_raises = release_raises
        self.acquired: list[BackendSession] = []
        self.embed_calls: list[tuple[BackendSession, Sequence[str]]] = []

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

    async def embed(self, session: BackendSession, inputs: Sequence[str]) -> Sequence[Vector]:
        self.embed_calls.append((session, inputs))
        if self._embed_raises is not None:
            raise self._embed_raises
        return self._vectors
