"""The Embedding Capability Provider (`capability-providers` spec:
Descriptor Catalog Correctness and Stability, "Chat advertises realistic
flags; Embedding/Rerank advertise none"; `provider-backend-composition`
spec: "Per-Request Dispatch Flow", "Non-Streaming Results Travel Through
the Channel").

`EmbeddingProvider` is *wired* (design decision D18): same shape as
`ChatProvider` — two constructor-injected, immutable fields, `backends`
and `selection_policy`, normalized via `MappingProxyType` in
`__post_init__`. `execute()` runs the same ADR-0002 flow through
`capabilities/dispatch.py`'s module-level pure functions and
`capabilities/requests.py`'s `EmbeddingRequest` — this module holds only
what is embedding-specific: calling `EmbeddingBackend.embed()` once (a
batch call, not a token stream) and the D24 embedding codec.

Embedding codec (D24): exactly **one** `OutputChunk`, `sequence=0`, UTF-8
JSON `{"vectors": [[...], ...]}` — one inner list per `Vector` returned by
`embed()`, in the order `embed()` returned them (which mirrors input
order since embedding is a positional, one-vector-per-input batch call).
Unlike `chat.py`'s per-delta codec there is no "empty/terminal" filter to
apply: a batch result is either emitted whole or not at all, so the D24
codec itself introduces no conditional. The one conditional native to
this module's `execute()` is cooperative cancellation — checked once,
after `embed()` resolves and the session is released, since a batch
capability method is a single awaited call with no intermediate progress
to poll mid-flight (`provider-backend-composition` spec: "Cooperative
cancellation is observed mid-execution" — for a batch Provider, "stops
driving further output" means the one batch result is not emitted).

Every failure below `execute()`'s own two report-returning outcomes
(`COMPLETED`, `CANCELLED`) is a raise, never a returned `FAILED` report
(D21) — `WorkerRuntime._dispatch` already translates any exception into
one at the Worker Contract boundary.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from time import monotonic
from types import MappingProxyType

from tibios_ray.backends.adapter import BackendId
from tibios_ray.backends.embedding import EmbeddingBackend
from tibios_ray.capabilities.descriptor import CapabilityDescriptor, ModelFamily
from tibios_ray.capabilities.dispatch import (
    cancelled_report,
    completed_report,
    resolve_backend,
    resolve_model_ref,
)
from tibios_ray.capabilities.errors import BackendExecutionError
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.capabilities.requests import EmbeddingRequest
from tibios_ray.execution.context import ExecutionContext
from tibios_ray.execution.events import OutputChunk
from tibios_ray.execution.report import ExecutionReport
from tibios_ray.selection.policy import ModelSelectionPolicy

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


@dataclass(frozen=True, slots=True, kw_only=True)
class EmbeddingProvider:
    """Implements `embedding.generate`. Holds exactly two constructor-
    injected, immutable fields — no Backend is ever constructed, looked
    up, or discovered here (ADR-0001/ADR-0002)."""

    backends: Mapping[BackendId, EmbeddingBackend]
    selection_policy: ModelSelectionPolicy

    def __post_init__(self) -> None:
        # Normalizing here (D18) makes the immutability guarantee the
        # Provider's own rather than the caller's: a plain `dict` passed
        # in is snapshotted via `dict(...)` first (so later mutating the
        # caller's own dict cannot leak in), then wrapped read-only.
        object.__setattr__(self, "backends", MappingProxyType(dict(self.backends)))

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return EMBEDDING_GENERATE_DESCRIPTOR

    async def execute(self, context: ExecutionContext) -> ExecutionReport:
        started_at = monotonic()
        trace_id = context.observability_context.trace_id
        capability = EMBEDDING_GENERATE_DESCRIPTOR.capability

        request = EmbeddingRequest.parse(context.execution_parameters)
        model = await resolve_model_ref(context, capability=capability)
        backend, plan = resolve_backend(
            self.backends,
            self.selection_policy,
            model,
            capability=capability,
            provider=type(self).__name__,
        )

        try:
            session = await backend.acquire(plan)
        except Exception as error:
            raise BackendExecutionError(
                backend=plan.backend, stage="acquire", error=error
            ) from error

        try:
            vectors = await backend.embed(session, request.inputs)
        except Exception as error:
            raise BackendExecutionError(
                backend=plan.backend, stage="execute", error=error
            ) from error
        finally:
            await backend.release(session)

        if context.cancellation.is_cancelled:
            return cancelled_report(started_at=started_at, trace_id=trace_id)

        payload = json.dumps(
            {"vectors": [list(vector.values) for vector in vectors]}
        ).encode()
        await context.channel.emit(OutputChunk(data=payload, sequence=0))
        return completed_report(started_at=started_at, trace_id=trace_id)
