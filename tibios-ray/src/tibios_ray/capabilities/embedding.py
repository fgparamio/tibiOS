"""The Embedding Capability Provider (`capability-providers` spec:
Descriptor Catalog Correctness and Stability, "Embedding/Rerank advertise
none").

Zero-field `@dataclass(frozen=True, slots=True)` satisfying
`CapabilityProvider` structurally — no base class (design decision D1,
CP1), same shape as `ChatProvider`. `execute()` raises
`NoBackendAvailableError` unconditionally (`capability-providers` spec:
"Uniform No-Backend Execution Failure") — it never touches `context`.

Family labels follow the Family Label Convention (design.md CP5),
including its explicit deviations from `proposal.md`'s shorthand:
`nomic-ai/nomic-embed-text-v1.5` -> `nomic_embed` and
`jinaai/jina-embeddings-v3` -> `jina_embeddings` (rule 3 keeps published
role tokens the FLC would otherwise drop).

`flags` is omitted entirely rather than spelled out as four `False`s —
embedding produces fixed-shape numeric output with no stream, no tools,
no structure, no reasoning trace, so the `CapabilityFlags()` default
already says everything (design.md, "Flag rationale").
"""

from dataclasses import dataclass

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import CapabilityDescriptor, ModelFamily
from tibios_ray.capabilities.errors import NoBackendAvailableError
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.execution.context import ExecutionContext
from tibios_ray.execution.report import ExecutionReport

EMBEDDING_GENERATE_DESCRIPTOR = CapabilityDescriptor(
    capability=CapabilityName("embedding.generate"),
    families=frozenset(
        {
            ModelFamily("bge"),
            ModelFamily("nomic_embed"),
            ModelFamily("e5"),
            ModelFamily("jina_embeddings"),
        }
    ),
    backends=frozenset({BackendId("onnxruntime")}),
)


@dataclass(frozen=True, slots=True)
class EmbeddingProvider:
    """Implements `embedding.generate`. Holds no Backend Adapter
    reference — no fields exist to hold one — so `execute()` always
    raises `NoBackendAvailableError`."""

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return EMBEDDING_GENERATE_DESCRIPTOR

    async def execute(self, context: ExecutionContext) -> ExecutionReport:
        raise NoBackendAvailableError(
            capability=EMBEDDING_GENERATE_DESCRIPTOR.capability,
            provider=type(self).__name__,
        )
