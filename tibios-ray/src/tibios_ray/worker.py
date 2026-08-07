"""Composition root for the tibios-ray Worker Contract entity.

This is the single place inside tibios-ray where "Worker" refers to the
entity seen by tibios-core's Runtime over gRPC (per
``../tibios-core/docs/architecture/18-worker-model.md``). It builds a
:class:`tibios_ray.runtime.registry.CapabilityRegistry` from the seven
concrete Capability Providers and hands it to exactly one
:class:`tibios_ray.runtime.worker_runtime.WorkerRuntime` — the whole
composition ``server.py`` needs before it can call
``transport.serve(build_runtime(), address)``. Imports zero ``grpc``/
``_pb2`` symbol (design decision D13); the gRPC transport that calls into
this composition lives entirely in ``transport/``.
"""

from tibios_ray.capabilities.chat import ChatProvider
from tibios_ray.capabilities.embedding import EmbeddingProvider
from tibios_ray.capabilities.ocr import OcrProvider
from tibios_ray.capabilities.rerank import RerankProvider
from tibios_ray.capabilities.speech import SpeechSynthesisProvider, SpeechTranscriptionProvider
from tibios_ray.capabilities.vision import VisionProvider
from tibios_ray.runtime.registry import CapabilityRegistry
from tibios_ray.runtime.worker_runtime import WorkerRuntime


def build_runtime() -> WorkerRuntime:
    """Builds the one `CapabilityRegistry` from the seven Capability
    Providers and hands it to the one `WorkerRuntime`."""
    providers = (
        ChatProvider(),
        EmbeddingProvider(),
        OcrProvider(),
        RerankProvider(),
        SpeechTranscriptionProvider(),
        SpeechSynthesisProvider(),
        VisionProvider(),
    )
    return WorkerRuntime(CapabilityRegistry(providers))
