"""Backend Adapter contract — the engine-agnostic boundary Capability
Providers execute against (`backend-adapter` spec).

See ``openspec/changes/ray-worker-runtime/design.md`` (design decision
D4). This package has zero dependency on ``selection/``,
``capabilities/``, or ``runtime/`` — those layers depend on
``backends/``, never the reverse.
"""

from tibios_ray.backends.adapter import BackendAdapter, BackendId, BackendSession
from tibios_ray.backends.embedding import EmbeddingBackend, Vector
from tibios_ray.backends.rerank import RerankBackend, RerankResult
from tibios_ray.backends.speech import AudioRef, TranscriptionBackend, TranscriptSegment
from tibios_ray.backends.text import TextChunk, TextGenerationBackend, TextRequest

__all__ = [
    "AudioRef",
    "BackendAdapter",
    "BackendId",
    "BackendSession",
    "EmbeddingBackend",
    "RerankBackend",
    "RerankResult",
    "TextChunk",
    "TextGenerationBackend",
    "TextRequest",
    "TranscriptionBackend",
    "TranscriptSegment",
    "Vector",
]
