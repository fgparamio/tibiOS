"""The Chat Capability Provider (`capability-providers` spec: Descriptor
Catalog Correctness and Stability, "Chat advertises realistic flags";
`provider-backend-composition` spec: "Per-Request Dispatch Flow").

`ChatProvider` is *wired* (design decision D18): it declares exactly two
constructor-injected, immutable fields — `backends` and
`selection_policy` — normalized via `MappingProxyType` in
`__post_init__` so an injected `dict` cannot be mutated afterwards, nor
can the caller's own `dict` leak later mutations in. `execute()` runs
the ADR-0002 flow through `capabilities/dispatch.py`'s module-level pure
functions (`resolve_model_ref`, `resolve_backend`, `completed_report`,
`cancelled_report`) and `capabilities/requests.py`'s `ChatRequest` — this
module holds only the chat-specific parts: building `TextRequest`,
streaming `TextChunk`s onto the channel via D24's codec, and cooperative
cancellation.

Chat codec (D24): raw UTF-8 bytes of each non-empty `TextChunk.text`,
one `OutputChunk` per delta, `sequence` incrementing from 0. The
terminal `TextChunk(text="", finished=True)` delta emits no chunk — an
empty payload carries nothing, and (per D25) `WorkerRuntime`, not this
Provider, owns emitting the terminal `EndOfStream`; a direct `execute()`
call in a test therefore sees chunks with no `EndOfStream`.

Every failure below `execute()`'s own two report-returning outcomes
(`COMPLETED`, `CANCELLED`) is a raise, never a returned `FAILED` report
(D21) — `WorkerRuntime._dispatch` already translates any exception into
one at the Worker Contract boundary.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from time import monotonic
from types import MappingProxyType

from tibios_ray.backends.adapter import BackendId
from tibios_ray.backends.text import TextGenerationBackend, TextRequest
from tibios_ray.capabilities.descriptor import CapabilityDescriptor, CapabilityFlags, ModelFamily
from tibios_ray.capabilities.dispatch import (
    cancelled_report,
    completed_report,
    resolve_backend,
    resolve_model_ref,
)
from tibios_ray.capabilities.errors import BackendExecutionError
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.capabilities.requests import ChatRequest
from tibios_ray.execution.context import ExecutionContext
from tibios_ray.execution.events import OutputChunk
from tibios_ray.execution.report import ExecutionReport
from tibios_ray.selection.policy import ModelSelectionPolicy

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


@dataclass(frozen=True, slots=True, kw_only=True)
class ChatProvider:
    """Implements `chat.generate`. Holds exactly two constructor-injected,
    immutable fields — no Backend is ever constructed, looked up, or
    discovered here (ADR-0001/ADR-0002)."""

    backends: Mapping[BackendId, TextGenerationBackend]
    selection_policy: ModelSelectionPolicy

    def __post_init__(self) -> None:
        # Normalizing here (D18) makes the immutability guarantee the
        # Provider's own rather than the caller's: a plain `dict` passed
        # in is snapshotted via `dict(...)` first (so later mutating the
        # caller's own dict cannot leak in), then wrapped read-only.
        object.__setattr__(self, "backends", MappingProxyType(dict(self.backends)))

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return CHAT_GENERATE_DESCRIPTOR

    async def execute(self, context: ExecutionContext) -> ExecutionReport:
        started_at = monotonic()
        trace_id = context.observability_context.trace_id
        capability = CHAT_GENERATE_DESCRIPTOR.capability

        request = ChatRequest.parse(context.execution_parameters)
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

        text_request = TextRequest(
            prompt=request.prompt,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            stop=request.stop,
        )

        sequence = 0
        try:
            async for chunk in backend.generate(session, text_request):
                if context.cancellation.is_cancelled:
                    break
                if chunk.text:
                    await context.channel.emit(
                        OutputChunk(data=chunk.text.encode(), sequence=sequence)
                    )
                    sequence += 1
        except Exception as error:
            raise BackendExecutionError(
                backend=plan.backend, stage="execute", error=error
            ) from error
        finally:
            await backend.release(session)

        if context.cancellation.is_cancelled:
            return cancelled_report(started_at=started_at, trace_id=trace_id)
        return completed_report(started_at=started_at, trace_id=trace_id)
