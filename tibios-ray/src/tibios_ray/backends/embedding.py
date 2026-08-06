"""Embedding execution — batch text in, fixed-shape vectors out, no
streaming (ONNX Runtime in Phase 4). Distinct from `TextGenerationBackend`
per design decision D4: embedding has no token stream, no sampling
parameters, no KV cache.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from tibios_ray.backends.adapter import BackendAdapter, BackendSession


@dataclass(frozen=True, slots=True, kw_only=True)
class Vector:
    """A fixed-shape embedding vector."""

    values: tuple[float, ...]


class EmbeddingBackend(BackendAdapter, Protocol):
    """Batch embedding over an acquired `BackendSession`. One vector per
    input, no streaming."""

    async def embed(
        self, session: BackendSession, inputs: Sequence[str]
    ) -> Sequence[Vector]: ...
