# Tasks: Worker Context Wiring (the gRPC boundary tibios-ray never grew)

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated hand-written lines (total, all slices) | **~1550**, unchanged from `design.md`'s Slice Plan — confirmed by this breakdown. Per-slice: S1 ~300, S2 ~200 (+ generated bulk, reviewed by its two guards, not by eye), S3a ~175, S3b ~175 (S3's original ~350 split in two — see below), S4a ~250, S4b ~300, S5 ~150. |
| 400-line budget risk | **High**, confirmed. |
| Chained PRs recommended | **Yes — mandatory**, confirmed. |
| S3's pre-agreed sub-split — **applied, not just flagged** | `design.md`'s Slice Plan named the fallback: *"S3 (~350) is the largest; if it drifts past 400, the natural sub-split is identity-wrapper conversions / `ExecutionContext` + event/report conversions."* Expanding S3 into concrete tasks below produces **19 tasks across two files' worth of conversion logic** (`transport/errors.py`'s two error families plus `transport/convert.py`'s inbound identity/context conversions, and separately its outbound event/report/pulse conversions carrying the full 10-row D16 lossiness table) — enough independent, individually-testable surface that landing it as one ~350-line PR is avoidable risk for zero benefit. **This breakdown pre-emptively applies the fallback**: S3 is planned as **S3a** (errors.py + inbound conversion: identity wrappers, `ExecutionContext`) → **S3b** (outbound conversion: event/report/pulse + D16 lossiness), sequentially chained, both touching `transport/convert.py` as stacked diffs. Total slice count rises from six to **seven**; total estimated lines is unchanged (the split does not add work, it re-draws one PR boundary). |
| Decision needed before apply | **Yes**, confirmed — `delivery_strategy` must be resolved before `sdd-apply` starts, per `design.md`. |
| Natural stopping points | Same two `design.md` identified: after Wave 1 (S1 + S2 landed, nothing consumes them yet) and after S4a (correlation proven, no server yet) — now Wave 4 in this seven-slice numbering. |

---

## Sequencing Notes

Six waves, seven slices, expanding `design.md`'s `S1 ∥ S2 → S3 → S4a → S4b → S5` with S3's pre-agreed sub-split inserted:

```
Wave 1:  S1 ∥ S2
Wave 2:  S3a            (depends on S1, S2)
Wave 3:  S3b            (depends on S3a)
Wave 4:  S4a            (depends on S3b)
Wave 5:  S4b            (depends on S4a)
Wave 6:  S5             (depends on S4b)
```

- **S1** and **S2** touch disjoint files (`execution/**` + `testing/context.py` vs. `pyproject.toml` + `scripts/` + `transport/_generated/**`) and share no runtime dependency on each other — authored, reviewed, and merged in parallel, exactly as `design.md` scoped them.
- **S3a** depends on both: it imports S1's widened `ExecutionContext`/`AllocationContract`/`SecurityContext`/`ObservabilityContext` and S2's generated `_pb2` messages.
- **S3b** depends on S3a only (same file, `transport/convert.py`, stacked diff) — not on S4a/S4b, since outbound conversion never touches the registry or the servicer.
- **S4a** depends on S3b because the registry's `CorrelationError` family is defined in S3a but the channel/queue's "Report always last" invariant (D14) is exercised against real converted values, and `GrpcExecutionChannel` wraps `execution_event_to_wire` (S3b) at its boundary in later integration tests — kept sequential rather than parallel to avoid a premature interface guess.
- **S4b** depends on S4a: the servicer composes conversion (S3a/S3b), the channel/registry/cancellation (S4a), and the error→status mapping (D17, started in S3a, completed in S4b).
- **S5** depends on S4b: it authors the four spec deltas `design.md`'s "Inputs to Downstream Phases" names. **These deltas are not yet in the spec files this change ships with** — confirmed by reading `specs/worker-wire-conversion/spec.md`, `specs/execution-identity/spec.md`, and `specs/worker-grpc-transport/spec.md` at task-planning time: none of the four additions design.md calls for (D9's missing-`allocation_contract`/negative-duration rejections, D10's order-preserving-no-key requirement, D16's closed lossiness list, D9's `AllocationContract` shape, D17's status-code mapping) are present yet. Only `specs/worker-runtime/spec.md`'s delta (the `Cancel`-not-`Pulse` restatement) is already correct as written. S1-S4b tasks therefore trace to **Architecture Decisions D8-D17 in `design.md` directly**, not to spec scenarios that don't exist yet; S5 is where those decisions get their normative home.

---

## S1 — Identity + Context Value Types

*(no dependencies; parallel with S2; satisfies `execution-identity/spec.md` in full plus D8/D9/D10)*

- [x] 1.1 Failing test in `tests/unit/execution/test_ids.py`: a raw `str` is not substitutable for `WorkloadId`/`AllocationId` at the type checker (pyright) and the two are distinct dataclass instances (`execution-identity` — "WorkloadId and AllocationId are type-distinct from raw strings"). Then implement `WorkloadId`, `AllocationId` in `src/tibios_ray/execution/ids.py` as frozen, slotted dataclasses wrapping `value: str`, mirroring `ObjectId`'s existing shape exactly (D3, never `NewType`).
- [x] 1.2 Failing test: two `WorkloadId` instances built from the same string value compare equal (`execution-identity` — "Equal values produce equal identities"). Confirm dataclass value semantics satisfy it with no extra code; add the assertion for `AllocationId` too.
- [x] 1.3 Failing test in `tests/unit/execution/test_context.py`: two contexts identical except for `SecurityContext` dispatch identically — no rejection or routing difference (`execution-identity` — "Dispatch outcome is independent of SecurityContext content"). Then add `SecurityContext(tenant_id: str, principal_id: str, grant_scope: tuple[str, ...])` to `src/tibios_ray/execution/context.py`, docstring stating it is carried, never interpreted (`18-worker-model.md:136`).
- [x] 1.4 Failing test: two contexts identical except for `ObservabilityContext` follow the same execution path (`execution-identity` — "Observability values pass through without altering execution"). Then add `ObservabilityContext(trace_id: str, span_id: str)`.
- [x] 1.5 Failing test: two contexts with different `execution_parameters` maps (including empty) resolve to the same Capability Provider (`execution-identity` — "Dispatch target is unaffected by execution_parameters content"). Then add `execution_parameters: Mapping[str, str]` to `ExecutionContext`.
- [x] 1.6 Failing test: constructing `AllocationContract` with only `max_execution_duration` succeeds, and the five removed fields (`exclusive`, `renewable_lease`, `preemptible`, `migration_allowed`, `checkpoint_required`) are no longer accepted keyword arguments (D9). Then narrow `AllocationContract` in `context.py` to the single field; update its docstring to state the partiality explicitly and name `15-allocation-model.md` as the future owner of the remaining facets — mirroring `runtime-allocation/spec.md:59-63` verbatim in spirit, per D9's decisive-ownership argument.
- [ ] 1.7 Failing test: `ExecutionContext.dependencies` accepts a `tuple[ResolvedModelRef, ...]` and preserves construction order; a `dict`/`Mapping` argument is no longer the declared type (D10). Then change `dependencies` from `Mapping[str, ResolvedModelRef]` to `tuple[ResolvedModelRef, ...]`.
- [ ] 1.8 Failing test: `ExecutionContext` constructs with all ten keyword-only fields — `workload_id`, `allocation_id`, `capability`, `allocation_contract`, `dependencies`, `security_context`, `observability_context`, `execution_parameters`, `channel`, `cancellation` (D8). Then widen the dataclass; confirm `kw_only=True` already set means no positional call site breaks (D8 rationale).
- [ ] 1.9 Failing test in `tests/unit/execution/test_report.py`: `ExecutionPhase` has a `CANCELLED` member (sixth state, matching the wire's six-value enum). Then add `CANCELLED = "cancelled"` to `src/tibios_ray/execution/report.py`.
- [ ] 1.10 Update `src/tibios_ray/execution/__init__.py`: re-export `WorkloadId`, `AllocationId`, `SecurityContext`, `ObservabilityContext`; add all four to `__all__` (alphabetical, matching existing convention).
- [ ] 1.11 Update `src/tibios_ray/testing/context.py`: `_default_allocation_contract()` shrinks to `AllocationContract(max_execution_duration=timedelta(minutes=5))` (D9 Consequences — the change's only non-mechanical revert, already anticipated); `FakeExecutionContext.__new__` gains `workload_id`, `allocation_id`, `security_context`, `observability_context`, `execution_parameters` parameters with test-friendly defaults (e.g. a fixed ULID-shaped string, empty tuple/mapping); `dependencies` parameter and default change from `Mapping[str, ResolvedModelRef] | None` / `{}` to `tuple[ResolvedModelRef, ...] | None` / `()`.
- [ ] 1.12 Update every existing test that breaks from 1.6/1.7/1.8: `tests/unit/execution/test_context.py` (six-field `AllocationContract` construction, `dependencies["model"]`-style indexing) and `tests/unit/testing/test_testing_context.py`, per D9 Consequences — the two tests this decision explicitly names.
- [ ] 1.13 Self-review: `uv run pytest tests/unit/execution tests/unit/testing`; `ruff check`; `pyright` — all green. Confirm no other module under `src/tibios_ray/` constructs `AllocationContract` with the five removed fields (recursive check, D9's "verified rather than assumed" claim re-confirmed against the current tree).

---

## S2 — Codegen + Guards

*(no dependencies; parallel with S1; satisfies `worker-grpc-transport/spec.md`'s isolation and drift-guard requirements; D11)*

- [ ] 2.1 Update `pyproject.toml`: add `grpcio` and `protobuf` to `[project] dependencies` as **pinned ranges, not exact versions** (Gotcha — `grpcio` on Python 3.14 is the one dependency risk); add `grpcio-tools` to `[dependency-groups] dev` only (never install-time). Verify a `cp314` wheel exists for the chosen `grpcio` range at apply time; if none does, fall back to the lowest `grpcio` version that ships one and note the pin in a comment, so this slice fails fast rather than S4b failing mysteriously.
- [ ] 2.2 Update `pyproject.toml`: add `_generated/` to `[tool.ruff] extend-exclude` and to `[tool.pyright] exclude` (excludes from the *checked* set while still using it for import-site inference).
- [ ] 2.3 Failing test in `tests/unit/transport/test_generate_proto.py`: the import-rewrite step in `scripts/generate_proto.py` (loaded via `importlib.util.spec_from_file_location`, same technique the drift guard will reuse) rewrites **only** lines matching `^from tibios\.`, and asserts the number of lines it changed equals the number of lines it matched — proving no other occurrence of the substring `tibios.` (including inside the serialized `FileDescriptorProto` bytes literal) is touched (Gotcha: line-anchored import rewrite; a global substitution corrupts the descriptor pool). Use a small synthetic sample file mixing a real `from tibios.` import line with an embedded `b"...tibios.worker.v1..."` bytes literal to prove the distinction.
- [ ] 2.4 Implement `scripts/generate_proto.py`: a plain module (not a `[project.scripts]` entry — `uv_build` exposes no build-hook API, and this design does not change the build backend to acquire one, D11) exposing `regenerate(into: Path) -> None` plus a `__main__` shim invoked as `uv run python scripts/generate_proto.py`. It shells out to `grpc_tools.protoc` against `../proto`, writes into the mirrored tree, applies 2.3's line-anchored rewrite, and — since protoc emits none (Gotcha) — writes a deterministic `__init__.py` at every level of the generated tree (required for byte-identity in the drift guard).
- [ ] 2.5 Run `uv run python scripts/generate_proto.py` against `../proto`; check in the resulting tree at `src/tibios_ray/transport/_generated/tibios/{worker,primitives}/v1/*_pb2.py`, `*_pb2.pyi`, `*_pb2_grpc.py`, with generated `__init__.py` at every level.
- [ ] 2.6 Failing test in `tests/unit/transport/test_proto_drift.py`: regenerating from `../proto` into `tmp_path` produces output byte-identical to the checked-in tree (`worker-grpc-transport` — "Drift guard passes against the checked-in tree"). Skip with an explicit reason if `../proto` or `grpc_tools` is absent. Add a companion non-vacuity test (the `test_backends_package_has_python_source_files_to_check` precedent, `tests/unit/backends/test_no_engine_imports.py:83-86`) asserting the checked-in `_generated/` tree is non-empty, so the drift test cannot pass vacuously against zero files.
- [ ] 2.7 Failing test in `tests/unit/transport/test_descriptor_shape.py`: the version-independent semantic guard — reading the generated descriptors, `WorkerExecution` has exactly three RPCs and the wire `ExecutionContext` message has exactly eight fields (D11's second guard, immune to a `grpcio-tools`/`protobuf` version bump that would only redden byte-identity).
- [ ] 2.8 Failing test in `tests/unit/transport/test_no_duplicate_descriptor.py`: importing `src/tibios_ray/transport/_generated/tibios/worker/v1/worker_pb2` twice (e.g. via `importlib.reload` or two independent import paths) does not raise `TypeError: Couldn't build proto file into descriptor pool: duplicate file name` (Gotcha: one copy of each descriptor, ever). Document in the test/module docstring that this invariant depends on there being exactly one checked-in copy and `_generated/` never being added to `sys.path` in addition to being imported as a package — the failure mode this test exists to catch if someone later violates that.
- [ ] 2.9 Create `src/tibios_ray/transport/__init__.py` — minimal package surface, no `grpc`/`_pb2` re-exports beyond what the package needs to expose later (S3a starts filling it in).
- [ ] 2.10 Failing test in `tests/unit/transport/test_isolation_guard.py`: retarget the `tests/unit/backends/test_no_engine_imports.py` scanner (same AST-walk technique for plain imports and `importlib.import_module("<literal>")` string imports) at `src/tibios_ray/`, **excluding** `transport/`, scanning for `grpc`, `grpc_tools`, and any module matching `*_pb2*` (`worker-grpc-transport` — "Recursive scan finds zero transport imports outside the package"). Include the same synthetic-nested-package + clean-tree pair (`test_scanner_recurses_into_nested_packages`, `test_scanner_finds_no_offenders_in_a_clean_nested_package` precedent) so recursion is asserted, not hoped. Confirm it passes now (nothing outside `transport/` imports anything yet).
- [ ] 2.11 Self-review: `uv run pytest tests/unit/transport`; `ruff check`; `pyright` — `_generated/` excluded from both, confirmed by inspecting their reported file counts; confirm `pyproject.toml`'s new deps resolve with `uv sync`.

---

## S3a — Errors + Inbound Conversion (Identity Wrappers, ExecutionContext)

*(depends on S1, S2; satisfies `worker-wire-conversion/spec.md`'s identity-wrapper, unset-field, and worker_capability requirements in full, plus D9/D10/D17; traces D9's missing-`allocation_contract`/negative-duration-inbound rejections and D10's no-fabricated-key rule directly to `design.md`, since these are not yet in the spec text — see Sequencing Notes)*

- [ ] 3a.1 Failing test in `tests/unit/transport/test_errors.py`: `ErrorClass` has exactly `TRANSIENT`, `PERMANENT`, `FATAL` members. Then create `src/tibios_ray/transport/errors.py` with `class ErrorClass(Enum)` (D17).
- [ ] 3a.2 Failing test: `ConversionError` and its five subclasses — `InvalidUlidError`, `InvalidObjectVersionError`, `MissingFieldError`, `EmptyCapabilityError`, `NegativeDurationError` — all classify `ErrorClass.PERMANENT`. Then implement the `ConversionError` family in `errors.py`.
- [ ] 3a.3 Failing test: `CorrelationError` and its two subclasses — `UnknownWorkloadError`, `DuplicateWorkloadError` — both classify `ErrorClass.PERMANENT`. Then implement the `CorrelationError` family (consumed later by S4a's registry and S4b's servicer; defined here per D17's single-hierarchy decision).
- [ ] 3a.4 Failing test in `tests/unit/transport/test_convert.py`: a well-formed wire `ObjectId`/`WorkloadId`/`AllocationId`/`ObjectVersion`/`ContentHash` converts successfully and reproduces the wire value (`worker-wire-conversion` — "Well-formed identity value converts successfully"). Then create `src/tibios_ray/transport/convert.py` (imports `_pb2`, never `grpc`) with the five identity-wrapper conversion helpers.
- [ ] 3a.5 Failing test: an `ObjectId`/`WorkloadId`/`AllocationId` wire message with a non-ULID `value` raises `InvalidUlidError`, never defaults (`worker-wire-conversion` — "Invalid ULID text is rejected, not defaulted"). Then implement the rejection.
- [ ] 3a.6 Failing test: an `ObjectVersion` wire message whose `value` is not a valid unsigned 64-bit integer raises `InvalidObjectVersionError` (`worker-wire-conversion` — "Non-numeric ObjectVersion text is rejected, not defaulted"). Then implement.
- [ ] 3a.7 Failing test: a wire `ExecutionContext`, `CancelRequest`, `PulseRequest`, or `ResolvedModelRef` with a required identity field unset raises `MissingFieldError` naming the missing field, no placeholder fabricated (`worker-wire-conversion` — "Missing required identity field fails conversion"). Then implement across all four message types.
- [ ] 3a.8 Failing test: converting a wire `ExecutionContext.dependencies` (`repeated ResolvedModelRef`) produces a domain `tuple[ResolvedModelRef, ...]` preserving wire order, with no key of any kind constructed from `object_id` or position (D10 — no written spec scenario yet, traced directly to D10's rejection of every keying alternative). Then implement `ResolvedModelRef` conversion and the tuple-building step.
- [ ] 3a.9 Failing test: a wire `ExecutionContext` whose `worker_capability` is unset raises `MissingFieldError` naming the field (`worker-wire-conversion` — "Missing worker_capability is rejected"). Then implement.
- [ ] 3a.10 Failing test: a wire `ExecutionContext` whose `worker_capability.value` is an empty string raises `EmptyCapabilityError`, neither accepted nor defaulted (`worker-wire-conversion` — "Empty worker_capability is rejected"). Then implement.
- [ ] 3a.11 Failing test: a wire `ExecutionContext` with `allocation_contract` unset raises a classified rejection, never a default (D9 — "Absent `allocation_contract` on the wire is a `Permanent` rejection, never a default"; not yet in spec text, traced to D9 directly). Then implement, reusing `MissingFieldError` or a dedicated variant — pick one and record the choice in the docstring.
- [ ] 3a.12 Failing test: a wire `allocation_contract.max_execution_duration` carrying a negative `google.protobuf.Duration` raises `NegativeDurationError` inbound (D9 — "A negative `google.protobuf.Duration` is a `Permanent` rejection"; Python's `timedelta` can represent negative values unlike Rust, so this is an explicit check, not a type-level guarantee). Then implement a shared `Duration -> timedelta` conversion helper with the negative check, used here and reused by S3b's outbound duration check.
- [ ] 3a.13 Failing test: `execution_context_from_wire(message, *, channel, cancellation)` composes a full domain `ExecutionContext` from a well-formed wire message — `security_context`, `observability_context`, `execution_parameters` carried verbatim (execution-identity's carried-never-interpreted rule, re-verified at this boundary), `workload_id`/`allocation_id` parsed via 3a.4-3a.5, `capability` via 3a.9-3a.10, `allocation_contract` via 3a.11-3a.12, `dependencies` via 3a.8, `channel`/`cancellation` passed through from the caller (domain-only, D8). Then implement the full function signature from `design.md`'s Key Contracts.
- [ ] 3a.14 Failing test (parametrized): every rejection variant introduced in this slice — invalid ULID (×3 message types), non-numeric `ObjectVersion`, unset required field, unset/empty `worker_capability`, missing `allocation_contract`, negative duration — classifies `ErrorClass.PERMANENT` (`worker-wire-conversion` — "Every rejection variant classifies as Permanent"). Assert the raised type **and** `error_class is ErrorClass.PERMANENT` for each.
- [ ] 3a.15 Failing test (parametrized, same malformed inputs as 3a.14): no conversion path panics — every case raises a `ConversionError` subclass, never a bare/unguarded exception (`worker-wire-conversion` — "No conversion path panics on malformed input").
- [ ] 3a.16 Self-review: `uv run pytest tests/unit/transport/test_errors.py tests/unit/transport/test_convert.py`; `ruff check`; `pyright`. Confirm `convert.py`'s import list contains `_pb2` symbols and zero `grpc` symbols (spot check — S2's isolation guard does not yet cover `transport/` internals, only what's outside it).

---

## S3b — Outbound Conversion (Event/Report/Pulse) + D16 Lossiness

*(depends on S3a; satisfies `worker-wire-conversion/spec.md`'s `ExecutionPhase` mapping requirement; traces the full D16 lossiness table directly to `design.md`, since no written spec scenario covers it yet — see Sequencing Notes)*

- [ ] 3b.1 Failing test in `tests/unit/transport/test_convert.py`: converting each value of the domain `ExecutionPhase` enum (six values, including S1's new `CANCELLED`) to its wire counterpart produces a defined, non-zero value; `EXECUTION_PHASE_UNSPECIFIED` is never produced (`worker-wire-conversion` — "Every domain phase maps to a defined wire phase"). Then implement `_PHASE_TO_WIRE: Mapping[ExecutionPhase, int]` in `convert.py`, asserting its key set equals `set(ExecutionPhase)` at import time or via a dedicated test.
- [ ] 3b.2 Failing test: a negative domain `ExecutionReport.duration` raises a classified `PERMANENT` error outbound (D9 Consequences — "Same treatment for `ExecutionReport.duration` outbound"). Then implement, reusing 3a.12's `timedelta -> Duration` direction of the shared helper.
- [ ] 3b.3 Failing test: `ExecutionReport.trace_id` maps to wire `trace_id` verbatim (D16 row: `trace_id` — "Mapped verbatim"). Then implement.
- [ ] 3b.4 Failing test: a failed report (`failure` set) produces wire `summary == failure` verbatim; a successful report (`failure is None`) produces `summary == ""` (D16 row: `failure` → `summary` — "Folded... two tests, not a silent default"). Then implement the folding rule in `execution_report_to_wire`.
- [ ] 3b.5 Failing test: `execution_report_to_wire` never sets a `resource_usage`/`metrics`-equivalent field on the wire message, and no code path in `convert.py` synthesizes a `MetricsSnapshot` event from a domain report's `resource_usage`/`metrics` (D16 row — "Dropped, by contract design... The transport does not synthesize one"). Document the relocation (Report → event stream's `MetricsSnapshot` arm) in the function's docstring.
- [ ] 3b.6 Failing test: `execution_report_to_wire` never carries `logs` onto the wire (D16 row — "Dropped... the correct fix, if ever needed, is a `.proto` change"). Document in the docstring.
- [ ] 3b.7 Failing test: converting a domain `Warning` event drops `code` and does **not** prefix it into `message` in any form (D16 row — "Dropped... inventing a `[code] msg` parse format on a frozen contract creates an unversioned side-channel"). Then implement the `Warning` arm of `execution_event_to_wire`.
- [ ] 3b.8 Failing test: `EndOfStream.reason` never reaches the wire (the wire `EndOfStream` is empty), and — driving `WorkerRuntime.execute` against a failing fixture Provider — the information is demonstrably non-lossy because `reason` derives from `report.failure`, which reaches `summary` via 3b.4 (D16 row — "Dropped, and demonstrably non-lossy on the only path that sets it"). Then implement the `EndOfStream` arm (drops `reason` unconditionally).
- [ ] 3b.9 Failing test: `execution_pulse_to_wire` never carries `detail` onto the wire; confirm by recursive search of `src/` that nothing constructs an `ExecutionPulse` with `detail` set (D16 row — "Dropped. Set by nothing, anywhere (verified)"). Then implement `execution_pulse_to_wire`'s phase/health-only mapping.
- [ ] 3b.10 Failing test: a domain `Progress.message` of `None` converts to wire `message == ""` (D16 row — "proto3 has no absent scalar; documented"). Then implement the `Progress` arm.
- [ ] 3b.11 Failing test: `OutputChunk.sequence` of a negative value or `>= 2**64` raises a classified `PERMANENT` error rather than being truncated (D16 row — "a Worker bug, surfaced rather than truncated"). Then implement the `OutputChunk` arm with the range check.
- [ ] 3b.12 Failing test: `CheckpointCreated.checkpoint_id` wraps verbatim into the wire's `ObjectId checkpoint_object_id` with no ULID validation performed at this boundary (D16 row — "the owning domain defines validity and the adapter does not second-guess," mirroring tibios-core's `ContentHash` treatment). Then implement the `CheckpointCreated` arm; note in Open Questions cross-reference that the underlying `str`-vs-`ObjectId` domain debt is out of scope here.
- [ ] 3b.13 Failing test in `tests/unit/transport/test_lossiness.py`: an explicit enumeration test — for each domain type (`ExecutionReport`, `ExecutionPulse`, `Warning`, `EndOfStream`) the set of fields with no wire home equals the documented D16 drop list exactly; adding an undocumented dropped field breaks the test (D16 — "the drop list is closed and asserted by test... adding a seventh domain field forces a decision rather than a silent extension"). Then implement/confirm the enumeration against 3b.5-3b.12's shipped behavior.
- [ ] 3b.14 Implement `execution_event_to_wire(event: ExecutionEvent) -> worker_pb2.ExecutionEvent`, composing all six arms (3b.7, 3b.8, 3b.10, 3b.11, 3b.12, plus the trivial pass-through arms for any event types not covered above).
- [ ] 3b.15 Implement `execution_report_to_wire(report: ExecutionReport) -> worker_pb2.ExecutionReport` and `execution_pulse_to_wire(pulse: ExecutionPulse) -> worker_pb2.ExecutionPulse` in full, composing 3b.1-3b.6 and 3b.9 respectively.
- [ ] 3b.16 Self-review: `uv run pytest tests/unit/transport/test_convert.py tests/unit/transport/test_lossiness.py`; `ruff check`; `pyright`. Re-confirm `convert.py` still imports zero `grpc` symbols after this slice's additions.

---

## S4a — Correlation Plumbing (Cancellation, Channel, Registry)

*(depends on S3b; satisfies `worker-grpc-transport/spec.md`'s O1-O4 requirements in full plus D14/D15; driven without a server, per `design.md`'s Testing Strategy)*

- [ ] 4a.1 Failing test in `tests/unit/transport/test_cancellation.py`: a transport-minted `CancellationToken` starts uncancelled, `wait()` returns once `cancel()` is called, and calling `cancel()` twice does not raise (D15 — "the token must be minted by the transport... not from `testing/`, because production code importing a test double is a layering inversion"). Then create `src/tibios_ray/transport/cancellation.py` (~12 lines per `design.md`) implementing `ExecutionChannel`'s companion protocol from `execution/channel.py`.
- [ ] 4a.2 Failing test in `tests/unit/transport/test_channel.py`: `GrpcExecutionChannel.emit(event)` puts the wire-converted event (via S3b's `execution_event_to_wire`) onto a bounded `asyncio.Queue(maxsize=8)` (D14 — matches LC6's judgment call). Then create `src/tibios_ray/transport/channel.py` implementing `ExecutionChannel`.
- [ ] 4a.3 Failing test: `GrpcExecutionChannel.emit` awaits (backpressures) rather than raising when the queue is full at `maxsize=8`, mirroring the engine-hop precedent (`05-async-concurrency.md`'s backpressure rule, LC6). Then confirm/implement via plain `asyncio.Queue.put` semantics (no `put_nowait`).
- [ ] 4a.4 Failing test in `tests/unit/transport/test_registry.py`: registering a `WorkloadId` is synchronous — completes with no `await` inside it — and the entry's phase starts at `RECEIVED` (D15). Then create `src/tibios_ray/transport/registry.py` with a `register(workload_id, token, task)` method and an entry dataclass holding `{token, task, phase}`.
- [ ] 4a.5 Failing test: marking a registered entry as started transitions its phase to `RUNNING`; the registry has no code path that ever reports `PREPARED` (D15 — "`WorkerRuntime` publishes no phase transitions, so `PREPARED` is genuinely unobservable... reporting `RUNNING` for a not-yet-started task would be a lie"). Then implement the phase-transition method.
- [ ] 4a.6 Failing test (O1): a `Cancel` call for `WorkloadId` W issued immediately after `register(W, ...)` — before the first `await` in the calling coroutine — finds W already registered (`worker-grpc-transport` — "A Cancel issued immediately after SubmitJob is observed"). Drive on one loop, no sleeps. Confirms 4a.4's registration is genuinely synchronous.
- [ ] 4a.7 Failing test (O2, parametrized over success/failure/cancellation outcomes): after `deregister(W)` is called, a subsequent `Pulse`-equivalent lookup for W raises `UnknownWorkloadError`, for all three outcomes in one parametrized test (`worker-grpc-transport` — "Registry entry is removed after completion in every outcome"). Then implement `deregister`.
- [ ] 4a.8 Failing test (O3): looking up an unregistered `WorkloadId` raises `CorrelationError.UnknownWorkloadError` (from S3a), never a silent `None`/success (`worker-grpc-transport` — both Cancel-for-unknown and Pulse-for-unknown scenarios, exercised here at the registry level before S4b wires them to RPCs). Then implement the lookup method's rejection.
- [ ] 4a.9 Failing test (O4): calling `register` a second time for an already-registered `WorkloadId` raises `CorrelationError.DuplicateWorkloadError` without disturbing the first entry (`worker-grpc-transport` — "Duplicate SubmitJob is rejected without disturbing the original"). Then implement the duplicate check in `register`.
- [ ] 4a.10 Failing test: calling `cancel()` on an already-cancelled token (still registered) does not raise and returns successfully both times — cancel is idempotent while registered (D15 — "`Cancel` is idempotent while registered (tibios-core D11)"). Confirms/extends 4a.1.
- [ ] 4a.11 Self-review: `uv run pytest tests/unit/transport/test_cancellation.py tests/unit/transport/test_channel.py tests/unit/transport/test_registry.py` — every test driven with `asyncio.run(...)` inside a sync test function, no `pytest-asyncio` (matches the whole existing suite, LC precedent); `ruff check`; `pyright`.

---

## S4b — Servicer + Composition

*(depends on S4a; satisfies `worker-grpc-transport/spec.md`'s three-RPCs and stream-ordering requirements in full, plus D12/D13/D14/D17; `worker-runtime/spec.md` delta's Cancel/Pulse restatement becomes exercised, not just documented)*

- [ ] 4b.1 Failing test in `tests/unit/transport/test_servicer.py`: `SubmitJob` registers the converted request's `WorkloadId` in the S4a registry synchronously before its first `await` (O1, re-verified at the servicer level, not just the registry level). Then create `src/tibios_ray/transport/servicer.py` with `WorkerExecutionServicer` subclassing the generated `WorkerExecutionServicer` base (S2's `_pb2_grpc.py`), implementing the `SubmitJob` skeleton: `convert.execution_context_from_wire` → `registry.register` → `asyncio.Queue(maxsize=8)` → `create_task(runtime.execute(ctx))`, per `design.md`'s sequence diagram.
- [ ] 4b.2 Failing test: a `ConversionError` raised during `execution_context_from_wire` inside `SubmitJob` is translated to a gRPC `INVALID_ARGUMENT` status before the response stream starts, and the stream never starts (D17 — "the transport rejects structural violations... the stream never starts"). Then implement the rejection path.
- [ ] 4b.3 Failing test: the `SubmitJob` response stream yields `Response(event=...)` for each item the queue produces (converted via S3b) and `Response(report=...)` exactly once for the terminal `_Done` item, then the loop breaks (D14). Then implement the drain loop.
- [ ] 4b.4 Failing test: for a completed execution, collecting the whole `SubmitJob` response stream shows the last message wraps `report`, exactly one `report` message exists, and nothing follows (`worker-grpc-transport` — "Successful execution ends with the terminal report last"). Then confirm/adjust the loop's break condition.
- [ ] 4b.5 Failing test: for an execution cancelled mid-flight via `Cancel`, the response stream still ends with the terminal report last — never omitted, never followed by further events (`worker-grpc-transport` — "Cancelled execution still ends with the terminal report last"). Then confirm/adjust cancellation handling in the loop.
- [ ] 4b.6 Failing test: `SubmitJob`'s `finally` block closes the channel and cancels the token with no `await` inside `finally`, and deregisters the `WorkloadId` on every outcome — success, failure, cancellation (O2, re-verified at the servicer level). Then implement the `finally` block per `design.md`'s sequence diagram.
- [ ] 4b.7 Failing test: `Cancel` for an in-flight `WorkloadId` returns `CancelAck` and signals the registered `CancellationToken` (reaching a stub Provider's cooperative check); `Cancel` for an unknown `WorkloadId` raises a gRPC `NOT_FOUND`-classified error, never a `CancelAck` (O3, `worker-grpc-transport`, D17's fixed mapping: unknown `WorkloadId` → `NOT_FOUND`). Then implement the `Cancel` RPC handler.
- [ ] 4b.8 Failing test: `Pulse` for a known `WorkloadId` reports the S4a registry's transport-observable phase (`RECEIVED`/`RUNNING`) and health; `Pulse` for an unknown `WorkloadId` raises the same `NOT_FOUND`-classified error (O3, D15). Then implement the `Pulse` RPC handler.
- [ ] 4b.9 Failing test: a second `SubmitJob` for an already-registered `WorkloadId` raises a gRPC `ALREADY_EXISTS`-classified error without starting a second execution, and the original execution proceeds unaffected (O4, D17's fixed mapping: duplicate `WorkloadId` → `ALREADY_EXISTS`). Then implement the rejection in `SubmitJob`, reusing S4a's `DuplicateWorkloadError`.
- [ ] 4b.10 Failing test: the classified-error-to-gRPC-status mapping is total and fixed — `ConversionError` family → `INVALID_ARGUMENT`, `UnknownWorkloadError` → `NOT_FOUND`, `DuplicateWorkloadError` → `ALREADY_EXISTS` — and nothing ever surfaces as `UNKNOWN` (D17). Then implement the mapping as a small helper in `servicer.py` or `errors.py`, consumed by 4b.2/4b.7/4b.8/4b.9.
- [ ] 4b.11 Implement `src/tibios_ray/transport/server.py`'s `serve(runtime: WorkerRuntime, address: str) -> None`: creates `grpc.aio.server()` and serves it **on the same event loop that will serve it** (D12's stated rule), registers `WorkerExecutionServicer(runtime)`. This is the one function outside `server.py`/`servicer.py` allowed to import `grpc`, per D13.
- [ ] 4b.12 Update `src/tibios_ray/server.py`: replace the docstring stub with a grpc-free process entry point — `asyncio.run(tibios_ray.transport.serve(worker.build_runtime(), address))` or equivalent — importing **no** `grpc` or `_pb2` symbol at this level (D13).
- [ ] 4b.13 Update `src/tibios_ray/worker.py`: replace the placeholder docstring with the composition root — instantiate the seven Capability Providers, build one `CapabilityRegistry`, hand it to one `WorkerRuntime`, expose a `build_runtime() -> WorkerRuntime` (or equivalent) for `server.py` to call. Zero `grpc`/`_pb2` import (D13).
- [ ] 4b.14 Failing test: re-run/extend S2's isolation guard (2.10) against the tree as it stands after this slice — `server.py` and `worker.py` still import zero `grpc`/`_pb2` symbols; confirm zero matches outside `transport/` (`worker-grpc-transport` — "Recursive scan finds zero transport imports outside the package", now exercised against the finished tree, not just the empty one).
- [ ] 4b.15 Failing integration test in `tests/integration/test_grpc_surface.py`: a real `grpc.aio.server()` on an ephemeral port, a stub Capability Provider (no Ray, no engine) — `SubmitJob` yields events then a terminal report; `Cancel` returns `CancelAck` and reaches the Provider's `CancellationToken`; `Pulse` reports phase and health (`design.md` Testing Strategy). Then wire it up end-to-end via `transport.serve` + a real client stub.
- [ ] 4b.16 Self-review: `uv run pytest tests/unit/transport tests/integration/test_grpc_surface.py`; `ruff check`; `pyright`; confirm the naming audit (`_AUDITED_PACKAGES = {capabilities, selection, backends, runtime, testing}`) still finds zero violations, and confirm no transport test double was added under `testing/` (Gotcha — `WorkerExecutionServicer` and generated `WorkerExecution*` symbols are fine in `transport/`, would not be fine in `testing/`).

---

## S5 — Spec Deltas

*(depends on S4b; authors the four spec deltas `design.md`'s "Inputs to Downstream Phases" names — confirmed NOT yet present in the spec files, per Sequencing Notes — plus confirms the one delta that already is)*

- [ ] 5.1 Add to `specs/worker-wire-conversion/spec.md`: a new requirement stating a missing `allocation_contract` on a wire `ExecutionContext` is rejected (D9), with a scenario mirroring S3a's 3a.11 test.
- [ ] 5.2 Add to `specs/worker-wire-conversion/spec.md`: a new requirement stating a negative `google.protobuf.Duration` is rejected both inbound (`allocation_contract.max_execution_duration`) and outbound (`ExecutionReport.duration`) (D9 Consequences), with scenarios mirroring 3a.12 and 3b.2.
- [ ] 5.3 Add to `specs/worker-wire-conversion/spec.md`: a new requirement stating `dependencies` converts order-preservingly from the wire's `repeated ResolvedModelRef` into the domain's `tuple[ResolvedModelRef, ...]`, with no key fabricated from `object_id` or position (D10), with a scenario mirroring 3a.8.
- [ ] 5.4 Add to `specs/worker-wire-conversion/spec.md`: a new requirement stating the domain→wire lossiness drop list is closed and enumerated (D16), naming every row of the table (`resource_usage`/`metrics`/`logs` dropped; `Warning.code` dropped, never prefixed; `EndOfStream.reason` dropped and non-lossy; `Progress.message` `None`→`""`; `OutputChunk.sequence` range-checked; `CheckpointCreated.checkpoint_id` wrapped verbatim; `failure`→`summary` folded), with a scenario mirroring 3b.13's enumeration test.
- [ ] 5.5 Add to `specs/execution-identity/spec.md`: a new requirement — `AllocationContract` carries exactly `max_execution_duration` (D9), cites `runtime-allocation` as the owning domain per `02-project-structure.md`'s Ownership Boundaries table, documents the partiality and names `15-allocation-model.md` as the future owner of the remaining facets, with a scenario mirroring 1.6's construction test.
- [ ] 5.6 Add to `specs/worker-grpc-transport/spec.md`: a new requirement — classified errors map to fixed gRPC status codes (D17): conversion rejection → `INVALID_ARGUMENT`; unknown `WorkloadId` → `NOT_FOUND`; duplicate `WorkloadId` → `ALREADY_EXISTS`; nothing ever surfaces `UNKNOWN`, with a scenario mirroring 4b.10's mapping test.
- [ ] 5.7 Confirm `specs/worker-runtime/spec.md`'s delta (already committed) matches the shipped `Cancel`/`Pulse` behavior exactly — the cancellation scenario names `Cancel`, not `Pulse`, and states the Report's always-last position (D14); the Pulse scenario states the transport, not `WorkerRuntime`, reports the observable phase (D15). No edit expected; if a mismatch is found, reconcile the spec against the shipped decision (D14/D15), not ad hoc, and flag it for `sdd-verify` rather than silently patching either side.
- [ ] 5.8 Cross-check every `proposal.md` Success Criterion against the task(s) that satisfy it (table below); flag and record any gap found rather than silently closing it.
- [ ] 5.9 Full gate: `uv run pytest`, `ruff check`, `pyright` all pass across the whole tree; the naming audit finds zero violations; the recursive import guard (2.10/4b.14) and the drift guard (2.6) both pass on the final tree; `openspec/config.yaml`'s stale `testing:` block is corrected out-of-band (`proposal.md:108` — noted, not blocking).

### Task 5.8 — Success Criteria Cross-Check

| # | Success Criterion (`proposal.md`) | Satisfied by |
|---|---|---|
| 1 | A real gRPC `SubmitJob` call produces Execution Events and exactly one terminal `ExecutionReport`, last on the stream | 4b.3-4b.5, 4b.15 |
| 2 | `Cancel` returns `CancelAck` for an in-flight execution and reaches the Provider's `CancellationToken`; `Pulse` reports phase and health | 4a.10, 4b.7-4b.8, 4b.15 |
| 3 | Every rejection scenario in `worker-wire-adapter/spec.md` has a passing tibios-ray counterpart — no path panics, no path defaults | 3a.4-3a.15, 3b.1-3b.13 |
| 4 | Unset/empty `worker_capability` and `EXECUTION_PHASE_UNSPECIFIED` are rejected | 3a.9-3a.10, 3b.1 |
| 5 | O1-O4 are asserted by test, not by docstring | 4a.6-4a.9, 4b.1, 4b.6, 4b.9 |
| 6 | No module outside the transport package imports `grpc` or any `_pb2` symbol (recursive check) | 2.10, 4b.14 |
| 7 | Regenerating from `../proto` produces byte-identical checked-in code (drift guard) | 2.6 |
| 8 | `uv run pytest` / `ruff check` / `pyright` pass; the naming audit still finds zero violations | 1.13, 2.11, 3a.16, 3b.16, 4a.11, 4b.16, 5.9 |

---

## Requirement Coverage Map

| Spec / Requirement | Task(s) |
|---|---|
| `execution-identity` — WorkloadId And AllocationId Are Proof-Carrying Identity Types (both scenarios) | 1.1-1.2 |
| `execution-identity` — SecurityContext Is Carried, Never Interpreted | 1.3 |
| `execution-identity` — ObservabilityContext Is Carried, Never Interpreted | 1.4 |
| `execution-identity` — execution_parameters Is Carried Opaque Data | 1.5 |
| `worker-wire-conversion` — Identity Wrapper Messages Convert Wire-to-Domain, Rejecting Invalid Content (all 3 scenarios) | 3a.4-3a.6 |
| `worker-wire-conversion` — Unset Required Message Fields Are Rejected | 3a.7 |
| `worker-wire-conversion` — worker_capability Is Rejected When Missing Or Empty (both scenarios) | 3a.9-3a.10 |
| `worker-wire-conversion` — Domain ExecutionPhase Never Maps To EXECUTION_PHASE_UNSPECIFIED | 3b.1 |
| `worker-wire-conversion` — Every Conversion Rejection Is Classified Permanent, Never Silent Or Panicking (both scenarios) | 3a.14-3a.15 |
| `worker-grpc-transport` — WorkerExecution Exposes Exactly Three RPCs | 2.7 (descriptor level), 4b.1 (servicer level) |
| `worker-grpc-transport` — SubmitJob Streams Events Then Exactly One Terminal Report, Always Last (both scenarios) | 4b.3-4b.5 |
| `worker-grpc-transport` — WorkloadId Is Registered Before The First Await (O1) | 4a.6, 4b.1 |
| `worker-grpc-transport` — WorkloadId Is Deregistered Before The Handler Returns (O2) | 4a.7, 4b.6 |
| `worker-grpc-transport` — Cancel And Pulse For An Unknown WorkloadId Are Classified Errors (O3, both scenarios) | 4a.8, 4b.7-4b.8 |
| `worker-grpc-transport` — SubmitJob For An Already-Registered WorkloadId Is Rejected (O4) | 4a.9, 4b.9 |
| `worker-grpc-transport` — Generated Code Is Isolated To The Transport Package | 2.10, 4b.14 |
| `worker-grpc-transport` — Regenerating From ../proto Produces Byte-Identical Checked-In Code | 2.6 |
| `worker-runtime` (delta) — Execution completes successfully | 4b.3, 4b.15 |
| `worker-runtime` (delta) — Cancellation propagates to the active execution | 4a.10, 4b.5, 4b.7 |
| `worker-runtime` (delta) — Pulse reports health without affecting execution state | 4a.5, 4b.8 |
| Design D8 (ten-field ExecutionContext, no envelope) | 1.8 |
| Design D9 (AllocationContract narrows to one field; missing/negative rejections) | 1.6, 1.11-1.12, 3a.11-3a.12, 3b.2, 5.1-5.2, 5.5 |
| Design D10 (dependencies as ordered, unkeyed tuple) | 1.7, 3a.8, 5.3 |
| Design D11 (codegen mechanics, both guards) | 2.1-2.8 |
| Design D12 (grpc.aio, loop affinity) | 4b.11 |
| Design D13 (transport package layout, zero-exception isolation guard) | 2.9-2.10, 4b.11-4b.14 |
| Design D14 (bounded queue, Report structurally last) | 4a.2-4a.3, 4b.3-4b.5 |
| Design D15 (registry owns token + transport-observable phase) | 4a.1, 4a.4-4a.5, 4b.8 |
| Design D16 (domain→wire lossiness, closed drop list) | 3b.3-3b.13, 5.4 |
| Design D17 (classified error hierarchy, fixed status mapping) | 3a.1-3a.3, 4b.2, 4b.7-4b.10, 5.6 |
| Gotcha — line-anchored import rewrite | 2.3-2.4 |
| Gotcha — single descriptor registration | 2.8 |
| Gotcha — protoc emits no `__init__.py` | 2.4 |
| Gotcha — grpcio cp314 wheel risk | 2.1 |
| Gotcha — naming audit does not cover `transport/` | 4b.16 |

---

## Risks

| Risk | Note |
|---|---|
| S3's line count still drifts past 400 even after the S3a/S3b split | Each of S3a/S3b is independently estimated at ~175 lines — well under budget — but if `sdd-apply` finds either drifting, the next natural cut inside S3a is identity-wrapper conversions (3a.4-3a.7) vs. `ExecutionContext` composition (3a.8-3a.13); inside S3b it is the event-arm conversions (3b.7-3b.12, 3b.14) vs. report/pulse conversions (3b.1-3b.6, 3b.9, 3b.15). |
| S5 is authoring, not confirmation, unlike the tibios-core `worker-inbound-port` precedent | Confirmed by reading the current spec files at task-planning time (Sequencing Notes) — three of the four named deltas are genuinely missing text, not already-written-and-just-needing-confirmation. This is more work than the precedent's S5b, budgeted at design.md's original ~150-line estimate for S5, which already assumed authoring. |
| `grpcio` cp314 wheel availability is unverified as of task-planning time | 2.1 is explicitly the fail-fast checkpoint; if no wheel exists, the pin choice becomes an `sdd-apply`-time decision, not a blocking one, per the Gotcha's own stated fallback. |
| Task 4a.3's backpressure test needs a fixture that can genuinely fill an `asyncio.Queue(maxsize=8)` without a real Provider | Same class of fixture-design problem tibios-core flagged for its own O1 test (`worker-inbound-port/tasks.md` task 4.13) — a small hand-rolled slow consumer or a queue pre-filled to capacity before asserting `emit` awaits rather than raises. Flagged here as the highest-friction task in S4a; the exact fixture shape is an `sdd-apply` implementation choice. |
| Task 3a.11's rejection variant name (`MissingFieldError` vs. a dedicated `MissingAllocationContractError`) is left open | Either satisfies D9's requirement; `sdd-apply` should pick the simpler one (reusing `MissingFieldError`) and record the choice, consistent with how 5a.3 in the tibios-core precedent left its own routing-shape choice open. |
