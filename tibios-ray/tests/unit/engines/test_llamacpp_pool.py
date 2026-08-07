"""`llamacpp-text-backend` spec, Requirement "Residency Is Backend-Owned,
Not Request-Owned" (design decisions D26/D27) — `LlamaCppTextBackend`
builds a pool of `pool_size` pre-warmed `Llama` instances eagerly in
`__init__`, `acquire()` checks one out without ever constructing a new
one, `release()` returns it for reuse (never `close()`s it), and
exhaustion waits up to a configured timeout before raising
`PoolExhaustedError`.
"""

import asyncio
import time
from pathlib import Path

import pytest
from stub_llama import StubLlama

from tibios_ray.backends.adapter import BackendId, BackendSession
from tibios_ray.engines.llamacpp import LlamaCppTextBackend, PoolExhaustedError


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


_PLAN = _Plan(BackendId("llama_cpp"))


def _gguf_path(tmp_path: Path) -> str:
    path = tmp_path / "model.gguf"
    path.write_bytes(b"not a real gguf, just needs to exist and be readable")
    return str(path)


def test_pool_size_n_calls_factory_exactly_n_times_and_never_again_on_acquire(
    tmp_path: Path,
) -> None:
    made: list[StubLlama] = []

    def factory(model_path: str) -> StubLlama:
        stub = StubLlama()
        made.append(stub)
        return stub

    backend = LlamaCppTextBackend(
        model_path=_gguf_path(tmp_path), factory=factory, pool_size=3
    )

    assert len(made) == 3

    async def scenario() -> None:
        # M > N sequential acquire()/release() cycles — the factory must
        # never be called again.
        for _ in range(5):
            session = await backend.acquire(_PLAN)
            await backend.release(session)

    asyncio.run(scenario())

    assert len(made) == 3


def test_nplus1_concurrent_acquire_waits_then_succeeds_once_one_is_released(
    tmp_path: Path,
) -> None:
    backend = LlamaCppTextBackend(
        model_path=_gguf_path(tmp_path),
        factory=lambda path: StubLlama(),
        pool_size=2,
    )

    async def scenario() -> None:
        session_a = await backend.acquire(_PLAN)
        session_b = await backend.acquire(_PLAN)

        third_started = asyncio.Event()

        async def acquire_third() -> BackendSession:
            third_started.set()
            return await backend.acquire(_PLAN)

        third_task = asyncio.create_task(acquire_third())
        await third_started.wait()
        # Give the third acquire a real chance to run and park on the
        # empty queue before asserting it is still pending.
        await asyncio.sleep(0.05)
        assert not third_task.done()

        await backend.release(session_a)

        session_c = await asyncio.wait_for(third_task, timeout=1.0)
        assert session_c is not None

        await backend.release(session_b)
        await backend.release(session_c)

    asyncio.run(scenario())


def test_exhaustion_raises_pool_exhausted_error_and_release_never_called(
    tmp_path: Path,
) -> None:
    backend = LlamaCppTextBackend(
        model_path=_gguf_path(tmp_path),
        factory=lambda path: StubLlama(),
        pool_size=1,
        acquire_timeout=0.05,
    )

    async def scenario() -> float:
        # The only instance is held for the whole scenario — never
        # released — so the second acquire() must wait out the timeout
        # and then raise.
        await backend.acquire(_PLAN)

        started = time.monotonic()
        with pytest.raises(PoolExhaustedError):
            await backend.acquire(_PLAN)
        return time.monotonic() - started

    elapsed = asyncio.run(scenario())

    # It genuinely waited (not an immediate reject) before failing.
    assert elapsed >= 0.05


def test_release_returns_instance_to_pool_without_closing_it(tmp_path: Path) -> None:
    stub = StubLlama()
    backend = LlamaCppTextBackend(
        model_path=_gguf_path(tmp_path), factory=lambda path: stub, pool_size=1
    )

    async def scenario() -> None:
        session = await backend.acquire(_PLAN)
        await backend.release(session)

    asyncio.run(scenario())

    assert stub.close_calls == 0


def test_pool_size_zero_raises_before_any_factory_call(tmp_path: Path) -> None:
    calls: list[str] = []

    def factory(model_path: str) -> StubLlama:
        calls.append(model_path)
        return StubLlama()

    with pytest.raises(Exception):
        LlamaCppTextBackend(model_path=_gguf_path(tmp_path), factory=factory, pool_size=0)

    assert calls == []


def test_missing_model_path_raises_before_any_factory_call(tmp_path: Path) -> None:
    calls: list[str] = []

    def factory(model_path: str) -> StubLlama:
        calls.append(model_path)
        return StubLlama()

    missing_path = str(tmp_path / "does-not-exist.gguf")

    with pytest.raises(Exception):
        LlamaCppTextBackend(model_path=missing_path, factory=factory, pool_size=1)

    assert calls == []


def test_unreadable_model_path_raises_before_any_factory_call(tmp_path: Path) -> None:
    calls: list[str] = []

    def factory(model_path: str) -> StubLlama:
        calls.append(model_path)
        return StubLlama()

    unreadable_path = tmp_path / "unreadable.gguf"
    unreadable_path.write_bytes(b"secret weights")
    unreadable_path.chmod(0o000)
    try:
        with pytest.raises(Exception):
            LlamaCppTextBackend(
                model_path=str(unreadable_path), factory=factory, pool_size=1
            )
    finally:
        # Restore permissions so pytest's tmp_path cleanup can remove it.
        unreadable_path.chmod(0o644)

    assert calls == []


def test_factory_raising_on_second_of_three_propagates_out_of_construction(
    tmp_path: Path,
) -> None:
    boom = RuntimeError("boom on second instance")
    calls: list[int] = []

    def factory(model_path: str) -> StubLlama:
        calls.append(1)
        if len(calls) == 2:
            raise boom
        return StubLlama()

    with pytest.raises(RuntimeError) as excinfo:
        LlamaCppTextBackend(model_path=_gguf_path(tmp_path), factory=factory, pool_size=3)

    assert excinfo.value is boom
    assert len(calls) == 2
