"""Recording `BackendAdapter` fake (`tibios_ray.backends.adapter`).

Consolidates the ad-hoc `FakeBackendAdapter` double from
`tests/unit/backends/test_adapter.py` — the residency-only surface every
modality-specific Backend Adapter extends (design decision D4). Per-modality
execution fakes (`FakeTextBackend`, `FakeEmbeddingBackend`,
`FakeRerankBackend`, `FakeTranscriptionBackend`) stay local to their own test
modules: each adds a distinct execution method (`generate`/`embed`/`rerank`/
`transcribe`) this shared fake deliberately does not model (design decision
D4: no unified `infer()`).
"""

from tibios_ray.backends.adapter import BackendId, BackendSession, ServingPlanLike


class RecordingBackend:
    """A conforming `BackendAdapter` (Protocol, design decision D1) that
    records every released session, for tests asserting the
    acquire/release residency round trip."""

    def __init__(self, backend_id: BackendId) -> None:
        self._backend_id = backend_id
        self.released: list[BackendSession] = []

    @property
    def backend_id(self) -> BackendId:
        return self._backend_id

    def supports(self, plan: ServingPlanLike) -> bool:
        return plan.backend == self._backend_id

    async def acquire(self, plan: ServingPlanLike) -> BackendSession:
        return BackendSession(backend_id=plan.backend, session_id="sess-acquired")

    async def release(self, session: BackendSession) -> None:
        self.released.append(session)
