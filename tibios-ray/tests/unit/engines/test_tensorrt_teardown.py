"""`tensorrt-llm-text-backend` spec, Requirement "Shared Refcounted
Model Runtime, Mirroring vllm-text-backend" — `release()` shuts the
shared engine down only when the last session referencing it is
released; releasing a non-last session leaves it running. Double
release / foreign-session release is rejected (`UnknownSessionError`),
never silently-idempotent (design decision D34, VL13/LC2 inherited) —
mirrors `test_vllm_teardown.py`.
"""

import asyncio

import pytest
from stub_trtllm import StubLLM

from tibios_ray.backends.adapter import BackendId
from tibios_ray.engines.tensorrt import TensorrtLlmTextBackend, UnknownSessionError


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


_PLAN = _Plan(BackendId("tensorrt_llm"))


def _backend_with_stub() -> tuple[TensorrtLlmTextBackend, list[StubLLM]]:
    made: list[StubLLM] = []

    async def factory(engine_path: str) -> StubLLM:
        stub = StubLLM(model=engine_path)
        made.append(stub)
        return stub

    return TensorrtLlmTextBackend(engine_path="/engines/m", engine_factory=factory), made


def test_releasing_the_last_session_shuts_the_engine_down() -> None:
    backend, made = _backend_with_stub()

    async def scenario() -> None:
        session = await backend.acquire(_PLAN)
        await backend.release(session)

    asyncio.run(scenario())

    assert made[0].shutdown_calls == 1


def test_releasing_a_non_last_session_keeps_the_engine_running() -> None:
    backend, made = _backend_with_stub()

    async def scenario() -> None:
        first = await backend.acquire(_PLAN)
        await backend.acquire(_PLAN)
        await backend.release(first)

    asyncio.run(scenario())

    assert made[0].shutdown_calls == 0


def test_releasing_the_second_of_two_then_the_first_shuts_down_exactly_once() -> None:
    backend, made = _backend_with_stub()

    async def scenario() -> None:
        first = await backend.acquire(_PLAN)
        second = await backend.acquire(_PLAN)
        await backend.release(second)
        assert made[0].shutdown_calls == 0
        await backend.release(first)

    asyncio.run(scenario())

    assert made[0].shutdown_calls == 1


def test_double_release_raises_unknown_session_error_and_refcount_unaffected() -> None:
    backend, made = _backend_with_stub()

    async def scenario() -> None:
        first = await backend.acquire(_PLAN)
        await backend.acquire(_PLAN)  # second session keeps the engine alive
        await backend.release(first)
        assert made[0].shutdown_calls == 0

        with pytest.raises(UnknownSessionError):
            await backend.release(first)
        # The refcount did not go negative: shutdown still hasn't fired.
        assert made[0].shutdown_calls == 0

    asyncio.run(scenario())


def test_releasing_a_foreign_session_raises_unknown_session_error() -> None:
    backend, _ = _backend_with_stub()
    other_backend, _ = _backend_with_stub()

    async def scenario() -> None:
        foreign_session = await other_backend.acquire(_PLAN)
        with pytest.raises(UnknownSessionError):
            await backend.release(foreign_session)

    asyncio.run(scenario())


def test_acquire_after_full_release_constructs_a_fresh_engine() -> None:
    backend, made = _backend_with_stub()

    async def scenario() -> None:
        first = await backend.acquire(_PLAN)
        await backend.release(first)
        await backend.acquire(_PLAN)

    asyncio.run(scenario())

    assert len(made) == 2
    assert made[0] is not made[1]
