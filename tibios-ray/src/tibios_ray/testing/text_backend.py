"""Recording `TextGenerationBackend` fake (`tibios_ray.backends.text`).

Extends `RecordingBackend` (`testing/backend.py`) — which models the
residency-only `BackendAdapter` surface shared by every modality — with
the `generate()` execution method `TextGenerationBackend` adds. Follows
`RecordingBackend`'s shape: records every acquired/released session, and
is injectable to raise a caller-supplied exception at `acquire`,
`generate`, or `release`, for a Provider test's release-guarantee
scenarios (`provider-backend-composition` spec: "Backend Session Release
Is Guaranteed").
"""

from collections.abc import AsyncIterator, Sequence

from tibios_ray.backends.adapter import BackendId, BackendSession, ServingPlanLike
from tibios_ray.backends.text import TextChunk, TextRequest
from tibios_ray.testing.backend import RecordingBackend


class FakeTextBackend(RecordingBackend):
    """A conforming `TextGenerationBackend` recording every
    acquired/released session and every `generate()` call, injectable to
    raise at `acquire`, `generate`, or `release`."""

    def __init__(
        self,
        backend_id: BackendId,
        *,
        chunks: Sequence[TextChunk] = (),
        acquire_raises: Exception | None = None,
        generate_raises: Exception | None = None,
        release_raises: Exception | None = None,
    ) -> None:
        super().__init__(backend_id)
        self._chunks = tuple(chunks)
        self._acquire_raises = acquire_raises
        self._generate_raises = generate_raises
        self._release_raises = release_raises
        self.acquired: list[BackendSession] = []
        self.generate_calls: list[tuple[BackendSession, TextRequest]] = []

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

    async def generate(
        self, session: BackendSession, request: TextRequest
    ) -> AsyncIterator[TextChunk]:
        self.generate_calls.append((session, request))
        if self._generate_raises is not None:
            raise self._generate_raises
        for chunk in self._chunks:
            yield chunk
