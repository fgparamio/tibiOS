"""Rerank execution — batch query+documents in, scored results out, no
streaming. Mirrors `EmbeddingBackend`'s shape (design decision D4's
residency-only commonality applies identically here: a rerank call is
one batched scoring pass, not a token stream).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from tibios_ray.backends.adapter import BackendAdapter, BackendSession


@dataclass(frozen=True, slots=True, kw_only=True)
class RerankResult:
    """A scored document — `index` refers back into the original
    `documents` sequence passed to `rerank`."""

    index: int
    score: float


class RerankBackend(BackendAdapter, Protocol):
    """Batch document reranking over an acquired `BackendSession`. One
    `RerankResult` per input document, no streaming."""

    async def rerank(
        self, session: BackendSession, query: str, documents: Sequence[str]
    ) -> Sequence[RerankResult]: ...
