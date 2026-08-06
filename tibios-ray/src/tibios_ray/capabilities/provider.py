"""Capability Provider contract (`capability-registry` spec: "Capability
Provider Interface").

A Capability Provider is the internal unit that implements one
capability (e.g. `chat.generate`) — it is never a "Worker" (`proposal.md`
binding terminology: "Worker" is reserved exclusively for the gRPC Worker
Contract entity; a `ChatProvider` does not implement that contract and
must never be misread as if it did). `runtime/`'s `WorkerRuntime`
(Phase 5) is the sole "Worker"-adjacent concrete class in this codebase;
everything downstream of `CapabilityRegistry.resolve()` is a Capability
Provider.

Modeled as `typing.Protocol` (design decision D1) — a Provider needs no
base class, and Phase 2's six concrete Providers (Chat, Embedding,
Reranker, Vision, Speech, OCR) can each satisfy it structurally.

## Resolving `CapabilityProvider.execute()`'s return type

`design.md`'s Key Contracts snippet types `execute()` as returning
`ExecutionMetrics` — but no such type was ever defined anywhere in this
codebase; Phase 1's `execution/report.py` deliberately models only the
fields named in `18-worker-model.md` (`ExecutionReport`,
`ExecutionPulse`, `ExecutionPhase`), and `design.md`'s own Open Questions
section already flags `ExecutionMetrics`/`ExecutionReport` field fidelity
as unresolved pending the real `.proto` contract.

This module resolves it as **`ExecutionReport`** — the type that already
exists — rather than introducing a new `ExecutionMetrics` type. Two
independent reasons converge on this call:

1. `18-worker-model.md`'s own principle, quoted verbatim in
   `execution/report.py`: "Execution produces events. Completion produces
   a report." `design.md`'s Data Flow section restates this for
   `execute()` specifically: "`execute()` returning the Report is not
   'returning a result' — completion produces a report." There is one
   Worker Contract completion artifact, not two.
2. `design.md`'s own flow line has `WorkerRuntime.execute(ctx) ->
   ExecutionReport`, and the Data Flow diagram shows the Report
   propagating from the Provider layer up through the Runtime to the
   gRPC boundary unchanged. A distinct `ExecutionMetrics` type at the
   Provider layer would require an unmodeled Runtime-side translation
   step that neither `design.md` nor `tasks.md` describes anywhere.

No new type was added to `execution/` for this — Phase 1 is not reopened.
If a future phase's real `.proto` contract needs a narrower/different
completion payload at the Provider boundary specifically, that is an
additive, non-breaking change to make then, not now.
"""

from typing import Protocol

from tibios_ray.capabilities.descriptor import CapabilityDescriptor
from tibios_ray.execution.context import ExecutionContext
from tibios_ray.execution.report import ExecutionReport


class CapabilityProvider(Protocol):
    """A unit that implements one capability. Advertises its
    `CapabilityDescriptor` and executes an already-prepared
    `ExecutionContext`, producing an `ExecutionReport` on completion —
    application output travels only through `ExecutionContext.channel`,
    never through this return value (see module docstring)."""

    @property
    def descriptor(self) -> CapabilityDescriptor: ...

    async def execute(self, context: ExecutionContext) -> ExecutionReport: ...
