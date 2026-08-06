"""Text generation execution — the Chat/Reasoning capability's
engine-facing contract (llama.cpp, vLLM, TensorRT-LLM in Phase 4).

Streaming: sampling parameters in, a token/chunk stream out. Modeled as
a Protocol method returning `AsyncIterator[TextChunk]` (not a coroutine)
so a conforming backend implements it as an async generator function —
callers get the stream directly without an intermediate `await`.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from tibios_ray.backends.adapter import BackendAdapter, BackendSession


@dataclass(frozen=True, slots=True, kw_only=True)
class TextRequest:
    """Sampling parameters for one text-generation call."""

    prompt: str
    max_tokens: int
    temperature: float = 1.0
    stop: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class TextChunk:
    """One unit of a streamed text-generation response."""

    text: str
    finished: bool = False


class TextGenerationBackend(BackendAdapter, Protocol):
    """Streaming text generation over an acquired `BackendSession`."""

    def generate(
        self, session: BackendSession, request: TextRequest
    ) -> AsyncIterator[TextChunk]: ...
