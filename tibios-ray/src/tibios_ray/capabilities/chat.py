"""The Chat Capability Provider (`capability-providers` spec: Descriptor
Catalog Correctness and Stability, "Chat advertises realistic flags").

Zero-field `@dataclass(frozen=True, slots=True)` satisfying
`CapabilityProvider` structurally — no base class (design decision D1,
CP1). `slots=True` with zero fields makes "holds no Backend Adapter" a
language guarantee, not a convention: there is no attribute slot to put
one in. `execute()` raises `NoBackendAvailableError` unconditionally
(`capability-providers` spec: "Uniform No-Backend Execution Failure") —
it never touches `context` (no channel emit, no cancellation read),
which is what makes "never returns a COMPLETED report" trivially true.

Family labels follow the Family Label Convention (design.md CP5): a pure
function of each model's published lineage name, e.g. `Qwen/Qwen3-8B-
Instruct` -> `qwen`, `deepseek-ai/DeepSeek-V3` -> `deepseek`.
"""

from dataclasses import dataclass

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import CapabilityDescriptor, CapabilityFlags, ModelFamily
from tibios_ray.capabilities.errors import NoBackendAvailableError
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.execution.context import ExecutionContext
from tibios_ray.execution.report import ExecutionReport

CHAT_GENERATE_DESCRIPTOR = CapabilityDescriptor(
    capability=CapabilityName("chat.generate"),
    families=frozenset(
        {
            ModelFamily("qwen"),
            ModelFamily("llama"),
            ModelFamily("deepseek"),
            ModelFamily("gemma"),
            ModelFamily("mistral"),
            ModelFamily("kimi"),
        }
    ),
    backends=frozenset(
        {
            BackendId("llama_cpp"),
            BackendId("tensorrt_llm"),
            BackendId("vllm"),
        }
    ),
    flags=CapabilityFlags(streaming=True, tools=True, json=True, reasoning=True),
)


@dataclass(frozen=True, slots=True)
class ChatProvider:
    """Implements `chat.generate`. Holds no Backend Adapter reference — no
    fields exist to hold one — so `execute()` always raises
    `NoBackendAvailableError`."""

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return CHAT_GENERATE_DESCRIPTOR

    async def execute(self, context: ExecutionContext) -> ExecutionReport:
        raise NoBackendAvailableError(
            capability=CHAT_GENERATE_DESCRIPTOR.capability,
            provider=type(self).__name__,
        )
