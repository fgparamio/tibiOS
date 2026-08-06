"""Tests for `tibios_ray.backends.adapter` — `BackendId`, `BackendSession`,
and the `BackendAdapter` Protocol (design decision D4: model residency
only, no unified `infer()`).

`RecordingBackend` (`tibios_ray.testing`, Phase 6) is the shared fake this
module's `FakeBackendAdapter` was consolidated into — this module is its
origin.
"""

import asyncio
import dataclasses

import pytest

from tibios_ray.backends.adapter import (
    BackendAdapter,
    BackendId,
    BackendSession,
)
from tibios_ray.testing import RecordingBackend


class TestBackendId:
    def test_holds_its_value(self) -> None:
        assert BackendId("llama_cpp").value == "llama_cpp"

    def test_is_frozen(self) -> None:
        backend_id = BackendId("llama_cpp")
        with pytest.raises(dataclasses.FrozenInstanceError):
            backend_id.value = "vllm"  # type: ignore[misc]

    def test_equality_is_by_value(self) -> None:
        assert BackendId("llama_cpp") == BackendId("llama_cpp")
        assert BackendId("llama_cpp") != BackendId("vllm")


class TestBackendSession:
    def test_holds_backend_id_and_session_id(self) -> None:
        session = BackendSession(backend_id=BackendId("llama_cpp"), session_id="sess-1")
        assert session.backend_id == BackendId("llama_cpp")
        assert session.session_id == "sess-1"

    def test_is_frozen(self) -> None:
        session = BackendSession(backend_id=BackendId("llama_cpp"), session_id="sess-1")
        with pytest.raises(dataclasses.FrozenInstanceError):
            session.session_id = "sess-2"  # type: ignore[misc]


class _FakeServingPlan:
    """A minimal stand-in for Phase 3's `selection.ServingPlan` — proves
    `BackendAdapter` needs only a structural `.backend` attribute, no
    import from `selection/` (that package does not exist yet)."""

    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


def test_fake_backend_adapter_satisfies_the_protocol() -> None:
    adapter: BackendAdapter = RecordingBackend(BackendId("llama_cpp"))
    assert adapter.backend_id == BackendId("llama_cpp")


def test_supports_returns_true_for_matching_backend_and_false_otherwise() -> None:
    adapter = RecordingBackend(BackendId("llama_cpp"))
    assert adapter.supports(_FakeServingPlan(BackendId("llama_cpp"))) is True
    assert adapter.supports(_FakeServingPlan(BackendId("vllm"))) is False


def test_acquire_then_release_round_trips_a_session() -> None:
    adapter = RecordingBackend(BackendId("onnxruntime"))

    async def scenario() -> None:
        session = await adapter.acquire(_FakeServingPlan(BackendId("onnxruntime")))
        assert session.backend_id == BackendId("onnxruntime")
        await adapter.release(session)

    asyncio.run(scenario())
    assert len(adapter.released) == 1
    assert adapter.released[0].backend_id == BackendId("onnxruntime")
