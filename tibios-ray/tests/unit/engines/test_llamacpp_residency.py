"""`llamacpp-text-backend` spec, Requirement "Residency Is Backend-Owned,
Not Request-Owned" (design decisions D26/D27) — `acquire()` checks an
already-warm instance out of the pool (never constructs one);
`release()` returns it for reuse and pops the session from the side
table, making that `BackendSession` handle unusable again.

Pool-level behavior (eager construction, exhaustion, no-close-on-release)
is covered end to end in `test_llamacpp_pool.py`; this module covers the
per-session handle bookkeeping layered on top of the pool (LC2).
"""

import asyncio
from pathlib import Path

import pytest
from stub_llama import StubLlama

from tibios_ray.backends.adapter import BackendId
from tibios_ray.engines.llamacpp import LlamaCppTextBackend


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


_PLAN = _Plan(BackendId("llama_cpp"))


def _gguf_path(tmp_path: Path) -> str:
    path = tmp_path / "model.gguf"
    path.write_bytes(b"not a real gguf, just needs to exist and be readable")
    return str(path)


def _backend_with_stubs(
    tmp_path: Path, *, pool_size: int = 1
) -> tuple[LlamaCppTextBackend, list[StubLlama]]:
    made: list[StubLlama] = []

    def factory(model_path: str) -> StubLlama:
        stub = StubLlama()
        made.append(stub)
        return stub

    backend = LlamaCppTextBackend(
        model_path=_gguf_path(tmp_path), factory=factory, pool_size=pool_size
    )
    return backend, made


def test_two_acquires_give_distinct_session_ids_and_distinct_pool_instances(
    tmp_path: Path,
) -> None:
    # pool_size=2: two pre-warmed instances exist before either acquire()
    # runs (D26/D27) — the factory is never called again by acquire()
    # itself, so `made` stays at exactly 2 throughout.
    backend, made = _backend_with_stubs(tmp_path, pool_size=2)

    async def scenario() -> tuple[str, str]:
        first = await backend.acquire(_PLAN)
        second = await backend.acquire(_PLAN)
        return first.session_id, second.session_id

    first_id, second_id = asyncio.run(scenario())

    assert first_id != second_id
    assert len(made) == 2
    assert made[0] is not made[1]


def test_acquire_returns_a_session_bound_to_the_llama_cpp_backend_id(
    tmp_path: Path,
) -> None:
    backend, _ = _backend_with_stubs(tmp_path)

    async def scenario() -> BackendId:
        session = await backend.acquire(_PLAN)
        return session.backend_id

    assert asyncio.run(scenario()) == BackendId("llama_cpp")


def test_release_never_closes_and_the_session_handle_becomes_unusable(
    tmp_path: Path,
) -> None:
    backend, made = _backend_with_stubs(tmp_path)

    async def scenario() -> None:
        session = await backend.acquire(_PLAN)
        await backend.release(session)
        # D26: the instance is returned to the pool for reuse, never
        # closed — instances are process-scoped (ADR-0001).
        assert made[0].close_calls == 0

        # The *session handle* is no longer usable: releasing it again
        # fails the same way an always-unknown session would (it has
        # been popped from the residency side table, design decision
        # LC2) — this is independent of whether the underlying `Llama`
        # instance itself is still alive in the pool.
        with pytest.raises(Exception):
            await backend.release(session)

    asyncio.run(scenario())


def test_releasing_an_unknown_session_raises(tmp_path: Path) -> None:
    backend, _ = _backend_with_stubs(tmp_path)
    other_backend, _ = _backend_with_stubs(tmp_path)
    foreign_session = asyncio.run(other_backend.acquire(_PLAN))

    async def scenario() -> None:
        with pytest.raises(Exception):
            await backend.release(foreign_session)

    asyncio.run(scenario())
