"""Speech transcription execution — time-segmented audio in, a stream of
transcript segments out (Faster-Whisper in Phase 4).
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from tibios_ray.backends.adapter import BackendAdapter, BackendSession
from tibios_ray.execution.ids import ContentHash


@dataclass(frozen=True, slots=True, kw_only=True)
class AudioRef:
    """Reference to time-segmented audio input, identified by content
    hash (``13-object-model.md``). Phase 2 models identity only —
    decoding/streaming details are Phase 4 (Faster-Whisper) engine
    specifics."""

    content_hash: ContentHash


@dataclass(frozen=True, slots=True, kw_only=True)
class TranscriptSegment:
    """One time-bounded unit of a streamed transcription result."""

    text: str
    start_seconds: float
    end_seconds: float


class TranscriptionBackend(BackendAdapter, Protocol):
    """Streaming transcription over an acquired `BackendSession`."""

    def transcribe(
        self, session: BackendSession, audio: AudioRef
    ) -> AsyncIterator[TranscriptSegment]: ...
