"""`vllm-text-backend` spec, design decision VL14 — `request_id =
f"{session_id}:{uuid4().hex}"`: per-call uniqueness is mandatory
because a session may run several generations and vLLM multiplexes
strictly by `request_id`, so two live requests sharing one id would
cross-talk. `generate()` on a released or foreign session must raise
`UnknownSessionError` before it ever reaches the engine (LC2's
idempotent-by-rejection, inherited).
"""

import asyncio

import pytest
from stub_async_llm import StubAsyncLLM, StubRequestOutput

from tibios_ray.backends.adapter import BackendId, BackendSession
from tibios_ray.backends.text import TextRequest
from tibios_ray.engines.vllm import UnknownSessionError, VllmTextBackend


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


_PLAN = _Plan(BackendId("vllm"))


def test_two_generate_calls_on_one_session_get_two_distinct_prefixed_request_ids() -> None:
    stub_holder: list[StubAsyncLLM] = []

    async def factory(model: str) -> StubAsyncLLM:
        stub = StubAsyncLLM(outputs=(StubRequestOutput(outputs=(), finished=True),))
        stub_holder.append(stub)
        return stub

    backend = VllmTextBackend(
        model="m", engine_factory=factory, sampling_params_factory=lambda request: object()
    )

    async def scenario() -> list[str]:
        session = await backend.acquire(_PLAN)
        request = TextRequest(prompt="hi", max_tokens=1)
        async for _ in backend.generate(session, request):
            pass
        async for _ in backend.generate(session, request):
            pass
        return [call["request_id"] for call in stub_holder[0].generate_calls]

    request_ids = asyncio.run(scenario())

    assert len(request_ids) == 2
    assert request_ids[0] != request_ids[1]
    session_id_prefix = request_ids[0].rsplit(":", 1)[0]
    assert all(request_id.startswith(f"{session_id_prefix}:") for request_id in request_ids)


def test_generate_on_unknown_session_raises_before_touching_the_engine() -> None:
    stub_holder: list[StubAsyncLLM] = []

    async def factory(model: str) -> StubAsyncLLM:
        stub = StubAsyncLLM()
        stub_holder.append(stub)
        return stub

    backend = VllmTextBackend(
        model="m", engine_factory=factory, sampling_params_factory=lambda request: object()
    )
    foreign_session = BackendSession(backend_id=BackendId("vllm"), session_id="never-acquired")

    async def scenario() -> None:
        await backend.acquire(_PLAN)  # constructs the engine so generate_calls is meaningful
        request = TextRequest(prompt="hi", max_tokens=1)
        with pytest.raises(UnknownSessionError):
            async for _ in backend.generate(foreign_session, request):
                pass

    asyncio.run(scenario())

    assert stub_holder[0].generate_calls == []


def test_generate_on_released_session_raises() -> None:
    async def factory(model: str) -> StubAsyncLLM:
        return StubAsyncLLM()

    backend = VllmTextBackend(
        model="m", engine_factory=factory, sampling_params_factory=lambda request: object()
    )

    async def scenario() -> None:
        session = await backend.acquire(_PLAN)
        await backend.release(session)
        request = TextRequest(prompt="hi", max_tokens=1)
        with pytest.raises(UnknownSessionError):
            async for _ in backend.generate(session, request):
                pass

    asyncio.run(scenario())
