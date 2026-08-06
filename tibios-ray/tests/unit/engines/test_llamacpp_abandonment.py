"""`llamacpp-text-backend` spec, Requirement "Non-Blocking Thread-Bridge
Streaming", scenario "Abandoning the stream mid-flight releases
resources" (design decisions LC5/LC7) — `aclose()` on a `generate()`
async generator must release the per-session lock without a consumer
draining or joining anything, and must cause the stub's own generator
body to unwind (not just the consumer's).

The stub is given far more tokens than the bounded queue's `maxsize`
(8, `_QUEUE_MAXSIZE` in `llamacpp.py`) so that, after the consumer
reads exactly one chunk and stops, the pump thread is *structurally
guaranteed* to still be mid-stream — parked in `_put`'s backpressure
polling loop, not naturally exhausted — when `aclose()` runs. That is
what actually exercises LC7's `stop_event` polling self-termination,
as opposed to a coincidence of the stream finishing on its own.
"""

import asyncio
from collections.abc import AsyncGenerator
from typing import cast

from stub_llama import StubLlama

from tibios_ray.backends.adapter import BackendId, BackendSession
from tibios_ray.backends.text import TextChunk, TextRequest
from tibios_ray.engines.llamacpp import LlamaCppTextBackend


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


_PLAN = _Plan(BackendId("llama_cpp"))

# Comfortably larger than `_QUEUE_MAXSIZE` (8) plus the one-token
# lookahead buffer, so the queue is guaranteed to fill and the pump
# thread is guaranteed to still be producing (parked in `_put`) when
# the consumer stops after its first chunk — by construction, not by
# timing.
_MANY_TOKENS = tuple(f"t{i}" for i in range(30))


def test_abandon_releases_lock() -> None:
    stub = StubLlama(tokens=_MANY_TOKENS)
    backend = LlamaCppTextBackend(model_path="model.gguf", factory=lambda path: stub)

    async def scenario() -> tuple[TextChunk, bool, list[TextChunk]]:
        session = await backend.acquire(_PLAN)
        request = TextRequest(prompt="hi", max_tokens=len(_MANY_TOKENS))

        # `generate()`'s Protocol return type is the narrower
        # `AsyncIterator[TextChunk]` (no `aclose()`), but the concrete
        # implementation is an async generator function — `cast`, not
        # `# type: ignore`, expresses that without risking
        # `reportUnnecessaryTypeIgnoreComment` (LC11's pincer, same
        # reasoning as `default_llama_factory`'s lazy import).
        agen = cast(
            "AsyncGenerator[TextChunk, None]", backend.generate(session, request)
        )
        first = await agen.__anext__()
        await agen.aclose()

        # (b) the stub's underlying generator's `finally` actually ran —
        # not merely that the consumer's async generator returned.
        stub_closed = await asyncio.to_thread(stub.closed.wait, 1.0)

        # (a) the lock was actually released, not deadlocked: a fresh
        # generate() call on the *same* session must complete. The stub
        # ignores `max_tokens` (it is not the real SDK), so its token
        # sequence is swapped to something short and deterministic —
        # the same between-calls-mutation pattern used by
        # `test_llamacpp_streaming.py::test_exception_propagation` to
        # prove the session is reusable, not the exact same completion.
        stub.tokens = ("done",)
        follow_up_request = TextRequest(prompt="hi", max_tokens=1)
        follow_up_chunks = await asyncio.wait_for(
            _drain(backend, session, follow_up_request), timeout=2.0
        )
        return first, stub_closed, follow_up_chunks

    first, stub_closed, follow_up_chunks = asyncio.run(scenario())

    assert first == TextChunk(text="t0", finished=False)
    assert stub_closed is True
    assert follow_up_chunks == [TextChunk(text="done", finished=True)]


async def _drain(
    backend: LlamaCppTextBackend, session: BackendSession, request: TextRequest
) -> list[TextChunk]:
    return [chunk async for chunk in backend.generate(session, request)]
