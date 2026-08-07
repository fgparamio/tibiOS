# Design: Worker Context Wiring (the gRPC boundary tibios-ray never grew)

Change: `worker-context-wiring` · Artifact store: openspec (file + Engram `sdd/worker-context-wiring/design`).
Extends — never renumbers — the frozen decisions **D1-D7** (`ray-worker-runtime`), **CP1-CP8** (`capability-providers`), **MC1-MC14** (`model-catalog`), **LC1-LC12** (`llamacpp-backend`). New decisions here are **D8-D17**, continuing the `D` series as `proposal.md:73` requires.

This document settles the five open questions of `proposal.md:75-79` plus the `grpc.aio` question of `:81`. **Q3 is resolved at D9.** Nothing here reopens D1-D7; nothing here touches `../proto/`, which stays frozen and cross-repo-owned.

## Technical Approach

One new package holds every `grpc` and `_pb2` symbol in the codebase, and the existing layer graph gains exactly one node:

```
execution/        Worker Contract vocabulary — gains WorkloadId/AllocationId/SecurityContext/ObservabilityContext
    ▲        ▲            ▲             ▲              ▲
runtime/ → capabilities/ → selection/ → backends/   transport/  ← NEW: grpc.aio + generated code, nothing else
    ▲                                                   │
    └───────────────────── server.py ───────────────────┘   (entry point: imports neither grpc nor _pb2)
```

`transport/` depends on `execution/` and `runtime/`. Nothing depends on `transport/` except `server.py`, and `server.py` reaches it through one grpc-free function call. The dependency direction of `runtime -> capabilities -> selection -> backends` is unchanged, and `engines/` is untouched.

Three properties carry the design:

1. **Conversion is a pure function over generated messages.** `transport/convert.py` imports `_pb2` and nothing from `grpc` — every rejection scenario is unit-testable with zero sockets, zero servers, zero event loops.
2. **"Report always last" is structural, not disciplined.** The Report is enqueued only after `WorkerRuntime.execute` returns, and the streaming loop breaks on it (D14). proto3 cannot enforce ordering; a queue can.
3. **The domain is narrowed to what its *owner* declares, never to what the wire happens to carry.** That distinction is what separates D9 (narrow) from D16 (drop at the boundary, keep in the domain).

## The Boundary / Data Flow

```
tibios-core ──①──▶ WorkerExecutionServicer ──②──▶ convert.py ──③──▶ WorkerRuntime ──④──▶ Provider
                            ▲                                            │
                            └────────⑤──── bounded asyncio.Queue ◀───────┘  (GrpcExecutionChannel)
```

| # | Boundary | What crosses | What MUST NOT cross |
|---|---|---|---|
| ① | gRPC → servicer | `ExecutionContext`, `CancelRequest`, `PulseRequest` (generated messages) | Transport metadata carrying contract data — `worker.proto:51-58`: "a Worker MUST NOT read transport metadata to obtain contract data" |
| ② | servicer → convert | one generated message | Any domain type; conversion is the only place the two vocabularies meet |
| ③ | convert → runtime | a domain `ExecutionContext` (D8), or a classified `Permanent` rejection (D17) | A defaulted, guessed, or placeholder value on any path (`worker-wire-conversion` spec) |
| ④ | runtime → Provider | the same `ExecutionContext`, unchanged | Any `grpc`/`_pb2` symbol — enforced recursively by the import guard (D13) |
| ⑤ | Provider → stream | `ExecutionEvent` values via `ExecutionChannel.emit`, then exactly one `ExecutionReport` | An event after the Report; a Report that is not last (D14) |

The SubmitJob handler, which is the only non-obvious half:

```
 servicer coroutine                          │  execute task (same event loop)
 ────────────────────────────────────────────┼─────────────────────────────────────────
 ctx = convert(request)        ← may reject  │
 registry.register(workload_id)  ← O1, SYNC, │
   before the first await                    │
 queue = asyncio.Queue(maxsize=8)            │
 task = create_task(runtime.execute(ctx)) ───┼─▶ Provider emits ...
 while True:                                 │     channel.emit(e) -> await queue.put(_Event(e))
   item = await queue.get()   ◀──────────────┤   ... EndOfStream
   _Event  -> yield Response(event=...)      │   execute() returns the Report
   _Done   -> yield Response(report=...); break ◀ done-callback puts _Done(report)
 finally:                                    │
   channel.close(); token.cancel()  ← no await
   registry.deregister(workload_id)  ← O2, SYNC, every outcome
```

## Architecture Decisions

| # | Decision | Alternatives rejected | Rationale |
|---|---|---|---|
| D8 | **`ExecutionContext` grows to ten fields; there is no envelope.** Eight wire-visible (`workload_id`, `allocation_id`, `capability`, `allocation_contract`, `dependencies`, `security_context`, `observability_context`, `execution_parameters`) plus the two domain-only ones (`channel`, `cancellation`) it already had | A nested `WireContext`/`ExecutionEnvelope` sub-object; a second parallel context type | `18-worker-model.md:52` describes **one** immutable Execution Context containing all of it; splitting it in two would make every Provider reach through a hop to read a field the doc puts at the same level. tibios-core reached the same answer for the same reason (`worker-inbound-port/design.md` Testability sequence keeps `workload_id`/`allocation_id` as direct fields of its own `ExecutionContext`). `kw_only=True` is already set, so widening the constructor breaks no positional call site. `channel`/`cancellation` stay inside the context — a deliberate, pre-existing divergence from tibios-core, which passes the channel as an `execute` parameter (its D9); D5 already made cancellation context-carried here, and reopening it is out of scope |
| D9 | **`AllocationContract` narrows to exactly `max_execution_duration`.** The other five fields are deleted, not defaulted (see below — this is Q3, the blocking one) | Default the five at the boundary; keep a six-field domain type and a separate one-field wire type; keep six and reject every wire message | Full argument below |
| D10 | **`dependencies` becomes `tuple[ResolvedModelRef, ...]` — ordered, unkeyed** | A `Mapping` keyed on `object_id.value`; a key derived from position (`"0"`, `"1"`); an invented role vocabulary | The wire is `repeated ResolvedModelRef` with no key, and `18-worker-model.md:52` says only "Dependency References (already resolved)" — it names no role, label, or slot. Any key the boundary produced would be **fabricated**, which is precisely what `worker-wire-conversion`'s reject-don't-guess rule forbids. A key derived from `object_id` is worse than useless: a Provider cannot know a ULID in advance, so it enables no lookup, while costing order and raising a duplicate-key question the wire allows and a `Mapping` cannot express. tibios-core's domain independently landed on `Vec<ResolvedDependency>` (`execution/context.rs:181`). Verified cost: **zero production readers** — `dependencies` is read nowhere in `src/`; only `testing/context.py` defaults it and two tests index `["model"]` |
| D11 | **Checked-in generated code under `src/tibios_ray/transport/_generated/`, mirroring the proto tree, produced by `scripts/generate_proto.py`, with a line-anchored import rewrite and two independent guards** | Build-time generation; flattening the tree; `protoletariat`; a `sys.path` insertion so `tibios.` resolves | Mechanics below |
| D12 | **`grpc.aio`, not sync `grpc`.** The server is built and served on one event loop, and **is not hosted inside a Ray actor by this change** | Sync `grpc` + `ThreadPoolExecutor`; `grpc.aio` inside a Ray async actor now | `WorkerRuntime.execute`, `CapabilityProvider.execute`, and `ExecutionChannel.emit` are all `async`, but that alone is only stylistic. The decisive argument is **loop affinity**: `engines/llamacpp.py` holds a per-session `asyncio.Lock` and a bounded `asyncio.Queue` (LC4, LC6), both bound to the loop that created them. A sync servicer would have to call `asyncio.run(...)` per RPC, minting a fresh loop each time — a session acquired on one RPC's loop could never be generated on another's. That is a correctness failure, not a preference. `grpc.aio` also makes O1 ("register before the first await") directly expressible, and lets `Cancel` signal a `CancellationToken` awaited by a sibling coroutine with no `call_soon_threadsafe` hop. No new dependency: `grpc.aio` ships inside `grpcio`. **The Ray risk is real and is sidestepped, not ignored** — see the limitation below |
| D13 | **Transport package layout, with the isolation guard at zero exceptions.** The servicer lives in `transport/servicer.py`, not in `server.py`; `server.py` is a grpc-free process entry point calling `tibios_ray.transport.serve(...)`; `worker.py` is a grpc-free composition root returning a `WorkerRuntime` | `WorkerExecutionServicer` in `server.py` (as `proposal.md:64` sketched) plus an allowlist entry in the import guard | `worker-grpc-transport`'s guard is written absolutely: *"No module outside the transport package MAY import `grpc` or any `_pb2` symbol"*. Putting the servicer in top-level `server.py` would force the very first exception into a brand-new guard. Moving it one directory keeps the guard at zero exceptions and still lets `server.py` "replace the docstring stub" as the proposal promised — it becomes the entry point, not the transport. Precedent: `test_no_engine_imports.py` has no allowlist either, and that is what makes it worth having |
| D14 | **The SubmitJob response stream is driven by a bounded per-execution `asyncio.Queue` (`maxsize=8`); the Report is enqueued only after `execute` returns, and the loop breaks on it** | Yield events from the channel and append the Report by convention; an unbounded queue; `asyncio.gather` on task + drain | Makes `worker-grpc-transport`'s "always last" requirement **structurally true**: no code path can enqueue an event after the Report, because the Report is produced by the same call whose return ends the producer. Bounded is load-bearing for the same reason as LC6 — an unbounded queue turns "streamed" into "buffered in RAM" for a fast token producer, and `05-async-concurrency.md`'s backpressure rule applies to this hop exactly as it does to the engine hop. `maxsize=8` matches LC6 and is a judgment call, not a measurement |
| D15 | **The in-flight registry owns the `CancellationToken` and the transport-observable phase.** One entry per `WorkloadId`: the token, the execute task, and a phase that is only ever `RECEIVED` (registered, task not started) or `RUNNING` (task started) | Reuse `testing/cancellation.ManualCancellation`; report `RUNNING` unconditionally; ask `WorkerRuntime` for the phase | The wire carries no cancellation object (`worker.proto:81-83`), so the token must be **minted by the transport** — and it must not come from `testing/`, because production code importing a test double is a layering inversion. A new ~12-line `transport/cancellation.py` is the honest cost; if a second producer ever appears, it promotes to `execution/`. On phase: `WorkerRuntime` publishes no transitions, so `PREPARED` is genuinely unobservable from here. Reporting it anyway would be a guess, and reporting `RUNNING` for a not-yet-started task would be a lie. Two observable values plus O2's deregistration (after which `Pulse` correctly says unknown) is exactly what this layer knows. `Cancel` is idempotent while registered (tibios-core D11) |
| D16 | **Domain→wire lossiness resolved field by field; the drop list is closed and asserted by test** | Silent drops; a JSON blob smuggled through `summary`; a `[code] message` prefix convention | Table below |
| D17 | **One classified error hierarchy in `transport/errors.py`: `ErrorClass{TRANSIENT, PERMANENT, FATAL}` mirroring tibios-core's `ErrorClass`, a `ConversionError` family and a `CorrelationError` family, every member `PERMANENT`, each mapped to a fixed gRPC status** | A bare `ValueError`; classification by `isinstance` at the call site; letting exceptions escape as `UNKNOWN` | `worker-wire-conversion` requires "a classified `Permanent` error" and tibios-ray has no classification concept at all today (`runtime/errors.py` and `capabilities/errors.py` are plain `Exception` families). Three enum members, not one, so "every rejection classifies `PERMANENT`" is a meaningful assertion rather than a tautology. **The Worker classifies the nature of the failure; the Runtime decides what to do about it** (`18-worker-model.md:122`) — the class is not a retry instruction. Fixed mapping: conversion rejection → `INVALID_ARGUMENT`; unknown `WorkloadId` (O3) → `NOT_FOUND`; duplicate `WorkloadId` (O4) → `ALREADY_EXISTS`. Nothing ever surfaces as `UNKNOWN` |

### D9 — `AllocationContract` narrows to one field (Q3, BLOCKING)

**Decision.** `execution/context.py`'s `AllocationContract` loses `exclusive`, `renewable_lease`, `preemptible`, `migration_allowed`, and `checkpoint_required`. One field remains: `max_execution_duration: timedelta`. There is no second wire-facing type, and the boundary defaults nothing.

**The decisive argument is ownership, not the wire.** `02-project-structure.md`'s Ownership Boundaries table reads `Allocation → AllocationContract → Worker`: the producer owns the contract, and consumers never redefine it. tibios-ray is a consumer. The producer — `runtime-allocation` — has now shipped the type, and its spec is explicit (`runtime-allocation/spec.md:36-63`): exactly one field, `max_execution_duration`, "intentionally partial, pending `15-allocation-model.md`'s own future change to add the remaining documented facets (exclusive/shared, renewable lease, preemptible, migration allowed, checkpoint required)". tibios-ray's six-field version is therefore not a richer model — it is a **consumer redefining another domain's contract**, the exact anti-pattern tibios-core rejected by name when it declined to mint Worker-local `TenantLabel`/`PrincipalLabel` newtypes (`worker-inbound-port/design.md` D10 Alternatives). The wire and the Rust domain already agree at one field; the Python domain is the only outlier, and outliers lose.

**Defaulting is not available, and not merely distasteful.** The five fields are booleans with real operational meaning — `preemptible=False` and `preemptible=True` describe opposite executions. Choosing either is inventing a term of a contract this process did not grant and cannot renew (`18-worker-model.md:56`: "Workers consume Allocation Contracts — they never create, modify, or renew them"). A defaulted `AllocationContract` would be a **Worker-authored** contract wearing the Runtime's name. Reject-don't-guess forbids it, and there is no principled exception to carve.

**Narrowing is behavior-preserving, verified rather than assumed.** A recursive scan of `src/` finds the five fields read by **nothing**: they are constructed in `testing/context.py:22-29` and in test fixtures, and consumed nowhere. They were speculative when `ray-worker-runtime` wrote them (that change's own Open Questions flagged Report/Context field fidelity as "unverifiable until `../proto/` exists" — `../proto/` now exists and has answered). Deleting them removes a promise the codebase never kept.

**Consequences.**
- `testing/context.py`'s `_default_allocation_contract()` shrinks to one keyword; `tests/unit/execution/test_context.py` and `tests/unit/testing/test_testing_context.py` update accordingly. This is the change's only non-mechanical revert (`proposal.md:98` already anticipated it for the constructor).
- The docstring must state the partiality and name `15-allocation-model.md` as the future owner of the full shape — the same obligation `runtime-allocation/spec.md:59-63` imposes on the Rust side, so the two read identically.
- **Absent `allocation_contract` on the wire is a `Permanent` rejection, never a default.** `18-worker-model.md:56` requires the Worker to enforce the maximum duration; a Worker with no contract can enforce nothing. This mirrors tibios-core's carried-forward decision verbatim.
- **A negative `google.protobuf.Duration` is a `Permanent` rejection.** The wire permits negative durations; a negative maximum execution duration is meaningless. Python's `timedelta` *can* represent one, so unlike Rust this is not caught by the type — it must be an explicit check. Same treatment for `ExecutionReport.duration` outbound.
- `max_execution_duration` is still enforced by nobody. That is pre-existing debt, not created here, and it is named in Open Questions so the narrowing does not quietly absorb it.

### D11 — Codegen mechanics (Q2)

| Aspect | Decision |
|---|---|
| Where | `src/tibios_ray/transport/_generated/tibios/{worker,primitives}/v1/*_pb2.py`, `*_pb2.pyi`, `*_pb2_grpc.py` — the proto tree mirrored, with generated `__init__.py` at every level (protoc emits none) |
| What generates | `scripts/generate_proto.py`, run as `uv run python scripts/generate_proto.py`. A plain module exposing `regenerate(into: Path) -> None` plus a `__main__` shim — **not** a `[project.scripts]` entry, which would ship a dev tool in the wheel. `uv_build` exposes no build-hook API (`proposal.md:76`), and this design does not change the build backend to acquire one |
| Dependencies | `grpcio` and `protobuf` become runtime dependencies (`grpcio` does not depend on `protobuf`; the generated modules do). `grpcio-tools` goes in the **dev** group only — regeneration is a developer task, never an install-time one |
| Import rewriting | protoc emits package-absolute `from tibios.primitives.v1 import identity_pb2 as ...` in all three file kinds (`_pb2.py`, `_pb2.pyi`, `_pb2_grpc.py`). The script rewrites **only lines matching `^from tibios\.`**, prefixing them to `from tibios_ray.transport._generated.tibios.`. One rule, no per-file table, and it survives a future `v2` package |
| Linting | `_generated/` is excluded from ruff (`extend-exclude`) and from pyright (`exclude` — which drops files from the *checked* set while still using them for inference at import sites, exactly what is wanted). `--pyi_out` is generated so `_pb2` message attributes are typed; `_pb2_grpc.py` has no stubs and needs none, since the servicer only subclasses it |
| Drift guard | **Byte-identical.** `tests/unit/transport/test_proto_drift.py` loads `scripts/generate_proto.py` via `importlib.util.spec_from_file_location` (single source of truth, no duplicated logic), regenerates into `tmp_path`, and compares every file. Skips with an explicit reason if `../proto` or `grpc_tools` is absent, plus a companion non-vacuity test asserting the checked-in tree is non-empty — the `test_backends_package_has_python_source_files_to_check` precedent |
| Second guard | A **version-independent semantic guard**: read the generated descriptors and assert `WorkerExecution` has exactly the three RPCs and `ExecutionContext` exactly its eight fields. Byte-identity is sensitive to the `grpcio-tools`/`protobuf` version (generated code embeds a runtime-version check); this one is not. Two guards, two failure modes — a toolchain bump reddens the first with a message naming the fix command, and leaves the second green |

**Why byte-identical rather than semantic equivalence for the drift guard:** semantic comparison means comparing descriptor pools, which is more code, catches strictly less (it cannot see a stale `_pb2_grpc.py` whose descriptors are unchanged), and its failure message tells you nothing actionable. Byte-identity's failure mode — "someone changed `../proto` and did not re-run the script" — is exactly the failure the guard exists for, and the fix is one command. The version sensitivity is why the second guard exists, not a reason to weaken the first.

### D16 — Domain→wire lossiness, resolved field by field (Q5)

The governing distinction: **the domain follows `18-worker-model.md`, which is canonical; the wire is a projection that says so about itself (`worker.proto:3-6`).** So a domain field with no wire home is not evidence the domain is wrong — unlike D9, where the *owner* of the type had narrowed it. tibios-core's Rust domain narrowed to the wire because it is a report *consumer* and can never learn more than the wire carries; tibios-ray is the *producer* and genuinely has more. Nothing is dropped silently; every row below is asserted by a test, and the drop list is closed — `tests/unit/transport/test_lossiness.py` enumerates it, so adding a seventh domain field forces a decision rather than a silent extension.

| Domain | Wire | Decision |
|---|---|---|
| `ExecutionReport.phase` | `final_phase` | Mapped through an explicit `Mapping[ExecutionPhase, int]`; a test asserts its key set equals the whole enum and no value is `0`. `EXECUTION_PHASE_UNSPECIFIED` is unreachable by construction |
| `ExecutionReport.duration` | `duration` | Mapped. A negative domain duration raises `PERMANENT` rather than emitting something the peer would reject (D9 Consequences) |
| `ExecutionReport.trace_id` | `trace_id` | Mapped verbatim |
| `ExecutionReport.failure` | **`summary`** | **Folded.** `summary = report.failure or ""`. The wire's `summary` is "a human-readable summary of the outcome" (tibios-core `report.rs:42`) and for a failed execution the failure text *is* that summary. proto3 cannot distinguish absent from empty, so a successful report yields `""`. Stated rule, two tests (failure text arrives verbatim; success yields empty) — not a silent default |
| `ExecutionReport.resource_usage`, `.metrics` | none | **Dropped, by contract design.** The wire did not forget metrics — it *relocated* them, from the Report to the event stream's `MetricsSnapshot` arm (`worker.proto:124-129`, `18-worker-model.md:94`). A Provider that wants metrics on the wire emits a `MetricsSnapshot` event, which it can do today, unchanged. The transport does **not** synthesize one: fabricating a domain event at the boundary is a worse sin than the drop |
| `ExecutionReport.logs` | none | **Dropped.** Logs belong to `09-observability.md`'s own channel, not to the Worker Contract wire. Documented in `convert.py`; the correct fix, if ever needed, is a `.proto` change — cross-repo and out of scope |
| `Warning.code` | none | **Dropped.** No wire field, no producer in `src/`, and not named by `18-worker-model.md`. Explicitly **not** prefixed into `message`: inventing a `[code] msg` parse format on a frozen contract creates an unversioned side-channel the peer never agreed to. The domain field stays as a Worker-local annotation whose docstring says it does not cross the wire |
| `EndOfStream.reason` | none (wire `EndOfStream` is empty) | **Dropped, and demonstrably non-lossy on the only path that sets it.** `WorkerRuntime.execute` derives `reason` from `report.failure` (`worker_runtime.py:69`), and `failure` reaches the wire through `summary`. The rule this establishes — no Worker may place information *solely* in `EndOfStream.reason` — is stated in the docstring and asserted by a test |
| `ExecutionPulse.detail` | none | **Dropped.** Set by nothing, anywhere (verified) |
| `Progress.message: str \| None` | `string message` | `None` → `""`. proto3 has no absent scalar; documented |
| `OutputChunk.sequence: int` | `uint64` | Negative or `>= 2**64` raises `PERMANENT` — a Worker bug, surfaced rather than truncated |
| `CheckpointCreated.checkpoint_id: str` | `ObjectId checkpoint_object_id` | **Wrapped verbatim, no ULID validation.** Same treatment tibios-core gives `ContentHash` (`convert.rs:137-143`): the owning domain defines validity and the adapter does not second-guess. Found during design, not listed in `proposal.md:79`; the underlying debt — the domain field should be an `ObjectId`, not a bare `str` — is recorded in Open Questions, not fixed here |
| — | `ExecutionReport.summary` inbound | **Non-issue in this repo.** tibios-ray is the gRPC *server*; it never receives an `ExecutionReport`. The "wire `summary` has no domain home" half of Q5 has no inbound direction to resolve, and no `summary` field is added to the domain `ExecutionReport` — it would be a field nothing fills, overlapping `failure` |

### Accepted, explicit limitations

- **`grpc.aio` inside a Ray actor is untested and deliberately deferred.** Ray async actors run their own event loop in a background thread; a `grpc.aio` server created on one loop and served on another is a known failure mode, and `max_concurrency` would additionally gate the servicer. This change hosts the server in a plain process (`asyncio.run` in `server.py`), which is exactly the scope `proposal.md:25` reserved ("Ray actor/cluster deployment topology, serving concurrency, process supervision" — out of scope). The rule the deployment change inherits, written down here so it is not rediscovered: **create the `grpc.aio.server()` on the same loop that will serve it, and never share a server across loops.**
- **`Pulse` cannot report `PREPARED`.** `WorkerRuntime` publishes no phase transitions, so the transport observes only "registered" and "task started" (D15). Teaching it more means changing what happens after a request is accepted — out of scope by `proposal.md:23`.
- **`max_execution_duration` is still enforced by nobody.** Pre-existing; D9 makes it visible rather than creating it.
- **`SecurityContext` stays three opaque strings.** Retyping is deferred as one unit until a security domain exists (`proposal.md:27`), matching tibios-core D10 exactly. The wire→domain step for it is therefore **infallible** and adds no rejection scenario.

## Key Contracts

```python
# execution/ids.py — D3 applies unchanged: frozen slotted dataclasses, never NewType
@dataclass(frozen=True, slots=True)
class WorkloadId:   value: str          # ULID; the sole correlation key for Cancel/Pulse
@dataclass(frozen=True, slots=True)
class AllocationId: value: str          # ULID

# execution/context.py — D9: one field, matching runtime-allocation's own shape
@dataclass(frozen=True, slots=True, kw_only=True)
class AllocationContract:
    max_execution_duration: timedelta   # intentionally partial; 15-allocation-model.md owns the rest

@dataclass(frozen=True, slots=True, kw_only=True)
class SecurityContext:                  # carried, never interpreted (18-worker-model.md:136)
    tenant_id: str
    principal_id: str
    grant_scope: tuple[str, ...]

@dataclass(frozen=True, slots=True, kw_only=True)
class ObservabilityContext:
    trace_id: str
    span_id: str

@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionContext:                 # D8: ten fields, eight of them wire-visible
    workload_id: WorkloadId
    allocation_id: AllocationId
    capability: str                     # <- wire WorkerCapability.value; name unchanged for WorkerRuntime
    allocation_contract: AllocationContract
    dependencies: tuple[ResolvedModelRef, ...]    # D10: ordered, unkeyed
    security_context: SecurityContext
    observability_context: ObservabilityContext
    execution_parameters: Mapping[str, str]
    channel: ExecutionChannel           # domain-only; the wire has no field, by design
    cancellation: CancellationToken     # domain-only; Cancel is an RPC (worker.proto:81-83)

# transport/errors.py — D17
class ErrorClass(Enum):  TRANSIENT = "transient"; PERMANENT = "permanent"; FATAL = "fatal"

class ConversionError(Exception):       # + InvalidUlidError, InvalidObjectVersionError,
    error_class = ErrorClass.PERMANENT  #   MissingFieldError, EmptyCapabilityError, NegativeDurationError
class CorrelationError(Exception):      # + UnknownWorkloadError (O3), DuplicateWorkloadError (O4)
    error_class = ErrorClass.PERMANENT

# transport/convert.py — pure, imports _pb2 but never grpc
def execution_context_from_wire(message, *, channel, cancellation) -> ExecutionContext: ...
def execution_event_to_wire(event: ExecutionEvent) -> worker_pb2.ExecutionEvent: ...
def execution_report_to_wire(report: ExecutionReport) -> worker_pb2.ExecutionReport: ...
def execution_pulse_to_wire(pulse: ExecutionPulse) -> worker_pb2.ExecutionPulse: ...
```

The capability boundary line, which is easy to get wrong: **the transport rejects structural violations; the runtime handles dispatch failures.** An unset or empty `worker_capability` means the sender sent nothing — `INVALID_ARGUMENT`, the stream never starts. A well-formed capability nobody serves means the Worker cannot do it — the stream starts and ends with a Failed `ExecutionReport`, via `WorkerRuntime`'s existing `UnknownCapabilityError` path, unchanged.

## File Changes

| File | Action | Slice | Description |
|---|---|---|---|
| `src/tibios_ray/execution/ids.py` | Modify | S1 | `WorkloadId`, `AllocationId` |
| `src/tibios_ray/execution/context.py` | Modify | S1 | `SecurityContext`, `ObservabilityContext`, narrowed `AllocationContract` (D9), tuple `dependencies` (D10), ten-field `ExecutionContext` (D8) |
| `src/tibios_ray/execution/report.py` | Modify | S1 | `ExecutionPhase.CANCELLED` |
| `src/tibios_ray/execution/__init__.py` | Modify | S1 | Re-exports + `__all__` |
| `src/tibios_ray/testing/context.py` | Modify | S1 | New fields; one-keyword default contract; `dependencies` sequence |
| `pyproject.toml` | Modify | S2 | `grpcio`, `protobuf`; `grpcio-tools` in dev; ruff/pyright excludes for `_generated/` |
| `scripts/generate_proto.py` | Create | S2 | `regenerate(into)` + `__main__` shim (D11) |
| `src/tibios_ray/transport/_generated/**` | Create | S2 | Checked-in codegen — reviewed by guard, not by eye |
| `src/tibios_ray/transport/{__init__,errors}.py` | Create | S2/S3 | Package surface; `ErrorClass` + both error families (D17) |
| `src/tibios_ray/transport/convert.py` | Create | S3 | Wire↔domain, pure, no `grpc` import |
| `src/tibios_ray/transport/{cancellation,channel,registry}.py` | Create | S4a | Cooperative token (D15), `GrpcExecutionChannel` (D14), in-flight registry (O1-O4) |
| `src/tibios_ray/transport/{servicer,server}.py` | Create | S4b | The three RPCs; `serve(runtime, address)` |
| `src/tibios_ray/server.py` | Modify | S4b | Entry point — replaces the docstring stub, imports **no** grpc (D13) |
| `src/tibios_ray/worker.py` | Modify | S4b | Composition root finally composes: seven Providers → `CapabilityRegistry` → one `WorkerRuntime` |
| `tests/unit/transport/**` | Create | S2-S4 | Drift, descriptor shape, isolation guard, rejection suite, lossiness, ordering, O1-O4 |
| `openspec/changes/.../specs/**` | Modify | S5 | The deltas named under Inputs to Downstream Phases |
| `src/tibios_ray/{runtime,capabilities,selection,backends,engines,catalog}/**` | Untouched | — | Dispatch and execution behavior are unchanged |

## Testing Strategy

Strict TDD — every rejection is a failing test first. No `pytest-asyncio` is installed; async assertions use `asyncio.run(...)` inside sync tests, matching the whole existing suite (LC precedent).

| Layer | What | Approach |
|---|---|---|
| Unit | Every rejection in `worker-wire-conversion`: invalid ULID (3 messages), non-numeric `ObjectVersion`, unset required message, unset/empty `worker_capability`, missing `allocation_contract`, negative duration | Hand-built `_pb2` messages; no server, no socket. Each asserts the raised type **and** `error_class is PERMANENT` |
| Unit | No conversion path panics | Parametrized over every malformed input above; assert a `ConversionError`, never a bare exception |
| Unit | Phase mapping is total and never `0` | `set(_PHASE_TO_WIRE) == set(ExecutionPhase)`, and `0 not in _PHASE_TO_WIRE.values()` |
| Unit | Lossiness is closed (D16) | An explicit enumeration test: for each domain type, the set of fields with no wire home equals the documented drop list. Adding a field breaks it |
| Unit | `summary` folding | Failed report → `summary == failure` verbatim; successful report → `summary == ""` |
| Unit | `EndOfStream.reason` is non-lossy | `WorkerRuntime.execute` on a failing Provider: `reason == report.failure`, and `failure` reaches `summary` |
| Unit | O1 | `Cancel` issued immediately after `SubmitJob` (before the first queue item) finds W registered — driven on one loop with no sleeps |
| Unit | O2 | Success, failure, and cancellation each followed by `Pulse` → unknown. Three outcomes, one parametrized test |
| Unit | O3 / O4 | `Cancel`/`Pulse` unknown → `NOT_FOUND`; duplicate `SubmitJob` → `ALREADY_EXISTS`, original unaffected |
| Unit | Report is last (D14) | Collect the whole stream; assert the last message's `payload` is `report`, exactly one `report` exists, and nothing follows — for both a completed and a cancelled execution |
| Unit | Isolation guard | The `test_no_engine_imports.py` scanner, retargeted: recursive AST scan of `src/tibios_ray/` **excluding** `transport/`, for `grpc`, `grpc_tools`, any `*_pb2*` module, and `importlib.import_module("<literal>")` of the same. Plus the same synthetic-nested-package + clean-tree pair, so recursion stays asserted rather than hoped |
| Unit | Drift + descriptor shape | D11's two guards |
| Type | Domain has no transport type in its signatures | pyright over `src`, unchanged; `_generated/` excluded |
| Integration | A real `grpc.aio` server on an ephemeral port: `SubmitJob` yields events then a terminal report; `Cancel` returns `CancelAck` and reaches the Provider's token; `Pulse` reports phase and health | `tests/integration/test_grpc_surface.py` — a real loopback socket, a stub Provider, no Ray, no engine |

## Slice Plan

Six chained PRs in five waves. `S1 ∥ S2` → `S3` → `S4a` → `S4b` → `S5`.

| # | Slice | Contents | Depends on | Est. hand-written lines |
|---|---|---|---|---|
| **S1** | Identity + context value types | `execution/{ids,context,report,__init__}.py`, `testing/context.py`, D8/D9/D10 in full, plus the updates D9 and D10 force on existing tests | — | ~300 |
| **S2** | Codegen + guards | `pyproject.toml`, `scripts/generate_proto.py`, `transport/{__init__}.py`, checked-in `_generated/`, drift + descriptor-shape + isolation guards | — | ~200 (+ generated bulk) |
| **S3** | Conversion + rejection suite | `transport/{errors,convert}.py` and every scenario in `worker-wire-conversion` | S1, S2 | ~350 |
| **S4a** | Correlation plumbing | `transport/{cancellation,channel,registry}.py` + O1-O4 unit tests, driven without a server | S3 | ~250 |
| **S4b** | Servicer + composition | `transport/{servicer,server}.py`, `server.py`, `worker.py`, ordering tests, integration test | S4a | ~300 |
| **S5** | Spec deltas | The four documents named below | S4b | ~150 |

### Review Workload Forecast

- **Estimated hand-written lines: ~1550**, plus generated bulk isolated in S2. 400-line budget risk: **High**.
- **Chained PRs recommended: Yes — mandatory.** No slice exceeds ~350 hand-written lines. S2's generated bulk is reviewed by its two guards, not by eye, which is the entire reason it is its own PR (`proposal.md:87`).
- **Decision needed before apply: Yes.** The delivery strategy must be resolved before `sdd-apply` starts. S3 (~350) is the largest; if it drifts past 400, the natural sub-split is identity-wrapper conversions / `ExecutionContext` + event/report conversions.
- Two natural stopping points where the tree is coherent and shippable: after wave 1 (value types and generated code landed, nothing consumes them yet) and after S4a (correlation proven, no server yet).

## Migration / Rollout

No migration. Additive except `pyproject.toml`, the `server.py`/`worker.py` docstrings, and three narrowings inside `execution/`: `AllocationContract`'s field set (D9), `dependencies`' type (D10), and `ExecutionContext`'s widened constructor (D8). Nothing under `runtime/`, `capabilities/`, `selection/`, `backends/`, `engines/`, or `catalog/` changes behavior — Providers still resolve and still raise `NoBackendAvailableError` exactly as today. `git revert` of the slice commits restores the current tree; the only non-mechanical reverts are the two narrowings, both contained to `execution/` and `testing/`.

## Inputs to Downstream Phases

**`sdd-spec` — four deltas this design creates, none of which the already-written specs cover:**

1. `worker-wire-conversion` — **add** three requirements: (a) a missing `allocation_contract` is rejected (the existing "Unset Required Message Fields" requirement names only *identity* fields); (b) a negative `google.protobuf.Duration` is rejected inbound and a negative domain duration is rejected outbound; (c) `dependencies` converts order-preservingly and no key is fabricated (D10). **Add** a fourth for D16: the domain→wire drop list is closed and enumerated.
2. `execution-identity` — **add** a requirement for D9: `AllocationContract` carries exactly `max_execution_duration`, cites `runtime-allocation` as the owner, and documents its partiality. Q3's resolution currently has **no normative home in any written spec**; this is the gap to close.
3. `worker-grpc-transport` — **add** the D17 status mapping (`INVALID_ARGUMENT` / `NOT_FOUND` / `ALREADY_EXISTS`), since "a classified error" is currently unpinned at the wire and tibios-core has to branch on it.
4. `worker-runtime` (delta) — two distinct inaccuracies in `specs/worker-runtime/spec.md`, both must be fixed:
   - **Cancellation scenario (`spec.md:22`)**: currently reads "a cancellation signal (Pulse) is received" — wrong against the frozen wire (`proposal.md`'s Modified Capabilities). `Pulse` is a Runtime-pulled health check; `Cancel` is the cancellation RPC returning `CancelAck`, *accepted* not *terminated* (`worker.proto:227-234`). Restate to name `Cancel`, plus the Report's position as always-last on the stream (D14).
   - **Pulse scenario**: currently reads "the Worker Runtime reports the execution's current phase and health" — per D15 the *transport* reports a transport-observable phase (`RECEIVED`/`RUNNING`), and `WorkerRuntime` publishes no transitions. Inaccurate as written.

**`sdd-tasks`** — the six-slice, five-wave graph above, with the Review Workload Forecast already stated. `proposal.md:64`'s placement of `WorkerExecutionServicer` in `server.py` is superseded by D13: it moves to `transport/servicer.py`, and `server.py` becomes a grpc-free entry point.

**`sdd-apply`** — the highest-friction items, none discoverable from the compiler, are listed under Gotchas below.

## Gotchas `sdd-apply` Must Know

**The import rewrite MUST be line-anchored.** `_pb2.py` contains a serialized `FileDescriptorProto` as a bytes literal, and that literal contains the string `tibios.worker.v1` (the proto package) and `tibios/worker/v1/worker.proto` (the proto path). A global `tibios.` → `tibios_ray.transport._generated.tibios.` substitution **corrupts the descriptor**, and the failure surfaces at import time as an opaque descriptor-pool error naming neither the cause nor the file. Rewrite only lines matching `^from tibios\.`, and have the script assert that the number of lines it changed equals the number it matched.

**One copy of each descriptor, ever.** Registering the same `.proto` file into the default descriptor pool twice raises `TypeError: Couldn't build proto file into descriptor pool: duplicate file name`. With a single checked-in tree this cannot happen — but it *will* happen if anyone adds a second generated copy or puts `_generated/` on `sys.path` as well as importing it as a package.

**protoc emits no `__init__.py`.** Every level of the mirrored tree needs one, written by the script deterministically (they are part of the byte-identity comparison).

**`grpcio` on Python 3.14 is the one dependency risk.** Pin ranges, not exact versions, and verify a `cp314` wheel exists at apply time; if none does, the fallback is pinning the lowest `grpcio` that ships one, and S2 fails fast rather than S4b failing mysteriously.

**The naming audit does not cover `transport/`.** `_AUDITED_PACKAGES` is `{capabilities, selection, backends, runtime, testing}` — so `WorkerExecutionServicer` and the generated `WorkerExecution*` symbols are fine where D13 puts them. They would **not** be fine in `testing/`, so no transport test double may be added there.

## Open Questions

- [ ] **Who enforces `max_execution_duration`?** `18-worker-model.md:56` says the Worker does; nothing does. Pre-existing, surfaced by D9, and a natural companion to the deployment change.
- [ ] **`CheckpointCreated.checkpoint_id` should be an `ObjectId`, not a `str`.** The wire already requires the wrapper; the domain does not carry the proof. Fixing it changes `execution/events.py` and every consumer — out of scope here, recorded so the wrapping in D16 is not mistaken for approval of the bare string.
- [ ] **How does a Provider name a specific dependency?** D10 refuses to invent a key. Until a `.proto` change adds a role/name field (cross-repo, out of scope), the interim rule is: a Provider needing exactly one dependency takes `dependencies[0]`; a Provider given more than one it cannot distinguish must fail rather than guess.
- [ ] **`maxsize=8` on the response queue** is a judgment call inherited from LC6, not a measurement. Revisit alongside the engine's queue when a real GPU stream exists.
- [ ] **Where does the server live in a Ray cluster?** D12 defers this by construction. Whoever writes the deployment change inherits the loop-affinity rule stated under Accepted Limitations.
- [ ] **`openspec/config.yaml`'s `testing:` block is stale** (`proposal.md:108`) — it claims no test runner while pytest/ruff/pyright have existed since `python-foundation`. Correct it out-of-band; Strict TDD applies to this change regardless.
