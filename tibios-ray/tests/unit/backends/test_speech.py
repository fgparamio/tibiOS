"""Tests for `tibios_ray.backends.speech` — `TranscriptionBackend`:
time-segmented audio in, a stream of transcript segments out
(Faster-Whisper in Phase 4).
"""

import asyncio
import dataclasses
from collections.abc import AsyncIterator

import pytest

from tibios_ray.backends.adapter import BackendId, BackendSession
from tibios_ray.backends.speech import AudioRef, TranscriptionBackend, TranscriptSegment
from tibios_ray.execution.ids import ContentHash


class FakeTranscriptionBackend:
    def __init__(self) -> None:
        self._backend_id = BackendId("faster_whisper")

    @property
    def backend_id(self) -> BackendId:
        return self._backend_id

    def supports(self, plan: object) -> bool:  # pragma: no cover - unused here
        return True

    async def acquire(self, plan: object) -> BackendSession:
        return BackendSession(backend_id=self._backend_id, session_id="sess-speech")

    async def release(self, session: BackendSession) -> None:  # pragma: no cover - unused
        return None

    async def transcribe(
        self, session: BackendSession, audio: AudioRef
    ) -> AsyncIterator[TranscriptSegment]:
        segments = [("hello", 0.0, 0.5), ("world", 0.5, 1.0)]
        for text, start, end in segments:
            yield TranscriptSegment(text=text, start_seconds=start, end_seconds=end)


class TestAudioRef:
    def test_holds_its_content_hash(self) -> None:
        ref = AudioRef(content_hash=ContentHash("sha256:abc123..."))
        assert ref.content_hash == ContentHash("sha256:abc123...")

    def test_is_frozen(self) -> None:
        ref = AudioRef(content_hash=ContentHash("sha256:abc123..."))
        with pytest.raises(dataclasses.FrozenInstanceError):
            ref.content_hash = ContentHash("sha256:other")  # type: ignore[misc]


class TestTranscriptSegment:
    def test_holds_text_and_time_bounds(self) -> None:
        segment = TranscriptSegment(text="hi", start_seconds=0.0, end_seconds=1.5)
        assert segment.text == "hi"
        assert segment.start_seconds == 0.0
        assert segment.end_seconds == 1.5

    def test_is_frozen(self) -> None:
        segment = TranscriptSegment(text="hi", start_seconds=0.0, end_seconds=1.0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            segment.text = "bye"  # type: ignore[misc]


def test_fake_transcription_backend_satisfies_the_protocol() -> None:
    backend: TranscriptionBackend = FakeTranscriptionBackend()
    assert backend.backend_id == BackendId("faster_whisper")


def test_transcribe_streams_time_ordered_segments() -> None:
    backend = FakeTranscriptionBackend()

    async def scenario() -> list[TranscriptSegment]:
        session = await backend.acquire(object())
        audio = AudioRef(content_hash=ContentHash("sha256:abc123..."))
        return [segment async for segment in backend.transcribe(session, audio)]

    segments = asyncio.run(scenario())
    assert [s.text for s in segments] == ["hello", "world"]
    assert segments[0].end_seconds == segments[1].start_seconds
