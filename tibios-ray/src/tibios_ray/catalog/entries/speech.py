"""Reference data for the Speech capability group.

Two families (design decision MC12, filing-by-family not by capability):
`whisper` (`speech.transcribe`) and `kokoro` (`speech.synthesize`). Both
directions share one module because `capabilities/speech.py` itself is
"the only two-class module" — one file for two Providers — and this
entries module mirrors that filing choice for the same capability group.

`SPEECH_ENTRIES` is this module's only exported entry point per family
group (MC14 — `entries/__init__.py`'s `ALL_ENTRIES`/`DEFAULT_CATALOG`
assembly is deferred to the final slice).

Unlike the Chat family group (slices 3-4), `design.md`'s worked
Reference data table does not cover `whisper`/`kokoro` — only the
family/model-name list (line 400, "Remaining groups"). Every
`min_vram_bytes` figure here is therefore *derived*, not copied, from
MC13's formula (`ceil_gib(parameter_count x bits/8 x 1.2)`), using the
decimal-GB (`bytes / 1e9`, ceiling) interpretation established in slice
5's `entries/embedding.py`/`entries/rerank.py` and reused in slice 6's
`entries/vision.py`.

`context_window` for these two families has no token-context analogue
the way it does for the text/vision families — it is each model's own
natively published sequence-length ceiling: Whisper's decoder
`max_target_positions` (448, from OpenAI's published Whisper config —
identical for `large-v3` and the `-turbo` variant, since turbo only
prunes decoder layers, not the positional embedding table) and Kokoro's
documented single-pass input limit (510 tokens, per the model card).

Backends are capability-specific, not shared across this module, unlike
every other family group so far: `capabilities/speech.py`'s
`SPEECH_TRANSCRIBE_DESCRIPTOR.backends` is `{faster_whisper}` (used by
`whisper`), and `SPEECH_SYNTHESIZE_DESCRIPTOR.backends` is
`{onnxruntime}` (used by `kokoro`) — two independent single-backend
constraints in the same module, each entry group only ever using its
own capability's advertised backend.
"""

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import ModelFamily
from tibios_ray.catalog.model import BackendSupport, ModelDescriptor
from tibios_ray.catalog.names import PublishedModelName
from tibios_ray.selection.policy import Quantization

_FASTER_WHISPER = BackendId("faster_whisper")
_ONNXRUNTIME = BackendId("onnxruntime")

_INT8 = Quantization(scheme="int8", bits=8)
_FP16 = Quantization(scheme="fp16", bits=16)
_FP32 = Quantization(scheme="fp32", bits=32)

_WHISPER = ModelFamily("whisper")
_KOKORO = ModelFamily("kokoro")

WHISPER_ENTRIES: tuple[ModelDescriptor, ...] = (
    ModelDescriptor(
        # 1.55B params, 448-token decoder context (OpenAI's published
        # max_target_positions).
        name=PublishedModelName("openai/whisper-large-v3"),
        family=_WHISPER,
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
    ),
    ModelDescriptor(
        # 809M params (decoder pruned from 32 to 4 layers; encoder
        # unchanged), same 448-token decoder context as large-v3.
        name=PublishedModelName("openai/whisper-large-v3-turbo"),
        family=_WHISPER,
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
    ),
)

KOKORO_ENTRIES: tuple[ModelDescriptor, ...] = (
    ModelDescriptor(
        # 82M params (StyleTTS2-based), 510-token input limit (the
        # model card's documented single-pass ceiling). int8 and fp32
        # both round to 1 GiB at this parameter count, so they share
        # one row (MC5's pattern).
        name=PublishedModelName("hexgrad/Kokoro-82M"),
        family=_KOKORO,
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
    ),
)

SPEECH_ENTRIES: tuple[ModelDescriptor, ...] = WHISPER_ENTRIES + KOKORO_ENTRIES
