"""Opt-in integration smoke test for `TensorrtLlmTextBackend` against the
real `tensorrt_llm` SDK and a real precompiled engine artifact —
design.md's own admission that "the stubbed seam cannot prove the real
SDK signature" (Testing Strategy, Integration row). Skipped unless
`TIBIOS_RAY_TENSORRT_ENGINE_PATH` points at a real, precompiled
TensorRT-LLM engine directory.

Uses only `TensorrtLlmTextBackend`'s public constructor (with the
module's real `default_engine_factory`/`default_sampling_params_factory`
— no override), `acquire()`, `generate()`, `release()`. No `tensorrt_llm`
import here, so this module type-checks whether or not the `tensorrt`
optional extra (`pyproject.toml`) is installed (design decision LC11
inherited via VL8) — only *running* it (not collecting or type-checking
it) requires the extra, a GPU, and a real precompiled engine.
"""

import asyncio
import os
from collections.abc import AsyncGenerator
from typing import cast

import pytest

from tibios_ray.backends.adapter import BackendId, BackendSession
from tibios_ray.backends.text import TextChunk, TextRequest
from tibios_ray.engines.tensorrt import TENSORRT_LLM_BACKEND_ID, TensorrtLlmTextBackend

_ENGINE_PATH = os.environ.get("TIBIOS_RAY_TENSORRT_ENGINE_PATH")

pytestmark = pytest.mark.skipif(
    _ENGINE_PATH is None,
    reason=(
        "set TIBIOS_RAY_TENSORRT_ENGINE_PATH to a real precompiled "
        "TensorRT-LLM engine directory to run this opt-in integration "
        "test against the real tensorrt_llm SDK"
    ),
)


class _Plan:
    """Minimal `ServingPlanLike` — this test targets boundary ③→④ only
    (design.md), so it needs nothing beyond `.backend`."""

    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


_PLAN = _Plan(TENSORRT_LLM_BACKEND_ID)


def _backend() -> TensorrtLlmTextBackend:
    assert _ENGINE_PATH is not None  # narrowed for pyright; guaranteed by skipif
    return TensorrtLlmTextBackend(engine_path=_ENGINE_PATH)


async def _drain(backend: TensorrtLlmTextBackend, request: TextRequest) -> list[TextChunk]:
    session = await backend.acquire(_PLAN)
    try:
        return [chunk async for chunk in backend.generate(session, request)]
    finally:
        await backend.release(session)


def test_generate_yields_multiple_chunks_with_one_terminal_chunk() -> None:
    backend = _backend()
    request = TextRequest(prompt="Once upon a time,", max_tokens=16)

    chunks = asyncio.run(_drain(backend, request))

    assert len(chunks) >= 2
    finished_flags = [chunk.finished for chunk in chunks]
    assert finished_flags.count(True) == 1
    assert finished_flags[-1] is True


def test_generate_honors_max_tokens() -> None:
    backend = _backend()
    max_tokens = 8
    request = TextRequest(prompt="Once upon a time,", max_tokens=max_tokens)

    chunks = asyncio.run(_drain(backend, request))

    assert len(chunks) <= max_tokens


def test_two_sessions_share_one_engine() -> None:
    backend = _backend()

    async def scenario() -> None:
        session_a = await backend.acquire(_PLAN)
        session_b = await backend.acquire(_PLAN)
        try:
            request = TextRequest(prompt="Once upon a time,", max_tokens=8)
            chunks_a, chunks_b = await asyncio.gather(
                _consume(backend, session_a, request),
                _consume(backend, session_b, request),
            )
            assert chunks_a
            assert chunks_b
        finally:
            await backend.release(session_a)
            await backend.release(session_b)

    async def _consume(
        backend: TensorrtLlmTextBackend, session: BackendSession, request: TextRequest
    ) -> list[TextChunk]:
        return [chunk async for chunk in backend.generate(session, request)]

    asyncio.run(scenario())


def test_mid_stream_abandonment_does_not_wedge_the_engine() -> None:
    backend = _backend()

    async def scenario() -> None:
        session = await backend.acquire(_PLAN)
        try:
            request = TextRequest(prompt="Once upon a time,", max_tokens=64)
            agen = cast(
                "AsyncGenerator[TextChunk, None]", backend.generate(session, request)
            )
            await agen.__anext__()
            await agen.aclose()

            # The engine must still be usable after an abandoned stream.
            follow_up_chunks = [
                chunk
                async for chunk in backend.generate(
                    session, TextRequest(prompt="Hello,", max_tokens=8)
                )
            ]
            assert follow_up_chunks
        finally:
            await backend.release(session)

    asyncio.run(scenario())


def test_release_completes_cleanly() -> None:
    backend = _backend()

    async def scenario() -> None:
        session = await backend.acquire(_PLAN)
        await backend.release(session)

    asyncio.run(scenario())
