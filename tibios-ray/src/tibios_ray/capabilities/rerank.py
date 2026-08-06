"""The Rerank Capability Provider (`capability-providers` spec:
Descriptor Catalog Correctness and Stability, "Embedding/Rerank advertise
none").

Zero-field `@dataclass(frozen=True, slots=True)` satisfying
`CapabilityProvider` structurally — no base class (design decision D1,
CP1), same shape as `ChatProvider`. `execute()` raises
`NoBackendAvailableError` unconditionally (`capability-providers` spec:
"Uniform No-Backend Execution Failure") — it never touches `context`.

Family labels follow the Family Label Convention (design.md CP5):
`BAAI/bge-reranker-v2-m3` -> `bge_reranker` and
`jinaai/jina-reranker-v2-base-multilingual` -> `jina_reranker` (rule 3
keeps the published `reranker` role token).

`flags` is omitted entirely rather than spelled out as four `False`s —
rerank produces fixed-shape numeric output with no stream, no tools, no
structure, no reasoning trace, so the `CapabilityFlags()` default already
says everything (design.md, "Flag rationale").
"""

from dataclasses import dataclass

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import CapabilityDescriptor, ModelFamily
from tibios_ray.capabilities.errors import NoBackendAvailableError
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.execution.context import ExecutionContext
from tibios_ray.execution.report import ExecutionReport

RERANK_DOCUMENTS_DESCRIPTOR = CapabilityDescriptor(
    capability=CapabilityName("rerank.documents"),
    families=frozenset(
        {
            ModelFamily("bge_reranker"),
            ModelFamily("jina_reranker"),
        }
    ),
    backends=frozenset({BackendId("onnxruntime")}),
)


@dataclass(frozen=True, slots=True)
class RerankProvider:
    """Implements `rerank.documents`. Holds no Backend Adapter
    reference — no fields exist to hold one — so `execute()` always
    raises `NoBackendAvailableError`."""

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return RERANK_DOCUMENTS_DESCRIPTOR

    async def execute(self, context: ExecutionContext) -> ExecutionReport:
        raise NoBackendAvailableError(
            capability=RERANK_DOCUMENTS_DESCRIPTOR.capability,
            provider=type(self).__name__,
        )
