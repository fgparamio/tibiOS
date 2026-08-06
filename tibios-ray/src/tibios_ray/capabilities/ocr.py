"""The OCR Capability Provider (`capability-providers` spec: Descriptor
Catalog Correctness and Stability).

Zero-field `@dataclass(frozen=True, slots=True)` satisfying
`CapabilityProvider` structurally — no base class (design decision D1,
CP1), same shape as `ChatProvider`/`EmbeddingProvider`/`RerankProvider`/
`VisionProvider`. `execute()` raises `NoBackendAvailableError`
unconditionally (`capability-providers` spec: "Uniform No-Backend
Execution Failure") — it never touches `context`.

Family label follows the Family Label Convention (design.md CP5):
`PaddlePaddle/PaddleOCR` -> `paddleocr` (rule 3 keeps the published `ocr`
role token joined to the lineage token, after dropping the `PaddlePaddle`
org prefix).

`flags`: OCR returns structured layout in one shot — `json=True`,
`streaming`/`tools`/`reasoning` left at their `False` default
(design.md, "Flag rationale").
"""

from dataclasses import dataclass

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import CapabilityDescriptor, CapabilityFlags, ModelFamily
from tibios_ray.capabilities.errors import NoBackendAvailableError
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.execution.context import ExecutionContext
from tibios_ray.execution.report import ExecutionReport

OCR_EXTRACT_DESCRIPTOR = CapabilityDescriptor(
    capability=CapabilityName("ocr.extract"),
    families=frozenset({ModelFamily("paddleocr")}),
    backends=frozenset({BackendId("onnxruntime")}),
    flags=CapabilityFlags(json=True),
)


@dataclass(frozen=True, slots=True)
class OcrProvider:
    """Implements `ocr.extract`. Holds no Backend Adapter reference — no
    fields exist to hold one — so `execute()` always raises
    `NoBackendAvailableError`."""

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return OCR_EXTRACT_DESCRIPTOR

    async def execute(self, context: ExecutionContext) -> ExecutionReport:
        raise NoBackendAvailableError(
            capability=OCR_EXTRACT_DESCRIPTOR.capability,
            provider=type(self).__name__,
        )
