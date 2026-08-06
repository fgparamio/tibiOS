"""Backend Adapter contract — the engine-agnostic boundary Capability
Providers execute against (`backend-adapter` spec, design decision D4).

Phase 2 defines the contract only: model residency (`acquire`/`release`)
plus the `backend_id`/`supports` identity surface shared by every
modality. There is **no unified `infer()`** — text generation (sampling
params, KV cache, token stream), embedding (batch in / fixed-shape
vectors out, no streaming), and speech (time-segmented audio I/O) share
only load/unload/health; forcing them into one method would require
`dict[str, Any]` payloads and destroy type safety. Per-modality execution
protocols live in `text.py`, `embedding.py`, `rerank.py`, `speech.py`,
each extending `BackendAdapter` with its own narrow execution method.

`backends/` has **zero dependency** on `selection/`, `capabilities/`, or
`runtime/` — those layers depend on `backends/`, never the reverse
(module dependency direction: `runtime -> capabilities -> selection ->
backends`). `ServingPlanLike` below is a minimal structural shape defined
here rather than importing `selection.ServingPlan` (which does not exist
until Phase 3); Phase 3's concrete `ServingPlan` will satisfy it
structurally with no import edge required — the same reasoning as design
decision D1 (structural typing removes import edges).
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class BackendId:
    """Identity of an inference backend/engine, e.g. `"llama_cpp"`,
    `"vllm"`, `"onnxruntime"`, `"faster_whisper"`. Advertised outward in
    `CapabilityDescriptor.backends` (Phase 4) and matched by
    `ModelSelectionPolicy` (Phase 3) against a concrete Backend Adapter."""

    value: str


@dataclass(frozen=True, slots=True, kw_only=True)
class BackendSession:
    """An opaque handle to acquired model residency — the private,
    per-execution cache described in `18-worker-model.md`. Fields beyond
    identity are intentionally engine-specific and belong to Phase 4's
    concrete adapters; Phase 2 models only what every residency handle
    must carry to be released again."""

    backend_id: BackendId
    session_id: str


class ServingPlanLike(Protocol):
    """Structural shape a serving plan must expose to be usable by a
    Backend Adapter: which backend it targets. See module docstring for
    why this is not imported from `selection.ServingPlan`."""

    @property
    def backend(self) -> BackendId: ...


class BackendAdapter(Protocol):
    """Common residency surface every modality-specific backend extends.
    No unified `infer()` — see module docstring / design decision D4."""

    @property
    def backend_id(self) -> BackendId: ...

    def supports(self, plan: ServingPlanLike) -> bool: ...

    async def acquire(self, plan: ServingPlanLike) -> BackendSession: ...

    async def release(self, session: BackendSession) -> None: ...
