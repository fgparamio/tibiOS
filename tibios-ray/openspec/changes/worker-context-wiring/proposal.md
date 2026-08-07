# Proposal: Worker Context Wiring (the gRPC boundary tibios-ray never grew)

## Intent

`src/tibios_ray/server.py` is a docstring. tibios-ray has a Capability Registry, seven Providers, a `WorkerRuntime` that drives the full lifecycle, and a real llama.cpp backend — and **no way for tibios-core to reach any of it**. `grpcio` is not even a dependency.

The wire contract is frozen and complete: `../proto/tibios/worker/v1/worker.proto` defines `WorkerExecution` (3 RPCs, permanently) and an 8-field `ExecutionContext`. tibios-core finished its side (`worker-inbound-port`, `worker-contract-capability-field`, both archived 2026-08-06). The domain `ExecutionContext` (`execution/context.py:63`) carries **5 fields, 3 of them wire-visible**; `WorkloadId` and `AllocationId` do not exist anywhere in this repo. This change closes that gap. It is 100% tibios-ray-side consumption work — **no cross-repo coordination is in scope**.

## Scope

### In Scope

- `execution/ids.py`: `WorkloadId`, `AllocationId` — frozen slotted dataclasses per D3 (proof-carrying identity, never `NewType`).
- `execution/context.py`: `SecurityContext(tenant_id, principal_id, grant_scope)` and `ObservabilityContext(trace_id, span_id)` — **carried, never interpreted** (tibios-core D10: a Worker that rejects work on identity grounds has made an authorization decision, forbidden by `18-worker-model.md:136`). Plus `execution_parameters: Mapping[str, str]`.
- `ExecutionContext` extended to carry all wire-visible fields (shape is Q1).
- `ExecutionPhase.CANCELLED` — the domain enum has 5 states, the wire has 6; `EXECUTION_PHASE_UNSPECIFIED` is a rejection, never a default.
- Python codegen from `../proto` into one isolated package, a regeneration script, and a **drift-guard test**; `grpcio`/`grpcio-tools` added to `pyproject.toml` (Q2).
- `WorkerExecutionServicer` (`server.py`): `SubmitJob` / `Cancel` / `Pulse`, plus a gRPC-backed `ExecutionChannel` adapter and a per-`WorkloadId` in-flight registry so `Cancel`/`Pulse` correlate.
- Wire→domain conversion with **reject-don't-guess** semantics mirroring `../tibios-core/openspec/specs/worker-wire-adapter/spec.md`: invalid ULID, unparseable `ObjectVersion`, unset required message, unset/empty `worker_capability`, unset `oneof` — all rejected, never defaulted, never panicking.

### Out of Scope

- **Capability dispatch/routing behind `SubmitJob`.** `CapabilityRegistry` + `WorkerRuntime` already own it and are already specified. This change is the transport/domain boundary only: what happens *after* a request is accepted is unchanged.
- **Any edit to `../proto/`** — frozen, cross-repo-owned. Where this codebase and the `.proto` disagree, the `.proto` wins.
- Ray actor/cluster deployment topology, serving concurrency, process supervision.
- TLS, peer auth, mTLS (`22-networking.md`) — a Worker is not a Runtime peer (tibios-core D1).
- Retyping `SecurityContext` into parsed identities — deferred as one unit until a security domain exists.

## Capabilities

### New Capabilities

- `execution-identity`: `WorkloadId`/`AllocationId` value types and the carried-never-interpreted rule for `SecurityContext`/`ObservabilityContext`/`execution_parameters`.
- `worker-wire-conversion`: the fallible wire↔domain boundary and its complete rejection surface.
- `worker-grpc-transport`: the three RPCs, SubmitJob stream ordering (events, then exactly one terminal Report, **always last**), the `WorkloadId` correlation obligations, and generated-code isolation.

### Modified Capabilities

- `worker-runtime`: its cancellation scenario says *"a cancellation signal (Pulse) is received"* (`specs/worker-runtime/spec.md:22`). **That is wrong against the frozen wire**: `Pulse` is a Runtime-pulled health check; `Cancel` is the cancellation RPC returning `CancelAck` — *accepted*, never *terminated* (`worker.proto:227-234`). Must be restated, plus the Report's position as the last message on the stream.

## Approach

Mirror tibios-core's containment discipline, in Python. Generated code and every `grpc`/`_pb2` import live in **one** package; a recursive import guard — the same `rglob` pattern as `tests/unit/backends/test_no_engine_imports.py` — proves no domain module ever imports transport. Conversion is a pure function over generated messages returning domain values or raising a classified, `Permanent` conversion error; it is unit-testable with zero sockets. The servicer wires `WorkerRuntime` to that boundary and owns the in-flight registry.

Correlation obligations are inherited verbatim from tibios-core's `worker-inbound-port` D11 (the wire hands tibios-ray nothing but a `WorkloadId`, so there is no other possible mechanism):

| # | Obligation |
|---|---|
| O1 | Register the `WorkloadId` **before the first `await`** in `SubmitJob`, so an immediately-following `Cancel` is never lost |
| O2 | Deregister before the handler returns — on success, failure, and cancellation alike |
| O3 | `Cancel`/`Pulse` for an unknown `WorkloadId` is a classified error, never a silent success |
| O4 | `SubmitJob` for an already-registered `WorkloadId` is rejected without starting a second execution |

Strict TDD throughout — every rejection scenario is a failing test first.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `src/tibios_ray/execution/ids.py` | Modified | `WorkloadId`, `AllocationId` |
| `src/tibios_ray/execution/context.py` | Modified | `SecurityContext`, `ObservabilityContext`, `execution_parameters`, extended `ExecutionContext` |
| `src/tibios_ray/execution/report.py` | Modified | `ExecutionPhase.CANCELLED` |
| `src/tibios_ray/transport/**` (new pkg) | New | generated stubs, conversion, channel adapter, in-flight registry |
| `src/tibios_ray/server.py` | New content | `WorkerExecutionServicer` — replaces the docstring stub |
| `src/tibios_ray/worker.py` | Modified | composition root finally composes |
| `src/tibios_ray/testing/context.py` | Modified | `FakeExecutionContext` gains the new fields |
| `pyproject.toml` | Modified | `grpcio`, `grpcio-tools`, codegen script |
| `tests/unit/transport/**` | New | conversion rejections, stream ordering, O1–O4, import guard, proto drift |
| `src/tibios_ray/{runtime,capabilities,selection,backends}/**` | Untouched | dispatch is out of scope |

## Open Design Questions

Five for `sdd-design`. **Q3 is blocking.** Continue decision numbering at **D8** (`ray-worker-runtime` ended at D7).

1. **Does `ExecutionContext` grow to 8+ fields, or split into an envelope?** Precedent leans *grow*: tibios-core kept `workload_id`/`allocation_id` inside its own `ExecutionContext` (`worker-inbound-port/design.md`, testability sequence). `channel`/`cancellation` stay domain-only — the wire has no field for either **by design** (`worker.proto:81-83`).
2. **Codegen: checked-in vs. build-time.** `uv_build` exposes no build-hook API, so build-time generation means changing build backend or a pre-build script. Checked-in is deterministic and needs no toolchain at install — but adds thousands of generated lines and can drift from `../proto`. Leaning: checked-in + regeneration script + drift-guard test, **isolated in its own PR slice** so generated bulk never consumes the 400-line review budget. Also settle generated-import rewriting (`grpc_tools.protoc` emits package-absolute imports) and `--pyi_out` for pyright.
3. **`AllocationContract` asymmetry — BLOCKING.** The wire carries **one** field (`max_execution_duration`); the domain type has **six** (`context.py:49`). The other five cannot be reconstructed, and reject-don't-guess forbids inventing them. Either the boundary defaults them deliberately and documents it, or the domain type narrows. Note tibios-core shipped this knowingly ("partial AllocationContract data contract").
4. **What keys the `dependencies` map?** Domain is `Mapping[str, ResolvedModelRef]`; the wire is `repeated ResolvedModelRef` with **no key**.
5. **Domain→wire lossiness.** `ExecutionReport.resource_usage/metrics/logs`, `Warning.code`, `EndOfStream.reason`, `ExecutionPulse.detail` have no wire home; wire `ExecutionReport.summary` has no domain home. Decide what is dropped, what is folded into `summary`, and what is asserted by test — silently is not an option.

Also to settle: `grpc.aio` vs sync `grpc` (`WorkerRuntime.execute` is `async`, which points hard at `aio`).

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Generated bulk swamps review | High | Isolate codegen in its own PR slice; drift-guard test instead of eyeballing |
| `grpcio` wheels on Python 3.14 | Med | Pin ranges not exact versions; verify in apply; codegen slice fails fast |
| Conversion silently defaults instead of rejecting | Med | Every rejection case from `worker-wire-adapter/spec.md` becomes a scenario; test-first |
| Report not last on the stream (proto3 cannot enforce it) | Med | An explicit ordering test is the only guard — `worker.proto:196-203` says so |
| Cancel races SubmitJob registration | Med | O1: register before the first suspension point; test issues `Cancel` immediately |
| Registry leaks in a long-lived process | Med | O2 + a test asserting `Pulse` reports unknown after completion |
| Transport leaks into domain modules | Low | Recursive import guard (`test_no_engine_imports.py` precedent) |
| `testing/` is naming-audited | Low | `_AUDITED_PACKAGES` includes `testing` — no test double may contain "Worker" in an identifier; `execution/` and a new `transport/` are not audited |

## Rollback Plan

Additive except `pyproject.toml`, `server.py`/`worker.py` docstrings, and `ExecutionContext`'s field set. Nothing under `runtime/`, `capabilities/`, `selection/`, `backends/`, or `engines/` changes behavior — Providers still resolve and execute exactly as today. `git revert` of the slice commits restores the current tree; the only non-mechanical revert is `ExecutionContext`'s widened constructor, contained to `execution/` and `testing/`.

## Delivery

Estimated **~1200 hand-written lines** plus generated code — far over the 400-line budget, so **chained PRs are mandatory**. Natural slices: (1) identity + context value types; (2) codegen + isolation guard + drift guard; (3) wire→domain conversion and its rejection suite; (4) servicer, channel adapter, in-flight registry; (5) spec deltas. `sdd-tasks` owns the final split and must emit the Review Workload Forecast.

## Dependencies

- `../proto/tibios/{worker,primitives}/v1/*.proto` — frozen, complete. **Satisfied.**
- tibios-core `worker-inbound-port` + `worker-contract-capability-field` — archived. **Satisfied.**
- `openspec/config.yaml`'s `testing:` block is **stale** (claims no test runner; pytest/ruff/pyright have existed since `python-foundation`). Strict TDD is active for this change regardless; the config should be corrected out-of-band.

## Success Criteria

- [ ] A real gRPC `SubmitJob` call produces Execution Events and exactly one terminal `ExecutionReport`, **last on the stream**
- [ ] `Cancel` returns `CancelAck` for an in-flight execution and reaches the Provider's `CancellationToken`; `Pulse` reports phase and health
- [ ] Every rejection scenario in `worker-wire-adapter/spec.md` has a passing tibios-ray counterpart — no path panics, no path defaults
- [ ] Unset/empty `worker_capability` and `EXECUTION_PHASE_UNSPECIFIED` are rejected
- [ ] O1–O4 are asserted by test, not by docstring
- [ ] No module outside the transport package imports `grpc` or any `_pb2` symbol (recursive check)
- [ ] Regenerating from `../proto` produces byte-identical checked-in code (drift guard)
- [ ] `uv run pytest` / `ruff check` / `pyright` pass; the naming audit still finds zero violations
