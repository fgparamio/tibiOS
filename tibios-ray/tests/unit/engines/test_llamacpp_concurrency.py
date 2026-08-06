"""`llamacpp-text-backend` spec, Requirement "Per-Session Lock
Serializes Only Calls Sharing That Session" (design decision LC4) —
both scenarios, made deterministic by structure rather than timing:

- `test_serializes_within_session`: an enter/exit marker log plus a
  live reentrancy counter on a single `StubLlama` proves two
  concurrent `generate()` calls on *one* session never run their
  underlying token streams interleaved.
- `test_independence_across_sessions`: a `threading.Barrier(2, ...)`
  shared by two distinct `StubLlama` instances (two distinct sessions)
  proves the lock is per-session, not global/per-process — a global
  lock would prevent the second session's stub from ever reaching the
  barrier, so the barrier would time out and the test would fail.
"""

import asyncio
import threading

from stub_llama import StubLlama

from tibios_ray.backends.adapter import BackendId, BackendSession
from tibios_ray.backends.text import TextChunk, TextRequest
from tibios_ray.engines.llamacpp import LlamaCppTextBackend


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


_PLAN = _Plan(BackendId("llama_cpp"))


async def _drain(
    backend: LlamaCppTextBackend, session: BackendSession, request: TextRequest
) -> list[TextChunk]:
    return [chunk async for chunk in backend.generate(session, request)]


def test_serializes_within_session() -> None:
    stub = StubLlama(tokens=("only",))
    backend = LlamaCppTextBackend(model_path="model.gguf", factory=lambda path: stub)

    async def scenario() -> list[list[TextChunk]]:
        session = await backend.acquire(_PLAN)
        request = TextRequest(prompt="hi", max_tokens=1)

        # `asyncio.gather` always returns a `list` at runtime; typeshed's
        # tuple-overload return type is a static-only convenience —
        # `list(...)` reconciles both without a type: ignore comment.
        return list(
            await asyncio.wait_for(
                asyncio.gather(
                    _drain(backend, session, request),
                    _drain(backend, session, request),
                ),
                timeout=5.0,
            )
        )

    results = asyncio.run(scenario())

    assert results == [
        [TextChunk(text="only", finished=True)],
        [TextChunk(text="only", finished=True)],
    ]
    # The two `create_completion()` calls' bodies never ran concurrently:
    # each fully entered and exited before the other's body started.
    assert stub.activity_log == [
        ("stub", "enter"),
        ("stub", "exit"),
        ("stub", "enter"),
        ("stub", "exit"),
    ]
    assert stub.max_active_count <= 1


def test_independence_across_sessions() -> None:
    barrier = threading.Barrier(2, timeout=5.0)
    stubs: list[StubLlama] = []

    def factory(model_path: str) -> StubLlama:
        stub = StubLlama(tokens=("ok",), barrier=barrier, marker=f"stub-{len(stubs)}")
        stubs.append(stub)
        return stub

    backend = LlamaCppTextBackend(model_path="model.gguf", factory=factory)

    async def scenario() -> list[list[TextChunk]]:
        session_a = await backend.acquire(_PLAN)
        session_b = await backend.acquire(_PLAN)
        request = TextRequest(prompt="hi", max_tokens=1)

        # If the lock were global/per-process rather than per-session
        # (LC4), session B's generate() would never even start its
        # pump thread while session A holds the lock — A's stub would
        # then be alone at the barrier and time out after 5s, raising
        # BrokenBarrierError from inside generate(). A bounded outer
        # timeout keeps a genuine deadlock from hanging the test suite.
        return list(
            await asyncio.wait_for(
                asyncio.gather(
                    _drain(backend, session_a, request),
                    _drain(backend, session_b, request),
                ),
                timeout=10.0,
            )
        )

    results = asyncio.run(scenario())

    assert results == [
        [TextChunk(text="ok", finished=True)],
        [TextChunk(text="ok", finished=True)],
    ]
