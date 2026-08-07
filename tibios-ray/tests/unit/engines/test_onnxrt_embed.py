"""`onnxruntime-backend` spec, Requirements "embed() Returns One
Order-Preserving Vector Per Input" (OR9) and "Injectable
InferenceSessionLike and Tokenizer Seams Enable SDK-Free Unit Testing"
— plus design decision OR8 (input filtering against the session's own
declared inputs). `embed()`'s hot path: tokenize -> filter feed against
`session.get_inputs()` -> `session.run()` -> extract rectangular 2-D
rows into `Vector`s, one per input, in order.
"""

import asyncio

import pytest
from stub_onnx import make_stub_session_factory, make_stub_tokenizer_factory

from tibios_ray.backends.adapter import BackendId
from tibios_ray.backends.embedding import Vector
from tibios_ray.engines.onnxrt import (
    ONNXRUNTIME_BACKEND_ID,
    OnnxEmbeddingBackend,
    OnnxOutputShapeError,
)


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


_PLAN = _Plan(ONNXRUNTIME_BACKEND_ID)


def _backend(*, input_names, outputs, encoded, **kwargs):
    session_factory, sessions = make_stub_session_factory(
        input_names=input_names, outputs=outputs
    )
    tokenizer_factory, tokenizers = make_stub_tokenizer_factory(encoded=encoded)
    backend = OnnxEmbeddingBackend(
        model_path="model.onnx",
        tokenizer_path="tok",
        session_factory=session_factory,
        tokenizer_factory=tokenizer_factory,
        **kwargs,
    )
    return backend, sessions, tokenizers


def test_feed_is_filtered_to_declared_input_names() -> None:
    # OR8: the tokenizer emits a key (`token_type_ids`) the graph never
    # declared — it must be dropped, not passed through verbatim.
    backend, sessions, _ = _backend(
        input_names=("input_ids", "attention_mask"),
        outputs=[[[0.1, 0.2]]],
        encoded={
            "input_ids": [[1, 2]],
            "attention_mask": [[1, 1]],
            "token_type_ids": [[0, 0]],
        },
    )

    async def scenario() -> None:
        session = await backend.acquire(_PLAN)
        await backend.embed(session, ["hello"])

    asyncio.run(scenario())

    feed = sessions[0].run_calls[0]["input_feed"]
    assert set(feed.keys()) == {"input_ids", "attention_mask"}


def test_declared_but_unemitted_input_is_absent_not_synthesized() -> None:
    # OR8's reverse case: the graph declares `position_ids`, but the
    # tokenizer never produced it — the feed must not synthesize it.
    backend, sessions, _ = _backend(
        input_names=("input_ids", "position_ids"),
        outputs=[[[0.1]]],
        encoded={"input_ids": [[1]]},
    )

    async def scenario() -> None:
        session = await backend.acquire(_PLAN)
        await backend.embed(session, ["hi"])

    asyncio.run(scenario())

    feed = sessions[0].run_calls[0]["input_feed"]
    assert set(feed.keys()) == {"input_ids"}
    assert "position_ids" not in feed


def test_embed_returns_one_vector_per_input_in_order_all_equal_length() -> None:
    backend, _sessions, _ = _backend(
        input_names=("input_ids",),
        outputs=[[[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]],
        encoded={"input_ids": [[1], [2], [3]]},
    )

    async def scenario() -> list[Vector]:
        session = await backend.acquire(_PLAN)
        return list(await backend.embed(session, ["a", "b", "c"]))

    result = asyncio.run(scenario())

    assert result == [
        Vector(values=(0.1, 0.2)),
        Vector(values=(0.3, 0.4)),
        Vector(values=(0.5, 0.6)),
    ]
    assert len({len(vector.values) for vector in result}) == 1


def test_non_2d_output_raises_onnx_output_shape_error() -> None:
    # A 3-D `last_hidden_state`-shaped output — never pooled by design
    # (OR9) — must be refused, not silently misread.
    backend, _sessions, _ = _backend(
        input_names=("input_ids",),
        outputs=[[[[0.1, 0.2]], [[0.3, 0.4]]]],
        encoded={"input_ids": [[1], [2]]},
    )

    async def scenario() -> None:
        session = await backend.acquire(_PLAN)
        with pytest.raises(OnnxOutputShapeError):
            await backend.embed(session, ["a", "b"])

    asyncio.run(scenario())


def test_empty_input_returns_empty_result_and_never_calls_run() -> None:
    backend, sessions, _ = _backend(
        input_names=("input_ids",),
        outputs=[[[0.1]]],
        encoded={"input_ids": [[1]]},
    )

    async def scenario() -> list[Vector]:
        session = await backend.acquire(_PLAN)
        return list(await backend.embed(session, []))

    result = asyncio.run(scenario())

    assert result == []
    assert sessions[0].run_calls == []
