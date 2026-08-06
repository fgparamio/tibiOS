"""Tests for `tibios_ray.catalog.entries.speech` — the Speech capability
group's reference data (`design.md` line 400, "Remaining groups").

Two families (design decision MC12, filing-by-family not by capability):
`whisper` (`speech.transcribe`) and `kokoro` (`speech.synthesize`). Both
directions share one module because `capabilities/speech.py` itself is
"the only two-class module" — one file for two Providers — and the
entries module mirrors that filing choice for the same capability group.

Unlike the Chat family group (slices 3-4), `design.md`'s worked
Reference data table does **not** cover `whisper`/`kokoro` — only the
family/model-name list (line 400, "Remaining groups"). Every
`min_vram_bytes` figure here is therefore *derived*, not copied, from
MC13's formula (`ceil_gib(parameter_count x bits/8 x 1.2)`), the same
decimal-GB (`bytes / 1e9`, ceiling) interpretation established in slice
5's `entries/embedding.py`/`entries/rerank.py` and reused in slice 6's
`entries/vision.py`.

`context_window` for these two families is not a token-context concept
the way it is for the text/vision families — it is each model's own
natively published sequence-length limit: Whisper's decoder
`max_target_positions` (448, from OpenAI's published Whisper config —
same value for `large-v3` and the `-turbo` variant, since turbo only
prunes decoder layers, not the positional embedding table) and Kokoro's
documented single-pass input limit (510 tokens, per the model card).

Per family: family coverage (at least one entry reachable through
`ModelCatalog.models`), one full `ModelDescriptor` equality as a
stability assertion against a hand-built expected value, and the
derivation round-trip `entry.family == family_of(entry.name)` for every
entry in this slice (MC14 — `entries/__init__.py` assembly is deferred
to slice 8, so this module builds its own local
`ModelCatalog(SPEECH_ENTRIES)` fixture rather than importing
`DEFAULT_CATALOG`).

Backends are capability-specific, not shared, unlike every other family
group so far: `capabilities/speech.py`'s `SPEECH_TRANSCRIBE_DESCRIPTOR`
advertises only `faster_whisper` for `whisper`, and
`SPEECH_SYNTHESIZE_DESCRIPTOR` advertises only `onnxruntime` for
`kokoro` — two different single-backend constraints in the same module,
checked separately per family.
"""

import pytest

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import ModelFamily
from tibios_ray.catalog.catalog import ModelCatalog
from tibios_ray.catalog.entries.speech import (
    KOKORO_ENTRIES,
    SPEECH_ENTRIES,
    WHISPER_ENTRIES,
)
from tibios_ray.catalog.model import BackendSupport, ModelDescriptor
from tibios_ray.catalog.names import PublishedModelName, family_of
from tibios_ray.selection.policy import Quantization

_FASTER_WHISPER = BackendId("faster_whisper")
_ONNXRUNTIME = BackendId("onnxruntime")

_INT8 = Quantization(scheme="int8", bits=8)
_FP16 = Quantization(scheme="fp16", bits=16)
_FP32 = Quantization(scheme="fp32", bits=32)


def _catalog() -> ModelCatalog:
    return ModelCatalog(SPEECH_ENTRIES)


def _find(entries: tuple[ModelDescriptor, ...], name: str) -> ModelDescriptor:
    for entry in entries:
        if entry.name.value == name:
            return entry
    raise AssertionError(f"no entry named {name!r} in {[e.name.value for e in entries]}")


class TestFamilyCoverage:
    def test_whisper_has_at_least_one_entry(self) -> None:
        assert _catalog().models(ModelFamily("whisper"))

    def test_kokoro_has_at_least_one_entry(self) -> None:
        assert _catalog().models(ModelFamily("kokoro"))

    def test_whisper_has_two_entries(self) -> None:
        # openai/whisper-large-v3, openai/whisper-large-v3-turbo
        assert len(WHISPER_ENTRIES) == 2

    def test_kokoro_has_one_entry(self) -> None:
        assert len(KOKORO_ENTRIES) == 1


class TestDerivationRoundTrip:
    @pytest.mark.parametrize(
        "entry", SPEECH_ENTRIES, ids=[entry.name.value for entry in SPEECH_ENTRIES]
    )
    def test_entry_family_matches_family_of(self, entry: ModelDescriptor) -> None:
        assert entry.family == family_of(entry.name)


class TestPerFamilyBackend:
    # SPEECH_TRANSCRIBE_DESCRIPTOR advertises only faster_whisper —
    # whisper entries must not claim any other backend.
    @pytest.mark.parametrize(
        "entry", WHISPER_ENTRIES, ids=[entry.name.value for entry in WHISPER_ENTRIES]
    )
    def test_whisper_entry_serving_rows_are_faster_whisper_only(
        self, entry: ModelDescriptor
    ) -> None:
        assert all(row.backend == _FASTER_WHISPER for row in entry.serving)

    # SPEECH_SYNTHESIZE_DESCRIPTOR advertises only onnxruntime — kokoro
    # entries must not claim any other backend.
    @pytest.mark.parametrize(
        "entry", KOKORO_ENTRIES, ids=[entry.name.value for entry in KOKORO_ENTRIES]
    )
    def test_kokoro_entry_serving_rows_are_onnxruntime_only(
        self, entry: ModelDescriptor
    ) -> None:
        assert all(row.backend == _ONNXRUNTIME for row in entry.serving)


class TestStabilityAssertions:
    def test_whisper_large_v3_full_equality(self) -> None:
        # 1.55B params, 448-token decoder context (OpenAI's published
        # max_target_positions, shared by every large-v3 variant).
        # fp16: ceil_gib(1_550_000_000 * 2 * 1.2) = ceil_gib(3_720_000_000) = 4
        # int8: ceil_gib(1_550_000_000 * 1 * 1.2) = ceil_gib(1_860_000_000) = 2
        expected = ModelDescriptor(
            name=PublishedModelName("openai/whisper-large-v3"),
            family=ModelFamily("whisper"),
            parameter_count=1_550_000_000,
            context_window=448,
            serving=frozenset(
                {
                    BackendSupport(
                        backend=_FASTER_WHISPER,
                        quantizations=frozenset({_FP16}),
                        min_vram_bytes=4,
                    ),
                    BackendSupport(
                        backend=_FASTER_WHISPER,
                        quantizations=frozenset({_INT8}),
                        min_vram_bytes=2,
                    ),
                }
            ),
        )

        assert _find(WHISPER_ENTRIES, "openai/whisper-large-v3") == expected

    def test_whisper_large_v3_turbo_full_equality(self) -> None:
        # 809M params (pruned decoder: 32 -> 4 layers, encoder
        # unchanged), same 448-token decoder context as large-v3.
        # fp16: ceil_gib(809_000_000 * 2 * 1.2) = ceil_gib(1_941_600_000) = 2
        # int8: ceil_gib(809_000_000 * 1 * 1.2) = ceil_gib(970_800_000) = 1
        expected = ModelDescriptor(
            name=PublishedModelName("openai/whisper-large-v3-turbo"),
            family=ModelFamily("whisper"),
            parameter_count=809_000_000,
            context_window=448,
            serving=frozenset(
                {
                    BackendSupport(
                        backend=_FASTER_WHISPER,
                        quantizations=frozenset({_FP16}),
                        min_vram_bytes=2,
                    ),
                    BackendSupport(
                        backend=_FASTER_WHISPER,
                        quantizations=frozenset({_INT8}),
                        min_vram_bytes=1,
                    ),
                }
            ),
        )

        assert _find(WHISPER_ENTRIES, "openai/whisper-large-v3-turbo") == expected

    def test_kokoro_82m_full_equality(self) -> None:
        # 82M params (StyleTTS2-based), 510-token input limit (the
        # model card's documented single-pass ceiling). int8 and fp32
        # both round to 1 GiB at this parameter count, so they share
        # one BackendSupport row (MC5's pattern).
        # int8: ceil_gib(82_000_000 * 1 * 1.2) = ceil_gib(98_400_000) = 1
        # fp32: ceil_gib(82_000_000 * 4 * 1.2) = ceil_gib(393_600_000) = 1
        expected = ModelDescriptor(
            name=PublishedModelName("hexgrad/Kokoro-82M"),
            family=ModelFamily("kokoro"),
            parameter_count=82_000_000,
            context_window=510,
            serving=frozenset(
                {
                    BackendSupport(
                        backend=_ONNXRUNTIME,
                        quantizations=frozenset({_INT8, _FP32}),
                        min_vram_bytes=1,
                    ),
                }
            ),
        )

        assert _find(KOKORO_ENTRIES, "hexgrad/Kokoro-82M") == expected
