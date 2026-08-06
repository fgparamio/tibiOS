"""Tests for `tibios_ray.testing.backend` — `RecordingBackend`, the shared
`BackendAdapter` fake consolidating the ad-hoc `FakeBackendAdapter` double
from `tests/unit/backends/test_adapter.py` (Phase 6, `testing/`).
"""

import asyncio

from tibios_ray.backends.adapter import BackendAdapter, BackendId
from tibios_ray.testing.backend import RecordingBackend


class _FakeServingPlan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


def test_satisfies_the_backend_adapter_protocol() -> None:
    adapter: BackendAdapter = RecordingBackend(BackendId("llama_cpp"))
    assert adapter.backend_id == BackendId("llama_cpp")


def test_supports_returns_true_for_matching_backend_and_false_otherwise() -> None:
    adapter = RecordingBackend(BackendId("llama_cpp"))
    assert adapter.supports(_FakeServingPlan(BackendId("llama_cpp"))) is True
    assert adapter.supports(_FakeServingPlan(BackendId("vllm"))) is False


def test_acquire_then_release_round_trips_a_session_and_records_it() -> None:
    adapter = RecordingBackend(BackendId("onnxruntime"))

    async def scenario() -> None:
        session = await adapter.acquire(_FakeServingPlan(BackendId("onnxruntime")))
        assert session.backend_id == BackendId("onnxruntime")
        await adapter.release(session)

    asyncio.run(scenario())

    assert len(adapter.released) == 1
    assert adapter.released[0].backend_id == BackendId("onnxruntime")
