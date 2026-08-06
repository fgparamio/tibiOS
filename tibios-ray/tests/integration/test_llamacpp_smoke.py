"""Opt-in integration smoke test for `LlamaCppTextBackend` against the
real `llama_cpp` SDK and a real GGUF file — design.md's own admission
that "the stubbed seam cannot prove the real SDK signature" (Testing
Strategy, Integration row). Skipped unless `TIBIOS_RAY_LLAMACPP_GGUF`
points at a real `.gguf` file on disk.

Uses only `LlamaCppTextBackend`'s public constructor (with the module's
real `default_llama_factory` — no override), `acquire()`, `generate()`,
`release()`. No `llama_cpp` import here, so this module type-checks
whether or not the `llamacpp` optional extra (`pyproject.toml`) is
installed (design decision LC11) — only *running* it (not collecting
or type-checking it) requires the extra and a real model file.
"""

import asyncio
import os

import pytest

from tibios_ray.backends.adapter import BackendId
from tibios_ray.backends.text import TextChunk, TextRequest
from tibios_ray.engines.llamacpp import LLAMA_CPP_BACKEND_ID, LlamaCppTextBackend

_GGUF_PATH = os.environ.get("TIBIOS_RAY_LLAMACPP_GGUF")

pytestmark = pytest.mark.skipif(
    _GGUF_PATH is None,
    reason=(
        "set TIBIOS_RAY_LLAMACPP_GGUF to a real .gguf file path to run this "
        "opt-in integration test against the real llama_cpp SDK"
    ),
)


class _Plan:
    """Minimal `ServingPlanLike` — this test targets boundary ③→④ only
    (design.md), so it needs nothing beyond `.backend`."""

    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


_PLAN = _Plan(LLAMA_CPP_BACKEND_ID)


def _backend() -> LlamaCppTextBackend:
    assert _GGUF_PATH is not None  # narrowed for pyright; guaranteed by skipif
    return LlamaCppTextBackend(model_path=_GGUF_PATH)


async def _drain(backend: LlamaCppTextBackend, request: TextRequest) -> list[TextChunk]:
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


def test_generate_honors_stop_string() -> None:
    backend = _backend()
    # A space is near-certain to appear early in any coherent
    # multi-word completion, so `stop=(" ",)` should truncate
    # generation well short of `max_tokens` and never itself appear in
    # the emitted text (llama.cpp excludes the matched stop string).
    request = TextRequest(prompt="Once upon a time,", max_tokens=64, stop=(" ",))

    chunks = asyncio.run(_drain(backend, request))

    text = "".join(chunk.text for chunk in chunks)
    assert " " not in text
    assert len(chunks) < 64


def test_release_completes_cleanly() -> None:
    backend = _backend()

    async def scenario() -> None:
        session = await backend.acquire(_PLAN)
        await backend.release(session)

    asyncio.run(scenario())
