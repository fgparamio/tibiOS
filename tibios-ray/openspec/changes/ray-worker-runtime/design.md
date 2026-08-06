# Design: Ray Worker Runtime (Foundation)

## Technical Approach

Four Phase-1 concepts land as **typed contracts only**, layered one-way so that the word "Worker" appears exactly once (the gRPC-facing entity) and never propagates inward:

```
execution/        Worker Contract vocabulary (ExecutionContext, Channel, Event, Report, Pulse, cancellation)
    ▲        ▲            ▲             ▲
runtime/ → capabilities/ → selection/ → backends/
```

Dependencies point right-to-left only; no cycles. Every value type crossing a layer is a frozen, slotted dataclass — serializable by construction, so a Phase-4 Ray-actor split cannot force a contract reshape.

Execution flow: `worker.py (gRPC entity)` → `WorkerRuntime.execute(ctx)` → `CapabilityRegistry.resolve(ctx.capability)` → `CapabilityProvider.execute(ctx)` → `ModelSelectionPolicy.plan(...)` → modality Backend Adapter.

## Architecture Decisions

| # | Decision | Alternatives rejected | Rationale |
|---|---|---|---|
| D1 | `typing.Protocol` for all four contracts; concrete classes only for `CapabilityRegistry`/`WorkerRuntime` | ABC | Structural typing removes the import edge from every Provider/Adapter back to the framework; an adapter implementing two modalities is naturally both without multiple inheritance; fakes need no base class (`18-worker-model.md` testability). Runtime enforcement is regained where it matters: the registry validates descriptors at construction. |
| D2 | Provider protocol + descriptor live in `capabilities/`, **not** `runtime/` (refines the proposal's Affected Areas) | Keep both in `runtime/` | Phase 2 drops six Providers here; nesting them under `runtime/` would read as "part of the Worker host". The registry (a runtime-side index) stays in `runtime/`. |
| D3 | `ObjectId`/`ContentHash` are frozen dataclasses, **not** `NewType[str]` | `NewType`, `str` alias | `NewType` is a no-op: `ObjectId("deepseek")` would type-check, so the "policy cannot accept a family string" guarantee would be cosmetic. A dataclass requiring a `ContentHash` makes resolution *proof-carrying* — only the Runtime's Dependency References can produce one (`18-worker-model.md`: "Dependency References already resolved — Workers never locate Objects or perform scheduling-time discovery"). |
| D4 | **No single unified Backend Adapter.** One shared residency protocol + one execution protocol per modality | One `infer(input) -> stream[output]` | Text generation (sampling params, KV cache, token stream), embedding (batch in / fixed-shape vectors out, no streaming), and speech (time-segmented audio I/O) share only *load/unload/health*. Unifying them forces `dict[str, Any]` payloads and destroys type safety — a bad abstraction bought for symmetry. What IS common is model residency, which is exactly the private-cache concept of `18-worker-model.md`. |
| D5 | Cooperative `CancellationToken` protocol, not `asyncio.CancelledError` | Raw task cancellation | Contract requires acknowledge → cleanup → **final events** → Report. `CancelledError` unwinds the stack and would skip all four. |
| D6 | Registry is immutable, built from an explicit provider sequence at the composition root (`worker.py`) | `register()` mutation, entry-point auto-discovery | Auto-discovery/hot-reload are declared non-goals; immutability satisfies the "no global mutable state" anti-pattern. |
| D7 | `ExecutionEvent` is a PEP 695 tagged union of frozen dataclasses | Class hierarchy | pyright checks `match` exhaustiveness; adding an event breaks consumers loudly. |

**Non-violation note (for verify):** the policy comparing model footprint against Allocation capacity to pick a quantization is *not* the forbidden size/cost routing rule of `25-ai-runtime.md` — that rule forbids choosing *between Worker implementations*. Here the model is already fixed and the Worker is already selected by Scheduling's Capability Filter.

## Module Layout

| Path | Action | Contents |
|---|---|---|
| `src/tibios_ray/execution/` | Create | `ids.py` (`ObjectId`, `ObjectVersion`, `ContentHash`), `context.py` (`ExecutionContext`, `AllocationContract`, `ResolvedModelRef`), `channel.py` (`ExecutionChannel`, `CancellationToken`), `events.py`, `report.py` (`ExecutionReport`, `ExecutionPulse`, `ExecutionPhase`) |
| `src/tibios_ray/runtime/` | Create | `worker_runtime.py` (lifecycle host + dispatch), `registry.py` (`CapabilityRegistry`), `errors.py` |
| `src/tibios_ray/capabilities/` | Create | `provider.py` (`CapabilityProvider`), `descriptor.py` (`CapabilityDescriptor`, `CapabilityFlags`, `CapabilityCatalog`), `names.py` (`CapabilityName` + shape validation) |
| `src/tibios_ray/selection/` | Create | `policy.py` (`ModelSelectionPolicy`, `ServingConstraints`, `ServingPlan`, `Quantization`) |
| `src/tibios_ray/backends/` | Create | `adapter.py` (`BackendAdapter`, `BackendId`, `BackendSession`), `text.py`, `embedding.py`, `rerank.py`, `speech.py` |
| `src/tibios_ray/testing/` | Create | `InMemoryExecutionChannel`, `FakeExecutionContext`, `ManualCancellation`, `StubProvider`, `RecordingBackend` — shipped in-package so Phases 2–4 reuse them |
| `src/tibios_ray/worker.py` | Modify | Composition root docstring: gRPC Worker entity → builds registry → owns one `WorkerRuntime` |
| `docs/architecture/01-worker-runtime.md` | Create | Concept doc citing (never duplicating) `18-worker-model.md` |
| `tests/unit/**` | Create | Mirrors package layout |

## Key Contracts

```python
# execution/ — vocabulary. Channel is write-only: "Workers write to it; they never own it".
class ExecutionChannel(Protocol):
    async def emit(self, event: ExecutionEvent) -> None: ...   # bounded; backpressure per 05-async-concurrency.md

class CancellationToken(Protocol):
    @property
    def is_cancelled(self) -> bool: ...
    async def wait(self) -> None: ...

type ExecutionEvent = OutputChunk | Progress | Warning | CheckpointCreated | MetricsSnapshot | EndOfStream

@dataclass(frozen=True, slots=True)
class ResolvedModelRef:            # constructible only from ctx.dependencies — carries resolution proof
    object_id: ObjectId
    version: ObjectVersion
    content_hash: ContentHash

# capabilities/
class CapabilityProvider(Protocol):
    @property
    def descriptor(self) -> CapabilityDescriptor: ...
    async def execute(self, context: ExecutionContext) -> ExecutionMetrics: ...

@dataclass(frozen=True, slots=True)
class CapabilityDescriptor:        # the catalog shape Scheduling's Capability Filter eventually consumes
    capability: CapabilityName     # "chat.generate"
    families: frozenset[ModelFamily]
    backends: frozenset[BackendId]
    flags: CapabilityFlags         # streaming | tools | json | reasoning

# runtime/
class CapabilityRegistry:
    def __init__(self, providers: Sequence[CapabilityProvider]) -> None: ...   # duplicate capability -> error
    def resolve(self, capability: CapabilityName) -> CapabilityProvider: ...
    def catalog(self) -> CapabilityCatalog: ...

class WorkerRuntime:
    def __init__(self, registry: CapabilityRegistry) -> None: ...
    async def execute(self, context: ExecutionContext) -> ExecutionReport: ...

# selection/ — no family/str overload exists anywhere; input is already resolved
class ModelSelectionPolicy(Protocol):
    def plan(self, model: ResolvedModelRef, constraints: ServingConstraints) -> ServingPlan: ...
    # ServingPlan = (model, backend: BackendId, quantization: Quantization, precision: Precision)

# backends/ — common residency + per-modality execution
class BackendAdapter(Protocol):
    @property
    def backend_id(self) -> BackendId: ...
    def supports(self, plan: ServingPlan) -> bool: ...
    async def acquire(self, plan: ServingPlan) -> BackendSession: ...   # private cache, 18-worker-model.md
    async def release(self, session: BackendSession) -> None: ...

class TextGenerationBackend(BackendAdapter, Protocol):     # llama.cpp, vLLM, TensorRT-LLM
    def generate(self, s: BackendSession, req: TextRequest) -> AsyncIterator[TextChunk]: ...
class EmbeddingBackend(BackendAdapter, Protocol):          # ONNX Runtime
    async def embed(self, s: BackendSession, inputs: Sequence[str]) -> Sequence[Vector]: ...
class TranscriptionBackend(BackendAdapter, Protocol):      # Faster-Whisper
    def transcribe(self, s: BackendSession, audio: AudioRef) -> AsyncIterator[TranscriptSegment]: ...
```

**Family strings appear only in `CapabilityDescriptor` (outward advertisement).** They never enter the inward execution path — a compile-time expression of the boundary rule.

## Data Flow

```
gRPC (Phase 4)          worker.py            WorkerRuntime                Provider            Policy/Backends
     │  ExecutionContext    │                     │                          │                      │
     ├─────────────────────>├────────────────────>│ Received→Prepared        │                      │
     │                      │                     ├─ registry.resolve(cap) ─>│                      │
     │                      │                     │ Running                  ├─ plan(ResolvedModelRef)─>│
     │  <── ExecutionEvent ─── ctx.channel.emit() ─┴──────────────────────────┤  <── AsyncIterator ──┤
     │  <── ExecutionPulse ──┤                     │ Completed | Failed       │                      │
     │  <── ExecutionReport ─┴─────────────────────┘                          │                      │
```

Application output leaves only through the channel; the Report carries operational data only. `execute()` returning the Report is not "returning a result" — completion produces a report, and the Runtime owns its delivery.

## Testing Strategy

| Layer | What | How |
|---|---|---|
| Unit | Runtime lifecycle: dispatch, unknown capability → Failed report (no exception across the boundary), cancellation → ack + final events + report, always-a-report invariant | `FakeExecutionContext` + `InMemoryExecutionChannel` + `ManualCancellation`; zero infrastructure per `18-worker-model.md` |
| Unit | Registry: duplicate capability rejected, catalog shape stable | Plain pytest |
| Type | **Structural guard**: `policy.plan("deepseek")  # type: ignore[arg-type]` in a fixture module, with pyright `reportUnnecessaryTypeIgnore = true` — if the signature ever admits a string, pyright fails on the now-unnecessary ignore | `uv run pyright` |
| Type | Fake Provider/Adapter satisfy the Protocols | `assert_type` conformance module |
| Integration / E2E | None in Phase 1 — no engine, no gRPC, no Ray | Deferred to Phase 4 |

## Migration / Rollout

No migration. Additive packages only; `python-foundation` (pytest/ruff/pyright, `uv run`) must apply first.

## Deferred Design

Inference Intent has been intentionally omitted.

The current architecture is fully expressible through:

- Capability
- Workload Requirements
- Model Selection Policy

An intermediate abstraction will only be introduced if implementation experience demonstrates that these three concepts are insufficient — concretely, the day `chat.generate` needs to distinguish deep reasoning / light conversation / coding / creativity in a way no Workload requirement or existing Policy input can express. Not before.

## Open Questions

- [ ] **Quantization vocabulary owner** — Phase 1 uses `Quantization(scheme, bits)` with a backend-scoped scheme token. Should Phase 3's Model Catalog own a closed enum instead? (Recommendation: keep open until real backends exist.)
- [ ] **`ExecutionMetrics` / `ExecutionReport` field fidelity** vs tibios-core's actual Report — unverifiable until `../TibiOS/proto/` exists. Phase 1 models the fields named in `18-worker-model.md` and nothing more.
- [ ] **Assumed external precondition (not solved here):** `ResolvedModelRef` always arrives pre-resolved in the Execution Context. Producing one from `preferred_family: X` needs a generic metadata/tag query the Object Store does not expose today (`23-object-store.md` lists identity-based queries only: `GetObject`/`GetVersion`/`ResolveContent`/`Exists`/`ListVersions`/`FindReferences`). Likely a future tibios-core proposal; nothing in Phase 1 blocks on it.
