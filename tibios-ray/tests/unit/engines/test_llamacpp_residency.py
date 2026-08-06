"""`llamacpp-text-backend` spec, Requirement "Residency Lifecycle
Constructs and Frees One Model Per Session" — `acquire()` constructs
exactly one `Llama` per call (design decision LC3, side table LC2);
`release()` frees it and makes the session unusable.
"""

import asyncio

import pytest
from stub_llama import StubLlama

from tibios_ray.backends.adapter import BackendId
from tibios_ray.engines.llamacpp import LlamaCppTextBackend


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


_PLAN = _Plan(BackendId("llama_cpp"))


def _backend_with_stubs() -> tuple[LlamaCppTextBackend, list[StubLlama]]:
    made: list[StubLlama] = []

    def factory(model_path: str) -> StubLlama:
        stub = StubLlama()
        made.append(stub)
        return stub

    return LlamaCppTextBackend(model_path="model.gguf", factory=factory), made


def test_two_acquires_give_distinct_session_ids_and_distinct_stub_instances() -> None:
    backend, made = _backend_with_stubs()

    async def scenario() -> tuple[str, str]:
        first = await backend.acquire(_PLAN)
        second = await backend.acquire(_PLAN)
        return first.session_id, second.session_id

    first_id, second_id = asyncio.run(scenario())

    assert first_id != second_id
    assert len(made) == 2
    assert made[0] is not made[1]


def test_acquire_returns_a_session_bound_to_the_llama_cpp_backend_id() -> None:
    backend, _ = _backend_with_stubs()

    async def scenario() -> BackendId:
        session = await backend.acquire(_PLAN)
        return session.backend_id

    assert asyncio.run(scenario()) == BackendId("llama_cpp")


def test_release_calls_close_exactly_once_and_the_session_becomes_unusable() -> None:
    backend, made = _backend_with_stubs()

    async def scenario() -> None:
        session = await backend.acquire(_PLAN)
        await backend.release(session)
        assert made[0].close_calls == 1

        # The session is no longer usable: releasing it again fails the
        # same way an always-unknown session would (it has been popped
        # from the residency side table, design decision LC2).
        with pytest.raises(Exception):
            await backend.release(session)

    asyncio.run(scenario())


def test_releasing_an_unknown_session_raises() -> None:
    backend, _ = _backend_with_stubs()
    foreign_session = asyncio.run(_backend_with_stubs()[0].acquire(_PLAN))

    async def scenario() -> None:
        with pytest.raises(Exception):
            await backend.release(foreign_session)

    asyncio.run(scenario())
