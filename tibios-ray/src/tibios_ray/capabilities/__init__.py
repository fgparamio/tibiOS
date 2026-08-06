"""Capability Provider contract (`capability-registry` spec).

See ``openspec/changes/ray-worker-runtime/design.md`` ("capabilities/"
block, design decision D2). This package depends on ``execution/`` (for
`ExecutionContext`/`ExecutionReport`) and ``backends/`` (for
`BackendId`) only — ``runtime/`` depends on ``capabilities/``, never the
reverse.
"""

from tibios_ray.capabilities.chat import ChatProvider
from tibios_ray.capabilities.descriptor import (
    CapabilityCatalog,
    CapabilityDescriptor,
    CapabilityFlags,
    ModelFamily,
)
from tibios_ray.capabilities.embedding import EmbeddingProvider
from tibios_ray.capabilities.errors import NoBackendAvailableError
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.capabilities.ocr import OcrProvider
from tibios_ray.capabilities.provider import CapabilityProvider
from tibios_ray.capabilities.rerank import RerankProvider
from tibios_ray.capabilities.speech import SpeechSynthesisProvider, SpeechTranscriptionProvider
from tibios_ray.capabilities.vision import VisionProvider

__all__ = [
    "CapabilityCatalog",
    "CapabilityDescriptor",
    "CapabilityFlags",
    "CapabilityName",
    "CapabilityProvider",
    "ChatProvider",
    "EmbeddingProvider",
    "ModelFamily",
    "NoBackendAvailableError",
    "OcrProvider",
    "RerankProvider",
    "SpeechSynthesisProvider",
    "SpeechTranscriptionProvider",
    "VisionProvider",
]
