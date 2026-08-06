"""Tests for `tibios_ray.capabilities.speech` — the Speech Capability
Providers (`capability-providers` spec: "Descriptor Catalog Correctness
and Stability").

`speech.py` is the one module with two classes: `CapabilityDescriptor.
capability` is singular and the registry is one-provider-per-capability,
so transcription (`speech.transcribe`) and synthesis (`speech.
synthesize`) are two registrable Providers sharing one module (design.md
"the only two-class module").

Only catalog data is asserted here — one full descriptor equality plus
flag values per class. Structural/behavioral conformance (identity
stability, element typing, FLC shape, `execute()` always raising,
end-to-end dispatch) is covered generically by
`test_provider_conformance.py` (design decision CP7) so this file stays
small.
"""

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import CapabilityDescriptor, CapabilityFlags, ModelFamily
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.capabilities.speech import (
    SPEECH_SYNTHESIZE_DESCRIPTOR,
    SPEECH_TRANSCRIBE_DESCRIPTOR,
    SpeechSynthesisProvider,
    SpeechTranscriptionProvider,
)


class TestSpeechTranscriptionProvider:
    def test_descriptor_matches_the_spec_table_exactly(self) -> None:
        provider = SpeechTranscriptionProvider()

        assert provider.descriptor == CapabilityDescriptor(
            capability=CapabilityName("speech.transcribe"),
            families=frozenset({ModelFamily("whisper")}),
            backends=frozenset({BackendId("faster_whisper")}),
            flags=CapabilityFlags(streaming=True),
        )

    def test_descriptor_is_the_module_level_constant(self) -> None:
        provider = SpeechTranscriptionProvider()

        assert provider.descriptor is SPEECH_TRANSCRIBE_DESCRIPTOR

    def test_flags_are_streaming_only(self) -> None:
        flags = SpeechTranscriptionProvider().descriptor.flags

        assert flags == CapabilityFlags(streaming=True)
        assert flags.streaming is True
        assert flags.tools is False
        assert flags.json is False
        assert flags.reasoning is False


class TestSpeechSynthesisProvider:
    def test_descriptor_matches_the_spec_table_exactly(self) -> None:
        provider = SpeechSynthesisProvider()

        assert provider.descriptor == CapabilityDescriptor(
            capability=CapabilityName("speech.synthesize"),
            families=frozenset({ModelFamily("kokoro")}),
            backends=frozenset({BackendId("onnxruntime")}),
            flags=CapabilityFlags(streaming=True),
        )

    def test_descriptor_is_the_module_level_constant(self) -> None:
        provider = SpeechSynthesisProvider()

        assert provider.descriptor is SPEECH_SYNTHESIZE_DESCRIPTOR

    def test_flags_are_streaming_only(self) -> None:
        flags = SpeechSynthesisProvider().descriptor.flags

        assert flags == CapabilityFlags(streaming=True)
        assert flags.streaming is True
        assert flags.tools is False
        assert flags.json is False
        assert flags.reasoning is False
