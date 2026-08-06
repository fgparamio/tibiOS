"""The Speech Capability Providers (`capability-providers` spec:
Descriptor Catalog Correctness and Stability).

The only two-class module: `CapabilityDescriptor.capability` is
singular and the registry is one-provider-per-capability, so
transcription (`speech.transcribe`) and synthesis (`speech.synthesize`)
are two registrable Providers sharing one module (design.md "the only
two-class module"). Both are zero-field `@dataclass(frozen=True,
slots=True)` satisfying `CapabilityProvider` structurally — no base
class (design decision D1, CP1), same shape as `ChatProvider`/
`EmbeddingProvider`/`RerankProvider`/`VisionProvider`. `execute()`
raises `NoBackendAvailableError` unconditionally (`capability-providers`
spec: "Uniform No-Backend Execution Failure") — neither touches
`context`.

Family labels follow the Family Label Convention (design.md CP5):
`whisper` (OpenAI Whisper, transcription) and `kokoro` (Kokoro TTS,
synthesis) are both already bare published lineage tokens.

`flags`: both speech directions stream (segments / audio chunks) but
claim no tool-calling, no structured output, and no reasoning trace
(design.md, "Flag rationale") — `streaming=True` only, `tools`/`json`/
`reasoning` left at their `False` default.
"""

from dataclasses import dataclass

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import CapabilityDescriptor, CapabilityFlags, ModelFamily
from tibios_ray.capabilities.errors import NoBackendAvailableError
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.execution.context import ExecutionContext
from tibios_ray.execution.report import ExecutionReport

SPEECH_TRANSCRIBE_DESCRIPTOR = CapabilityDescriptor(
    capability=CapabilityName("speech.transcribe"),
    families=frozenset({ModelFamily("whisper")}),
    backends=frozenset({BackendId("faster_whisper")}),
    flags=CapabilityFlags(streaming=True),
)

SPEECH_SYNTHESIZE_DESCRIPTOR = CapabilityDescriptor(
    capability=CapabilityName("speech.synthesize"),
    families=frozenset({ModelFamily("kokoro")}),
    backends=frozenset({BackendId("onnxruntime")}),
    flags=CapabilityFlags(streaming=True),
)


@dataclass(frozen=True, slots=True)
class SpeechTranscriptionProvider:
    """Implements `speech.transcribe`. Holds no Backend Adapter
    reference — no fields exist to hold one — so `execute()` always
    raises `NoBackendAvailableError`."""

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return SPEECH_TRANSCRIBE_DESCRIPTOR

    async def execute(self, context: ExecutionContext) -> ExecutionReport:
        raise NoBackendAvailableError(
            capability=SPEECH_TRANSCRIBE_DESCRIPTOR.capability,
            provider=type(self).__name__,
        )


@dataclass(frozen=True, slots=True)
class SpeechSynthesisProvider:
    """Implements `speech.synthesize`. Holds no Backend Adapter
    reference — no fields exist to hold one — so `execute()` always
    raises `NoBackendAvailableError`."""

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return SPEECH_SYNTHESIZE_DESCRIPTOR

    async def execute(self, context: ExecutionContext) -> ExecutionReport:
        raise NoBackendAvailableError(
            capability=SPEECH_SYNTHESIZE_DESCRIPTOR.capability,
            provider=type(self).__name__,
        )
