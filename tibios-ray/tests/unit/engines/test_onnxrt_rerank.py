"""`onnxruntime-backend` spec, Requirement "rerank() Returns One Scored
Result Per Document With a Valid Back-Reference" (OR9) — plus design
decision OR6 (the query is paired with every document via
`TokenizerLike.text_pair`, making cross-encoder rerank possible).
"""

import asyncio

from stub_onnx import make_stub_session_factory, make_stub_tokenizer_factory

from tibios_ray.backends.adapter import BackendId
from tibios_ray.backends.rerank import RerankResult
from tibios_ray.engines.onnxrt import ONNXRUNTIME_BACKEND_ID, OnnxRerankBackend


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


_PLAN = _Plan(ONNXRUNTIME_BACKEND_ID)


def _backend(*, outputs):
    # `outputs` here is the [batch, 1] score matrix a cross-encoder
    # produces; `session.run()` returns a *list of output tensors*, so
    # the stub wraps it once more — `outputs[0]` (read by `_infer`) is
    # this matrix itself.
    session_factory, sessions = make_stub_session_factory(
        input_names=("input_ids",), outputs=[outputs]
    )
    tokenizer_factory, tokenizers = make_stub_tokenizer_factory(
        encoded={"input_ids": [[1]] * len(outputs)}
    )
    backend = OnnxRerankBackend(
        model_path="model.onnx",
        tokenizer_path="tok",
        session_factory=session_factory,
        tokenizer_factory=tokenizer_factory,
    )
    return backend, sessions, tokenizers


def test_rerank_pairs_the_query_with_every_document() -> None:
    backend, _sessions, tokenizers = _backend(outputs=[[0.9], [0.1], [0.5]])
    documents = ["doc-a", "doc-b", "doc-c"]

    async def scenario() -> None:
        session = await backend.acquire(_PLAN)
        await backend.rerank(session, "query", documents)

    asyncio.run(scenario())

    call = tokenizers[0].call_args[0]
    assert call["text"] == ["query", "query", "query"]
    assert call["text_pair"] == documents


def test_rerank_returns_one_result_per_document_with_index_and_score() -> None:
    backend, _sessions, _ = _backend(outputs=[[0.9], [0.1], [0.5]])
    documents = ["doc-a", "doc-b", "doc-c"]

    async def scenario() -> list[RerankResult]:
        session = await backend.acquire(_PLAN)
        return list(await backend.rerank(session, "query", documents))

    result = asyncio.run(scenario())

    assert result == [
        RerankResult(index=0, score=0.9),
        RerankResult(index=1, score=0.1),
        RerankResult(index=2, score=0.5),
    ]


def test_rerank_result_indices_are_a_permutation_of_0_to_n_minus_1() -> None:
    backend, _sessions, _ = _backend(outputs=[[0.2], [0.8], [0.4], [0.6]])
    documents = ["d0", "d1", "d2", "d3"]

    async def scenario() -> list[RerankResult]:
        session = await backend.acquire(_PLAN)
        return list(await backend.rerank(session, "q", documents))

    result = asyncio.run(scenario())

    assert sorted(item.index for item in result) == [0, 1, 2, 3]
    for item in result:
        assert documents[item.index] == f"d{item.index}"


def test_empty_documents_returns_empty_result_and_never_calls_run() -> None:
    backend, sessions, _ = _backend(outputs=[[0.5]])

    async def scenario() -> list[RerankResult]:
        session = await backend.acquire(_PLAN)
        return list(await backend.rerank(session, "q", []))

    result = asyncio.run(scenario())

    assert result == []
    assert sessions[0].run_calls == []
