"""`onnxruntime-backend` spec, Requirement "Residency Lifecycle Governs
Model Access Through Acquire and Release", Scenario "acquire returns a
usable session, release ends it" (design decision OR2/VL13 inherited)
— `release()` drops the shared residency only when the last session
referencing it is released; releasing a non-last session leaves it
resident. Double release / foreign-session release is rejected
(`UnknownSessionError`), never silently-idempotent (LC2's rule
inherited unchanged).
"""

import asyncio

import pytest
from stub_onnx import make_stub_session_factory, make_stub_tokenizer_factory

from tibios_ray.backends.adapter import BackendId
from tibios_ray.engines.onnxrt import (
    ONNXRUNTIME_BACKEND_ID,
    OnnxEmbeddingBackend,
    UnknownSessionError,
)


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


_PLAN = _Plan(ONNXRUNTIME_BACKEND_ID)


def _backend_with_stubs():
    session_factory, sessions = make_stub_session_factory()
    tokenizer_factory, _ = make_stub_tokenizer_factory()
    backend = OnnxEmbeddingBackend(
        model_path="model.onnx",
        tokenizer_path="tok",
        session_factory=session_factory,
        tokenizer_factory=tokenizer_factory,
    )
    return backend, sessions


def test_acquire_then_release_round_trips_without_error() -> None:
    backend, _ = _backend_with_stubs()

    async def scenario() -> None:
        session = await backend.acquire(_PLAN)
        await backend.release(session)

    asyncio.run(scenario())  # no error


def test_releasing_a_non_last_session_leaves_the_session_resident() -> None:
    backend, made = _backend_with_stubs()

    async def scenario() -> None:
        first = await backend.acquire(_PLAN)
        await backend.acquire(_PLAN)
        await backend.release(first)
        # The shared session is still resident: a third acquire() must
        # reuse it, not build a second one.
        await backend.acquire(_PLAN)

    asyncio.run(scenario())

    assert len(made) == 1


def test_releasing_the_last_session_then_acquiring_again_builds_a_fresh_session() -> None:
    backend, made = _backend_with_stubs()

    async def scenario() -> None:
        first = await backend.acquire(_PLAN)
        second = await backend.acquire(_PLAN)
        await backend.release(first)
        await backend.release(second)
        await backend.acquire(_PLAN)  # nothing resident: builds fresh

    asyncio.run(scenario())

    assert len(made) == 2
    assert made[0] is not made[1]


def test_double_release_raises_unknown_session_error() -> None:
    backend, made = _backend_with_stubs()

    async def scenario() -> None:
        first = await backend.acquire(_PLAN)
        await backend.acquire(_PLAN)  # second session keeps residency alive
        await backend.release(first)

        with pytest.raises(UnknownSessionError):
            await backend.release(first)

    asyncio.run(scenario())

    assert len(made) == 1  # the refcount never went negative: no rebuild


def test_releasing_a_foreign_session_raises_unknown_session_error() -> None:
    backend, _ = _backend_with_stubs()
    other_backend, _ = _backend_with_stubs()

    async def scenario() -> None:
        foreign_session = await other_backend.acquire(_PLAN)
        with pytest.raises(UnknownSessionError):
            await backend.release(foreign_session)

    asyncio.run(scenario())
