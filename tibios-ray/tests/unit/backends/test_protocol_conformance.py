"""`assert_type` conformance module (design.md Testing Strategy: "Fake
Provider/Adapter satisfy the Protocols" -> `assert_type` conformance
module) for every `backends/` Protocol.

`typing.assert_type` is a no-op at runtime — it returns its first
argument unchanged. Its value is at the type-checker layer: `uv run
pyright` fails the build if the expression's static type does not match
the declared Protocol exactly. Combined with a variable annotated with
the Protocol type (which pyright checks structurally on assignment),
this proves every fake satisfies its Protocol without runtime
`isinstance` checks against `Protocol` classes, which are not
`@runtime_checkable` here (design decision D1: structural typing only,
no base-class coupling).
"""

from collections.abc import AsyncIterator, Sequence
from typing import assert_type

from tibios_ray.backends.adapter import BackendAdapter, BackendId, BackendSession
from tibios_ray.backends.embedding import EmbeddingBackend, Vector
from tibios_ray.backends.rerank import RerankBackend, RerankResult
from tibios_ray.backends.speech import AudioRef, TranscriptionBackend, TranscriptSegment
from tibios_ray.backends.text import TextChunk, TextGenerationBackend, TextRequest


class _FakeResidencyOnly:
    """Satisfies only `BackendAdapter` — no modality execution method."""

    @property
    def backend_id(self) -> BackendId:
        return BackendId("generic")

    def supports(self, plan: object) -> bool:
        return True

    async def acquire(self, plan: object) -> BackendSession:
        return BackendSession(backend_id=self.backend_id, session_id="s")

    async def release(self, session: BackendSession) -> None:
        return None


class _FakeText(_FakeResidencyOnly):
    async def generate(
        self, session: BackendSession, request: TextRequest
    ) -> AsyncIterator[TextChunk]:
        yield TextChunk(text=request.prompt)


class _FakeEmbedding(_FakeResidencyOnly):
    async def embed(self, session: BackendSession, inputs: Sequence[str]) -> Sequence[Vector]:
        return [Vector(values=(0.0,)) for _ in inputs]


class _FakeRerank(_FakeResidencyOnly):
    async def rerank(
        self, session: BackendSession, query: str, documents: Sequence[str]
    ) -> Sequence[RerankResult]:
        return [RerankResult(index=i, score=0.0) for i in range(len(documents))]


class _FakeTranscription(_FakeResidencyOnly):
    async def transcribe(
        self, session: BackendSession, audio: AudioRef
    ) -> AsyncIterator[TranscriptSegment]:
        yield TranscriptSegment(text="", start_seconds=0.0, end_seconds=0.0)


# Each helper's parameter is declared with the Protocol type, not the
# concrete fake — parameter types are NOT narrowed to the caller's
# argument type the way local-variable assignments are, so `assert_type`
# inside genuinely proves the Protocol-typed value keeps its declared
# static type. Pyright separately rejects the *call site* if the fake
# does not structurally satisfy the Protocol (`reportArgumentType`).


def _accepts_backend_adapter(adapter: BackendAdapter) -> None:
    assert_type(adapter, BackendAdapter)


def _accepts_text_generation_backend(backend: TextGenerationBackend) -> None:
    assert_type(backend, TextGenerationBackend)


def _accepts_embedding_backend(backend: EmbeddingBackend) -> None:
    assert_type(backend, EmbeddingBackend)


def _accepts_rerank_backend(backend: RerankBackend) -> None:
    assert_type(backend, RerankBackend)


def _accepts_transcription_backend(backend: TranscriptionBackend) -> None:
    assert_type(backend, TranscriptionBackend)


def test_fake_residency_only_conforms_to_backend_adapter() -> None:
    fake = _FakeResidencyOnly()
    _accepts_backend_adapter(fake)
    assert fake.backend_id == BackendId("generic")


def test_fake_text_conforms_to_text_generation_backend() -> None:
    fake = _FakeText()
    _accepts_text_generation_backend(fake)
    assert fake.backend_id == BackendId("generic")


def test_fake_embedding_conforms_to_embedding_backend() -> None:
    fake = _FakeEmbedding()
    _accepts_embedding_backend(fake)
    assert fake.backend_id == BackendId("generic")


def test_fake_rerank_conforms_to_rerank_backend() -> None:
    fake = _FakeRerank()
    _accepts_rerank_backend(fake)
    assert fake.backend_id == BackendId("generic")


def test_fake_transcription_conforms_to_transcription_backend() -> None:
    fake = _FakeTranscription()
    _accepts_transcription_backend(fake)
    assert fake.backend_id == BackendId("generic")
