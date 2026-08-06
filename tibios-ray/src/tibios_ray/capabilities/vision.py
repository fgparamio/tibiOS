"""The Vision Capability Provider (`capability-providers` spec: Descriptor
Catalog Correctness and Stability).

Zero-field `@dataclass(frozen=True, slots=True)` satisfying
`CapabilityProvider` structurally — no base class (design decision D1,
CP1), same shape as `ChatProvider`/`EmbeddingProvider`/`RerankProvider`.
`execute()` raises `NoBackendAvailableError` unconditionally
(`capability-providers` spec: "Uniform No-Backend Execution Failure") —
it never touches `context`.

Family labels follow the Family Label Convention (design.md CP5):
`Qwen/Qwen2-VL-7B-Instruct` -> `qwen_vl`, `meta-llama/Llama-3.2-11B-
Vision` -> `llama_vision` (rule 3 keeps published role tokens). `gemma`
deviates from `proposal.md`'s shorthand `gemma_vision`: Google publishes
no "Gemma Vision" lineage (Gemma 3 is natively multimodal), so rule 3
keeps only the bare published lineage token `gemma` — the same label
`ChatProvider` uses for `chat.generate`. This is intentional: one
lineage legitimately serves two capabilities.

`flags`: vision streams generated text and supports structured
extraction, but this catalog claims no VLM tool-calling and no
reasoning trace (design.md, "Flag rationale") — `streaming=True,
json=True`, `tools`/`reasoning` left at their `False` default.
"""

from dataclasses import dataclass

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import CapabilityDescriptor, CapabilityFlags, ModelFamily
from tibios_ray.capabilities.errors import NoBackendAvailableError
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.execution.context import ExecutionContext
from tibios_ray.execution.report import ExecutionReport

VISION_UNDERSTAND_DESCRIPTOR = CapabilityDescriptor(
    capability=CapabilityName("vision.understand"),
    families=frozenset(
        {
            ModelFamily("qwen_vl"),
            ModelFamily("llama_vision"),
            ModelFamily("gemma"),
        }
    ),
    backends=frozenset(
        {
            BackendId("vllm"),
            BackendId("tensorrt_llm"),
        }
    ),
    flags=CapabilityFlags(streaming=True, json=True),
)


@dataclass(frozen=True, slots=True)
class VisionProvider:
    """Implements `vision.understand`. Holds no Backend Adapter reference
    — no fields exist to hold one — so `execute()` always raises
    `NoBackendAvailableError`."""

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return VISION_UNDERSTAND_DESCRIPTOR

    async def execute(self, context: ExecutionContext) -> ExecutionReport:
        raise NoBackendAvailableError(
            capability=VISION_UNDERSTAND_DESCRIPTOR.capability,
            provider=type(self).__name__,
        )
