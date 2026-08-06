"""Reference data for the OCR capability group.

One family only: `paddleocr` (`ocr.extract`) ← `PaddlePaddle/PaddleOCR`.

`OCR_ENTRIES` is this module's only exported entry point per family
group (MC14 — `entries/__init__.py`'s `ALL_ENTRIES`/`DEFAULT_CATALOG`
assembly is deferred to the final slice).

Unlike the Chat family group (slices 3-4), `design.md`'s worked
Reference data table does not cover `paddleocr` — only the
family/model-name list (line 400, "Remaining groups"). `min_vram_gb`
is therefore *derived*, not copied, from MC13's formula
(`ceil_gib(parameter_count x bits/8 x 1.2)`), using the decimal-GB
(`bytes / 1e9`, ceiling) interpretation established in slice 5.

`parameter_count` is the combined detection + classification +
recognition pipeline PaddleOCR ships as one system — publicly documented
at roughly 15M parameters total, an order of magnitude below every
transformer-based family in this catalog, consistent with PaddleOCR's
mobile-first design goals. `context_window` has no token-context
analogue for a detect-then-recognize pipeline; the closest natively
published figure is the recognition head's `max_text_length` config
value (25 characters per detected text line), used here.

Every `BackendSupport` row uses `onnxruntime` — the only backend
`capabilities/ocr.py`'s `OCR_EXTRACT_DESCRIPTOR` advertises for
`paddleocr`. Same two quantization tiers as `entries/embedding.py`/
`entries/rerank.py`: `int8` (8 bits) and `fp32` (32 bits).
"""

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import ModelFamily
from tibios_ray.catalog.model import BackendSupport, ModelDescriptor
from tibios_ray.catalog.names import PublishedModelName
from tibios_ray.selection.policy import Quantization

_ONNXRUNTIME = BackendId("onnxruntime")

_INT8 = Quantization(scheme="int8", bits=8)
_FP32 = Quantization(scheme="fp32", bits=32)

_PADDLEOCR = ModelFamily("paddleocr")

PADDLEOCR_ENTRIES: tuple[ModelDescriptor, ...] = (
    ModelDescriptor(
        # ~15M params (det + cls + rec pipeline combined), 25-character
        # max_text_length (the recognition head's published config
        # value). int8 and fp32 both round to 1 GiB at this parameter
        # count, so they share one row (MC5's pattern).
        name=PublishedModelName("PaddlePaddle/PaddleOCR"),
        family=_PADDLEOCR,
        parameter_count=15_000_000,
        context_window=25,
        serving=frozenset(
            {
                BackendSupport(
                    backend=_ONNXRUNTIME,
                    quantizations=frozenset({_INT8, _FP32}),
                    min_vram_gb=1,
                ),
            }
        ),
    ),
)

OCR_ENTRIES: tuple[ModelDescriptor, ...] = PADDLEOCR_ENTRIES
