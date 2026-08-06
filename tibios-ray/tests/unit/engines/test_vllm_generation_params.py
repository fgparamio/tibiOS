"""`vllm-text-backend` spec, design decisions VL8/VL9 — the
`sampling_params_factory` seam is wired into `generate()`: the factory
receives the `TextRequest` verbatim and the resulting params object
reaches `engine.generate()` untouched, alongside an unmodified prompt.
Plus the consumer-side proof that VL9's `DELTA` requirement actually
matters: concatenating every yielded `TextChunk.text` reproduces the
stub's own deltas exactly (a `CUMULATIVE` bug would make this quadratic
and unequal).
"""

import asyncio

from stub_async_llm import StubAsyncLLM, StubCompletionOutput, StubRequestOutput

from tibios_ray.backends.adapter import BackendId
from tibios_ray.backends.text import TextChunk, TextRequest
from tibios_ray.engines.vllm import VllmTextBackend


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


_PLAN = _Plan(BackendId("vllm"))


def _backend_with_stub(
    outputs: tuple[StubRequestOutput, ...], recorded_requests: list[TextRequest]
) -> VllmTextBackend:
    async def factory(model: str) -> StubAsyncLLM:
        return StubAsyncLLM(outputs=outputs)

    def params_factory(request: TextRequest) -> dict[str, object]:
        recorded_requests.append(request)
        return {"max_tokens": request.max_tokens, "temperature": request.temperature}

    return VllmTextBackend(
        model="m", engine_factory=factory, sampling_params_factory=params_factory
    )


def test_parameter_mapping_reaches_factory_verbatim_and_prompt_is_unmodified() -> None:
    stub_holder: list[StubAsyncLLM] = []

    async def factory(model: str) -> StubAsyncLLM:
        stub = StubAsyncLLM(outputs=(StubRequestOutput(outputs=(), finished=True),))
        stub_holder.append(stub)
        return stub

    recorded_requests: list[TextRequest] = []
    sentinel_params: dict[str, object] = {"sentinel": True}

    def params_factory(request: TextRequest) -> dict[str, object]:
        recorded_requests.append(request)
        return sentinel_params

    backend = VllmTextBackend(
        model="m", engine_factory=factory, sampling_params_factory=params_factory
    )
    request = TextRequest(
        prompt="translate: hola", max_tokens=42, temperature=0.3, stop=("</s>", "\n\n")
    )

    async def scenario() -> None:
        session = await backend.acquire(_PLAN)
        async for _ in backend.generate(session, request):
            pass

    asyncio.run(scenario())

    assert recorded_requests == [request]  # the factory received the request verbatim
    stub = stub_holder[0]
    assert stub.generate_calls == [
        {
            "prompt": "translate: hola",
            "sampling_params": sentinel_params,
            "request_id": stub.generate_calls[0]["request_id"],
        }
    ]


def test_concatenated_deltas_equal_the_stubs_own_deltas() -> None:
    outputs = (
        StubRequestOutput(outputs=(StubCompletionOutput(text="Hel"),), finished=False),
        StubRequestOutput(outputs=(StubCompletionOutput(text="lo, "),), finished=False),
        StubRequestOutput(outputs=(StubCompletionOutput(text="world"),), finished=True),
    )
    recorded_requests: list[TextRequest] = []
    backend = _backend_with_stub(outputs, recorded_requests)

    async def scenario() -> list[TextChunk]:
        session = await backend.acquire(_PLAN)
        request = TextRequest(prompt="hi", max_tokens=3)
        return [chunk async for chunk in backend.generate(session, request)]

    chunks = asyncio.run(scenario())

    # A CUMULATIVE bug would make each chunk carry the full text so
    # far ("Hel", "Hello, ", "Hello, world"); concatenating those would
    # duplicate content and not equal the stub's own delta stream.
    assert "".join(chunk.text for chunk in chunks) == "Hello, world"
    assert "".join(o.outputs[0].text for o in outputs) == "Hello, world"
