# Proposal: Worker Wire Contract (`.proto`)

## Intent

`18-worker-model.md` defines the Worker Contract in prose; `tibios-ray` has already materialized it as Python types (`execution/*.py`). Nothing binds them. Until a `.proto` exists, `tibios-ray`'s `worker.py`/`server.py` stay docstring-only and every core↔ray change is a copy-paste negotiation between two repos.

This change produces the **language-neutral projection** of the Worker Contract — a projection pattern, never a canonical crate (`27-sdk.md`), the same shape `18-worker-model.md` already uses for one contract with many implementations.

## Scope

### In Scope
- `../TibiOS/proto/` — proto3 definitions, sibling to `tibios-core/` and `tibios-ray/` (owned by neither, consumed by both).
- Service: `SubmitJob(ExecutionContext) → stream ExecutionResponse`, `Cancel(WorkloadId)`, `Pulse(WorkloadId) → ExecutionPulse`.
- Messages: identity wrappers (`ObjectId`, `ObjectVersion`, `ContentHash`, `WorkloadId`), `ResolvedModelRef`, `AllocationContract`, `ExecutionContext`, `ExecutionEvent` (6-arm oneof), `ExecutionReport`, `ExecutionPulse`, `ExecutionPhase`.
- A normative mapping table: every `tibios_ray.execution` type ↔ its proto message, proving losslessness in both directions.

### Out of Scope
- Rust codegen wiring (`build.rs`, `prost`/`tonic`, crate placement) — follow-up change.
- Ray-side generated client and `worker.py`/`server.py` wiring — `tibios-ray`'s follow-up.
- Runtime API transport (`26-runtime-api.md`); Object Store metadata queries.

## Capabilities

### New Capabilities
- `worker-wire-contract`: the proto3 projection of `18-worker-model.md` — service, messages, enums, and the bidirectional type-mapping guarantee.

### Modified Capabilities
- None. No Rust source, `Cargo.toml`, or existing spec changes in this change.

## Approach

`18-worker-model.md` is authoritative; the `.proto` mirrors it, and the Python types are validated against it — not the reverse. Two consequences must be resolved in `sdd-design`:

1. **Execution Context is incomplete on the Ray side.** The doc lists Workload, Allocation, Security Context, Observability Context, and Execution Parameters; `context.py` has none of them. The `.proto` carries the doc's set.
2. **Channel and cancellation do not serialize.** They are process-local (`tokio::mpsc`, `CancellationToken`). On the wire the Channel *is* the response stream and cancellation *is* the `Cancel` RPC — they are absent from `ExecutionContext`.

Recommended envelope: `ExecutionResponse { oneof { ExecutionEvent event; ExecutionReport report; } }`. This gives the Report a transport (it has none otherwise) without adding a 7th arm to `ExecutionEvent`, preserving exhaustive `match` on both sides.

Settled inputs (do not reopen): unary request / server-streaming response; `Cancel` and `Pulse` as separate RPCs; `WorkloadId` alone as correlation key — retries reuse it (`10-distributed-systems.md:49`, `20-admission-control.md:34`) and Workers never know recovery strategy (`18-worker-model.md:122`).

## Open Design Questions (for `sdd-design`, non-blocking)

| # | Question | Note |
|---|---|---|
| 1 | Does Trust/Session (`22-networking.md`) apply to this channel? | Networking governs Runtime↔Runtime peers; a Worker process is not a peer. But `18-worker-model.md` mandates a Security Context in the Execution Context. Neither assumption may be made silently. |
| 2 | File organization: one `worker.proto` vs. split (`identity`/`context`/`events`/`report`)? | Affects import graph for both codegens. |
| 3 | Rust codegen home: internal `adapters/` module in `runtime-worker`, or a new crate? | A new crate breaks `workspace-manifest`'s "exactly 16 members" and needs `architecture_guard.rs` updates. Deferred, but decide the target before the follow-up. |
| 4 | Does `ExecutionReport` ride the response stream (recommended) or a fourth RPC? | Blocks nothing here; blocks the server implementation. |

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `../TibiOS/proto/` | New | proto3 contract, owned by the monorepo root |
| `tibios-core/openspec/specs/worker-wire-contract/` | New | capability spec |
| `docs/architecture/18-worker-model.md` | Unchanged | authoritative source, referenced only |
| `tibios-ray/src/tibios_ray/execution/` | Unchanged | validated against, reconciled in its own repo |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Contract drifts from `18-worker-model.md` (frozen `architecture-v1.0`) | Med | Every message cites its doc section; spec requires the citation |
| `tibios-ray` types diverge from the `.proto` after landing | High | Mapping table is normative; gaps (Security/Observability Context) recorded as ray-side follow-ups, not silently dropped |
| proto3 field-presence semantics lose Python `X \| None` optionality | Med | Explicit `optional` on every nullable field; covered by spec scenarios |
| Cross-repo coordination still manual (two parallel sessions) | Med | This `.proto` is precisely what ends it |

## Rollback Plan

Purely additive: new `.proto` files and one new spec. No Rust, no Cargo, no Python touched, nothing generated or committed downstream. `git revert` of this change's commits restores the current state exactly. No consumer exists yet, so there is no migration to unwind.

## Dependencies

- `docs/architecture/` at tag `architecture-v1.0` (read-only).
- `tibios-ray`'s `ray-worker-runtime` Phase 1 types (read-only reference; already landed).
- Tooling: `protoc` or `buf` for lint/compile verification.

## Success Criteria

- [ ] `.proto` compiles cleanly and passes lint for both `prost`/`tonic` and Python codegen
- [ ] Every `tibios_ray.execution` public type has exactly one proto counterpart, and vice versa, in the mapping table
- [ ] `ExecutionEvent` has exactly the 6 documented arms — no Pulse arm, no Report arm
- [ ] Exactly three RPCs; `WorkloadId` is the sole correlation field on `Cancel` and `Pulse`
- [ ] No message encodes retry, attempt number, or recovery strategy
- [ ] Every message carries a comment citing its `18-worker-model.md` section
- [ ] All four open design questions are answered in `design.md` before any codegen lands
