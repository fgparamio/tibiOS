"""Opt-in integration smoke test for `OnnxEmbeddingBackend`/
`OnnxRerankBackend` against the real `onnxruntime`/`transformers` SDKs
and real model files — design.md's own admission that "the stub cannot
prove the real SDK signature" (Testing Strategy, Integration row).
Skipped unless `TIBIOS_RAY_ONNX_MODEL` and `TIBIOS_RAY_ONNX_TOKENIZER`
both point at a real `.onnx` model file and a real tokenizer
path/repo id.

Uses only the public constructors (with the module's real
`default_session_factory`/`default_tokenizer_factory` — no override),
`acquire()`, `embed()`/`rerank()`, `release()`. No `onnxruntime` or
`transformers` import here, so this module type-checks whether or not
the `onnx` optional extra (`pyproject.toml`) is installed (design
decision LC11/VL8 inherited) — only *running* it (not collecting or
type-checking it) requires the extra and real artifacts.

The two concurrent `embed()` calls in
`test_concurrent_embeds_on_one_shared_session_match_serial_results` are
OR3/OR4's empirical discharge in this environment: the module docstring
cites the ONNX Runtime maintainer discussions that document shared-
session `Run()` concurrency as safe; this test is the local proof that
holds for whatever model/EP combination the operator points it at.
"""

import asyncio
import os

import pytest

from tibios_ray.backends.adapter import BackendId
from tibios_ray.backends.embedding import Vector
from tibios_ray.backends.rerank import RerankResult
from tibios_ray.engines.onnxrt import (
    ONNXRUNTIME_BACKEND_ID,
    OnnxEmbeddingBackend,
    OnnxRerankBackend,
)

_MODEL_PATH = os.environ.get("TIBIOS_RAY_ONNX_MODEL")
_TOKENIZER_PATH = os.environ.get("TIBIOS_RAY_ONNX_TOKENIZER")

pytestmark = pytest.mark.skipif(
    _MODEL_PATH is None or _TOKENIZER_PATH is None,
    reason=(
        "set TIBIOS_RAY_ONNX_MODEL to a real .onnx model file and "
        "TIBIOS_RAY_ONNX_TOKENIZER to a real tokenizer path/repo id to run "
        "this opt-in integration test against the real onnxruntime/"
        "transformers SDKs"
    ),
)


class _Plan:
    """Minimal `ServingPlanLike` — this test targets boundary ③→④ only
    (design.md), so it needs nothing beyond `.backend`."""

    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


_PLAN = _Plan(ONNXRUNTIME_BACKEND_ID)


def _embedding_backend() -> OnnxEmbeddingBackend:
    assert _MODEL_PATH is not None  # narrowed for pyright; guaranteed by skipif
    assert _TOKENIZER_PATH is not None
    return OnnxEmbeddingBackend(model_path=_MODEL_PATH, tokenizer_path=_TOKENIZER_PATH)


def _rerank_backend() -> OnnxRerankBackend:
    assert _MODEL_PATH is not None
    assert _TOKENIZER_PATH is not None
    return OnnxRerankBackend(model_path=_MODEL_PATH, tokenizer_path=_TOKENIZER_PATH)


def test_embed_returns_equal_length_vectors_for_each_input() -> None:
    backend = _embedding_backend()
    texts = ["the quick brown fox", "jumps over the lazy dog", "hello world"]

    async def scenario() -> list[Vector]:
        session = await backend.acquire(_PLAN)
        try:
            return list(await backend.embed(session, texts))
        finally:
            await backend.release(session)

    vectors = asyncio.run(scenario())

    assert len(vectors) == len(texts)
    assert len({len(vector.values) for vector in vectors}) == 1


def test_rerank_returns_one_ordered_result_per_document() -> None:
    backend = _rerank_backend()
    documents = ["a red apple", "a fast car", "a slow turtle"]

    async def scenario() -> list[RerankResult]:
        session = await backend.acquire(_PLAN)
        try:
            return list(await backend.rerank(session, "fruit", documents))
        finally:
            await backend.release(session)

    results = asyncio.run(scenario())

    assert sorted(result.index for result in results) == list(range(len(documents)))
    for result in results:
        assert 0 <= result.index < len(documents)


def test_concurrent_embeds_on_one_shared_session_match_serial_results() -> None:
    backend = _embedding_backend()
    texts_a = ["first batch text one", "first batch text two"]
    texts_b = ["second batch text one", "second batch text two"]

    async def scenario() -> tuple[list[Vector], list[Vector], list[Vector], list[Vector]]:
        session_a = await backend.acquire(_PLAN)
        session_b = await backend.acquire(_PLAN)
        try:
            serial_a = list(await backend.embed(session_a, texts_a))
            serial_b = list(await backend.embed(session_b, texts_b))

            concurrent_a, concurrent_b = await asyncio.gather(
                backend.embed(session_a, texts_a),
                backend.embed(session_b, texts_b),
            )
            return serial_a, serial_b, list(concurrent_a), list(concurrent_b)
        finally:
            await backend.release(session_a)
            await backend.release(session_b)

    serial_a, serial_b, concurrent_a, concurrent_b = asyncio.run(scenario())

    assert concurrent_a == serial_a
    assert concurrent_b == serial_b


def test_release_completes_cleanly() -> None:
    backend = _embedding_backend()

    async def scenario() -> None:
        session = await backend.acquire(_PLAN)
        await backend.release(session)

    asyncio.run(scenario())
