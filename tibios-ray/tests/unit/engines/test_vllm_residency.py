"""`vllm-text-backend` spec, Requirement "Model Runtime Shares One
Engine Per Model" — `acquire()` constructs the engine lazily, on the
first call, and every subsequent `acquire()` for the same model reuses
that same instance (design decisions VL2/VL3/VL5), the exact inversion
of `llamacpp-text-backend`'s one-engine-per-session shape
(`test_llamacpp_residency.py`).

VL3: keying is degenerate — one `VllmTextBackend` instance serves
exactly one model (supplied out of band at construction), so "two
models get two engines" is proven with two distinct backend instances,
not one instance juggling two models.
"""

import asyncio

from stub_async_llm import StubAsyncLLM, make_stub_engine_factory

from tibios_ray.backends.adapter import BackendId
from tibios_ray.engines.vllm import VllmTextBackend


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


_PLAN = _Plan(BackendId("vllm"))


def _backend_with_stubs() -> tuple[VllmTextBackend, list[StubAsyncLLM]]:
    factory, made = make_stub_engine_factory()
    return VllmTextBackend(model="m", engine_factory=factory), made


def test_first_acquire_constructs_second_acquire_reuses() -> None:
    backend, made = _backend_with_stubs()

    async def scenario() -> tuple[str, str]:
        first = await backend.acquire(_PLAN)
        second = await backend.acquire(_PLAN)
        return first.session_id, second.session_id

    first_id, second_id = asyncio.run(scenario())

    assert first_id != second_id
    assert len(made) == 1  # exactly one engine constructed


def test_acquire_returns_a_session_bound_to_the_vllm_backend_id() -> None:
    backend, _ = _backend_with_stubs()

    async def scenario() -> BackendId:
        session = await backend.acquire(_PLAN)
        return session.backend_id

    assert asyncio.run(scenario()) == BackendId("vllm")


def test_two_distinct_backend_instances_get_two_distinct_engines() -> None:
    # VL3: one adapter instance serves exactly one model; two models
    # means two VllmTextBackend instances, each with its own runtime.
    backend_a, made_a = _backend_with_stubs()
    backend_b, made_b = _backend_with_stubs()

    async def scenario() -> None:
        await backend_a.acquire(_PLAN)
        await backend_b.acquire(_PLAN)

    asyncio.run(scenario())

    assert len(made_a) == 1
    assert len(made_b) == 1
    assert made_a[0] is not made_b[0]
