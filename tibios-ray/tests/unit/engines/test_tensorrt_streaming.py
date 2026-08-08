"""`tensorrt-llm-text-backend` spec, Requirement "Native-Async Streaming,
No Thread Bridge" (design decisions D35/D37) — `generate()` consumes the
handle `LLMLike.generate_async` returns directly via `async for`, with
no pump thread, bounded queue, or polling loop bridging it to the event
loop, mirroring `test_vllm_streaming.py`.

The one genuinely different thing under test here, D37: the SDK's
incremental token lives in `CompletionOutputLike.text_diff`, a separate
field from `.text` (cumulative) — never modeled on
`RequestOutputLike`/`CompletionOutputLike`'s own Protocol, but present
as an *extra* attribute on the stub (`stub_trtllm.py`'s
"cumulative-`.text` stub") so a regression that reads `.text` instead of
`text_diff` fails loudly (either an `AttributeError`, since the real
Protocol never promises `.text` exists, or a wrong, quadratically
duplicated value if the stub happens to expose one).

Tests inject their own `sampling_params_factory` so none of this depends
on `default_sampling_params_factory`.
"""

import asyncio

from stub_trtllm import StubLLM, StubRequestOutput

from tibios_ray.backends.adapter import BackendId, BackendSession
from tibios_ray.backends.text import TextChunk, TextRequest
from tibios_ray.engines.tensorrt import TensorrtLlmTextBackend


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


_PLAN = _Plan(BackendId("tensorrt_llm"))


def _no_op_params_factory(request: TextRequest) -> object:
    return object()


def _backend_with_stub(
    output: StubRequestOutput,
) -> tuple[TensorrtLlmTextBackend, list[StubLLM]]:
    made: list[StubLLM] = []

    async def factory(engine_path: str) -> StubLLM:
        stub = StubLLM(model=engine_path)
        stub.queue_output(output)
        made.append(stub)
        return stub

    backend = TensorrtLlmTextBackend(
        engine_path="/engines/m",
        engine_factory=factory,
        sampling_params_factory=_no_op_params_factory,
    )
    return backend, made


async def _drain(
    backend: TensorrtLlmTextBackend, session: BackendSession, request: TextRequest
) -> list[TextChunk]:
    return [chunk async for chunk in backend.generate(session, request)]


def test_generate_streams_stub_diffs_in_production_order() -> None:
    output = StubRequestOutput(diffs=("a", "b", "c"))
    backend, _ = _backend_with_stub(output)

    async def scenario() -> list[TextChunk]:
        session = await backend.acquire(_PLAN)
        return await _drain(backend, session, TextRequest(prompt="hi", max_tokens=3))

    chunks = asyncio.run(scenario())
    assert chunks == [
        TextChunk(text="a", finished=False),
        TextChunk(text="b", finished=False),
        TextChunk(text="c", finished=True),
    ]
    # D37: emitted chunks concatenate to the cumulative text exactly
    # once — not the quadratic duplication reading `.text` would cause.
    assert "".join(chunk.text for chunk in chunks) == "abc"


def test_generate_reads_text_diff_never_text() -> None:
    # The trap: the stub's `.text` (cumulative) grows to "aab"-shaped
    # duplication territory if ever read in place of `text_diff` — the
    # exact bug D37 exists to prevent. Concatenating the diffs the
    # adapter emitted must equal the diffs supplied, not the (much
    # longer) cumulative `.text` values the stub also carries.
    output = StubRequestOutput(diffs=("Hello", ", ", "world"))
    backend, _ = _backend_with_stub(output)

    async def scenario() -> list[TextChunk]:
        session = await backend.acquire(_PLAN)
        return await _drain(backend, session, TextRequest(prompt="hi", max_tokens=3))

    chunks = asyncio.run(scenario())
    assert [chunk.text for chunk in chunks] == ["Hello", ", ", "world"]
    assert "".join(chunk.text for chunk in chunks) == "Hello, world"


def test_generate_call_path_has_no_thread_queue_polling_or_grpc() -> None:
    # Static proof, not a runtime one: mirrors
    # `test_vllm_streaming.py::test_generate_call_path_has_no_thread_or_queue_or_polling`.
    import inspect

    from tibios_ray.engines.tensorrt import TensorrtLlmTextBackend as _Backend

    source = inspect.getsource(_Backend.generate)
    for forbidden in ("Thread", "asyncio.Queue", "while True", "poll", "grpc"):
        assert forbidden not in source, f"{forbidden!r} found in generate() source"


def test_terminal_semantics_single_finished_output() -> None:
    output = StubRequestOutput(diffs=("only",))
    backend, _ = _backend_with_stub(output)

    async def scenario() -> list[TextChunk]:
        session = await backend.acquire(_PLAN)
        return await _drain(backend, session, TextRequest(prompt="hi", max_tokens=1))

    chunks = asyncio.run(scenario())
    assert chunks == [TextChunk(text="only", finished=True)]


def test_terminal_semantics_exhaustion_without_finished_synthesizes_terminator() -> None:
    # VL10's defensive rule inherited: a handle that never sets
    # finished=True still produces exactly one synthetic
    # TextChunk("", finished=True) once exhausted.
    output = StubRequestOutput(diffs=("a",), finished_at_exhaustion=False)
    backend, _ = _backend_with_stub(output)

    async def scenario() -> list[TextChunk]:
        session = await backend.acquire(_PLAN)
        return await _drain(backend, session, TextRequest(prompt="hi", max_tokens=1))

    chunks = asyncio.run(scenario())
    assert chunks == [
        TextChunk(text="a", finished=False),
        TextChunk(text="", finished=True),
    ]


def test_terminal_semantics_drops_empty_non_terminal_delta() -> None:
    output = StubRequestOutput(diffs=("a", "", "b"))
    backend, _ = _backend_with_stub(output)

    async def scenario() -> list[TextChunk]:
        session = await backend.acquire(_PLAN)
        return await _drain(backend, session, TextRequest(prompt="hi", max_tokens=3))

    chunks = asyncio.run(scenario())
    assert chunks == [
        TextChunk(text="a", finished=False),
        TextChunk(text="b", finished=True),
    ]


def test_generate_only_yields_text_chunk_values() -> None:
    output = StubRequestOutput(diffs=("a", "b"))
    backend, _ = _backend_with_stub(output)

    async def scenario() -> list[TextChunk]:
        session = await backend.acquire(_PLAN)
        return await _drain(backend, session, TextRequest(prompt="hi", max_tokens=2))

    chunks = asyncio.run(scenario())
    assert all(isinstance(chunk, TextChunk) for chunk in chunks)
