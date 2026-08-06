# Archive Report: Worker Wire Contract (`.proto`)

**Date**: 2026-08-06
**Change**: proto-worker-contract
**Artifact Store**: hybrid (openspec + engram)
**Status**: ARCHIVED

---

## Executive Summary

The `proto-worker-contract` change has been successfully completed, verified (PASS with 0 CRITICAL / 0 WARNING), and archived. This change delivered the language-neutral proto3 wire projection of the Worker Contract (`18-worker-model.md`), consisting of two carefully organized `.proto` files — `identity.proto` (5 Runtime Primitive identity wrappers) and `worker.proto` (the complete Worker domain surface with 3 RPCs, 13 message types, and 1 enum) — plus one new capability spec establishing the binding between architecture and wire format. No Rust, no Python, no Cargo changes. The spec is normative; the proto files pass lint, compile cleanly, and carry comprehensive citations to their defining architecture documents. All 39/40 tasks completed (1 blocked per policy: Rust codegen verification deferred to follow-up). Two follow-up changes identified and ready to start.

---

## What Was Delivered

### Artifacts (All Complete)

| Artifact | Count | Status |
|----------|-------|--------|
| Proposal | 1 | CLOSED |
| Design | 1 | CLOSED (4 decisions, 9 invariants settled) |
| Tasks | 1 | 39/40 complete (1 blocked by policy: Rust codegen verification) |
| Verification Report | 1 | PASS (0 CRITICAL, 0 WARNING, 3 non-blocking SUGGESTION) |
| Capability Spec (New) | 1 | MERGED to openspec/specs/worker-wire-contract/spec.md |

### Proto Files Delivered

**`/Users/fernandogutierrezparamio/desarrollo/TibiOS/proto/tibios/primitives/v1/identity.proto`**
- 5 message definitions: `ObjectId`, `ObjectVersion`, `ContentHash`, `WorkloadId`, `AllocationId`
- Service-free by design (future projections can depend without inheriting RPC surface)
- No intra-repo imports; versioned package `tibios.primitives.v1`
- Every message has architecture citation: `02-project-structure.md:116` for all four existing primitives; added `AllocationId` as distinct primitive per `15-allocation-model.md:41`

**`/Users/fernandogutierrezparamio/desarrollo/TibiOS/proto/tibios/worker/v1/worker.proto`**
- 13 message types + 1 enum + 1 service = **complete Worker Contract projection**
  - Messages: `ResolvedModelRef`, `AllocationContract`, `SecurityContext`, `ObservabilityContext`, `ExecutionContext`, `ExecutionEvent` (wrapper), `OutputChunk`, `Progress`, `Warning`, `CheckpointCreated`, `MetricsSnapshot`, `EndOfStream`, `ExecutionReport`, `ExecutionPulse`, `ExecutionResponse`, `CancelRequest`, `PulseRequest`, `CancelAck`
  - Enum: `ExecutionPhase` with 7 values (including `EXECUTION_PHASE_CANCELLED` for mid-cancellation reports)
  - Service: `WorkerExecution` with exactly 3 RPCs: `SubmitJob` (unary → server stream), `Cancel`, `Pulse`
- One intra-repo import: `tibios/primitives/v1/identity.proto` (design D2's single edge)
- Google well-known types: `google/protobuf/duration.proto` for `AllocationContract.max_execution_duration` and `ExecutionReport.duration`
- Every element carries architecture citation to `18-worker-model.md` (and cross-cites to design decisions D1/D4 where applicable)

### Scope Completed

**Design Questions (Settled)**:
- D1: Trust/Session does NOT govern the Worker channel; `SecurityContext` is execution-scoped authorization, never peer trust
- D2: Two-file split by ownership (`identity.proto` + `worker.proto`), not by concern; exactly one import edge
- D3: Generated codegen lives in private `adapters/` module inside `runtime-worker`; no new crate added to manifest
- D4: `ExecutionResponse` oneof confirmed with refinements: exactly 2 arms (event | report), report is last and unique, `Cancel` returns named `CancelAck`

**File Organization**:
- `../TibiOS/proto/` — sibling to both `tibios-core/` and `tibios-ray/`, owned by neither
- Versioned packages (`v1`) from day one, enabling contract evolution via new packages

**Completeness Metrics**:
- 2 `.proto` files, ~350 lines of code + citations
- 1 capability spec at `openspec/specs/worker-wire-contract/spec.md` (new, not delta)
- Normative mapping table: 18 Python types ↔ proto messages/arms, with explicit ray-side follow-ups for proto-only additions
- All 8 spec Requirements verified; all 9 design Invariants confirmed

---

## Verification Result

**Verdict**: PASS

- **Completeness**: 39/40 tasks complete (1 blocked per "never build" policy: Rust `prost`/`tonic` codegen verification requires `cargo install`, deferred to `worker-grpc-adapter` follow-up)
- **Quality Gates**:
  - `protoc` compilation: PASSED (exit 0, both files parse and resolve imports cleanly)
  - Python codegen: PASSED (scratch venv, absolute imports confirmed)
  - Citation verification: PASSED (all 18 messages + 1 enum + 1 service carry architecture citations)
  - Invariant checks: PASSED (all 9 design invariants verified against current `.proto` content)
- **Critical Issues**: 0
- **Warnings**: 0
- **Suggestions**: 3 (non-blocking; table footnotes and naming conventions, no wire correctness impact)

Key verifications:
- RPC interface exactly 3 methods; `WorkloadId` sole correlation key on `Cancel`/`Pulse`
- `ExecutionEvent` exactly 6 arms; `ExecutionResponse` exactly 2 arms (event|report)
- `ExecutionContext` carries full doc-mandated set: Workload, Allocation, AllocationContract, resolved dependencies, Security/Observability Contexts, Execution Parameters
- No Session/Node/Trust/Membership/Lease/Credential fields anywhere (D1 enforced via grep)
- No retry/attempt/recovery encoding anywhere
- `AllocationId` is distinct from `ObjectId` (fixed in post-verify batch)
- Every message cites its defining architecture section (final pass confirms all misses closed)

---

## Specification Baseline (openspec/specs/)

The new capability spec is already in place at the main specs location — no delta-merge required (this spec was created fresh during `sdd-spec`, not as a delta within the change folder).

| Spec | Location | Status |
|------|----------|--------|
| Worker Wire Contract | `openspec/specs/worker-wire-contract/spec.md` | NEW (complete, normative) |

The spec defines the 8 binding requirements and the normative mapping table, establishing the source of truth for both codegens.

---

## Design Decisions and Rationale

All four open design questions from the proposal have been answered and settled:

### D1 — Trust/Session does NOT govern the core↔ray channel
- `SecurityContext` in `ExecutionContext` is execution-scoped authorization, not peer trust
- Channel credentials live in transport metadata/TLS, never in the `.proto`
- `ObservabilityContext` is message-normative; `traceparent` header is derived, never authoritative
- Consequence: a Worker never needs (and must never read) Runtime peer identity, membership, or trust status

### D2 — Two-file split by ownership
- `identity.proto`: 5 Runtime Primitives (owned by `runtime-primitives` domain)
- `worker.proto`: Worker domain language + service (owned by `runtime-worker` domain)
- Exactly one intra-repo import edge; future projections can depend on primitives without depending on Worker
- Versioned packages (`v1`) from day one

### D3 — Rust codegen lives in private `adapters/` module
- Generated `prost`/`tonic` code stays in `runtime-worker/src/adapters/`, not public-facing
- No new crate added; workspace stays at exactly 16 members
- Spec amendment required (Requirement: "Generated Transport Code Stays Private")
- Guard updates required (per-crate external allowlist, public-surface assertion)
- Follow-up change `worker-grpc-adapter` will implement this with a hand-written `TryFrom` conversion layer

### D4 — `ExecutionResponse` oneof confirmed
- Exactly 2 arms (event | report); report is always last on the stream
- `Cancel` returns named `CancelAck` ("accepted", never "terminated")
- Cancelled executions still produce a terminal Report on the same stream
- Ordering is total, no sequence number needed

---

## Follow-Up Changes Identified

### 1. **`worker-grpc-adapter`** (follow-up, Rust codegen wiring)

Spec deltas required in `openspec/specs/runtime-worker/spec.md`:
- Requirement "Stub Crate, No Public Traits" → "Generated Transport Code Stays Private"
- Explicit external allowlist: `{tonic, prost}` (dependencies) + `{tonic-build}` (build-dep)

Guard updates required in `runtime/tests/architecture_guard.rs`:
- New per-crate external allowlist test (tonic/prost/tonic-build on `runtime-worker` only)
- New public-surface assertion (no transport types in public API)

Unresolved input for this follow-up:
- How `../TibiOS/proto/` becomes available to `build.rs` reproducibly (submodule vs. vendored + hash check vs. `buf` remote module)

Non-obvious consequence:
- Proto-generated `tibios.primitives.v1.ObjectId` is not `runtime_primitives::ObjectId`; hand-written `TryFrom` conversion layer mandatory (enforces proto3 optionality, ULID parsing, unset-oneof rejection)

### 2. **`tibios-ray` follow-up** (close ExecutionContext gaps)

Design D1 identified Ray-side gaps recorded as normative additions in the mapping table:
- `WorkloadId` — proto-only, Ray-side implementation needed
- `AllocationId` — proto-only distinct primitive, Ray-side implementation needed
- `SecurityContext` — proto-only, Ray-side implementation needed
- `ObservabilityContext` — `ExecutionReport.trace_id` exists on Ray side, but `ExecutionContext`-carried observability fields don't; need Ray-side follow-up
- `ExecutionPhase.CANCELLED` — proto-only enum value; Ray-side implementation needed
- `CancelAck` — proto-only ack message; Ray-side implementation needed

Every addition is explicitly recorded in the mapping table, not silent.

---

## Proto Compliance & Quality

| Check | Result |
|-------|--------|
| `protoc` compilation | PASS (exit 0) |
| Python codegen | PASS (scratch venv, absolute imports verified) |
| Rust `prost`/`tonic` codegen | BLOCKED (no plugins installed; deferred to `worker-grpc-adapter`) |
| Citation completeness | PASS (all 20 message/enum/service blocks have architecture citations) |
| Forbidden keyword grep (Session/Node/RuntimeId/membership/lease/credential) | PASS (0 matches) |
| Retry/attempt/recovery grep | PASS (0 matches) |
| RPC count | PASS (exactly 3) |
| ExecutionEvent oneof arms | PASS (exactly 6) |
| ExecutionResponse oneof arms | PASS (exactly 2) |
| Import edges | PASS (exactly 1 intra-repo edge) |
| Package versioning | PASS (both packages are `v1`) |

---

## Architecture Compliance

All 4 design decisions are grounded in the frozen architecture (`18-worker-model.md:v1.0`):

- **D1** is rooted in `22-networking.md` (Workers not Runtime peers) and `25-ai-runtime.md` (two implementations, same contract)
- **D2** follows `02-project-structure.md:325` (data contracts belong to producing domain) and `.351` (never split one owner's language by technology)
- **D3** is grounded in `02-project-structure.md:437-446` (crates represent domains, not implementation details) and `.359` (avoid utility/helper crates)
- **D4** is defended by `18-worker-model.md:108/118/122` (execution state, completion ownership, recovery strategy)

The Transport-Agnosticism Test (Governing Principle) — *would `local-infer` still need it?* — is the tiebreaker for every field.

---

## Archive Locations

| Artifact Type | Location |
|---------------|----------|
| **OpenSpec** (file-based) | `openspec/changes/archive/2026-08-06-proto-worker-contract/` |
| Proposal | `proposal.md` |
| Design | `design.md` |
| Tasks | `tasks.md` |
| Verify Report | `verify-report.md` |
| Archive Report | `archive-report.md` (this document) |
| **Proto Source** (sibling repo) | `/Users/fernandogutierrezparamio/desarrollo/TibiOS/proto/` |
| `identity.proto` | `tibios/primitives/v1/identity.proto` |
| `worker.proto` | `tibios/worker/v1/worker.proto` |
| **Spec Baseline** (merged) | `openspec/specs/worker-wire-contract/spec.md` |
| **Engram** (persistent memory) | `sdd/proto-worker-contract/archive-report` |
| Traceability | Cross-references to proposal, design, tasks, verify-report observation IDs |

---

## SDD Cycle Status

**proto-worker-contract**: COMPLETE

- Phase 1 (Propose): ✓ Completed (intent, scope, approach, open questions)
- Phase 2 (Design): ✓ Completed (4 decisions, 9 invariants, governing principle)
- Phase 3 (Spec): ✓ Completed (8 requirements, normative mapping table)
- Phase 4 (Tasks): ✓ Completed (39/40 tasks planned; 1 blocked by policy, not defect)
- Phase 5 (Apply): ✓ Completed (2 `.proto` files written, spec finalized, citations verified)
- Phase 6 (Verify): ✓ Completed (PASS: 0 CRITICAL, 0 WARNING, 3 non-blocking SUGGESTION)
- Phase 7 (Archive): ✓ Completed (change archived, spec merged to baseline)

**Next Steps for the project**:
1. Start `worker-grpc-adapter` to wire Rust codegen (implement D3)
2. Start `tibios-ray` follow-up to close ExecutionContext gaps (implement Ray-side additions)
3. Both can proceed in parallel; neither blocks the other

No further work is required on this change. The proto files are stable, the spec is normative, and the contract is frozen.

---

## Traceability

Engram observation IDs (for cross-session recovery):
- Proposal: `sdd/proto-worker-contract/proposal`
- Design: `sdd/proto-worker-contract/design`
- Spec: `sdd/proto-worker-contract/spec`
- Tasks: `sdd/proto-worker-contract/tasks`
- Verify Report: `sdd/proto-worker-contract/verify-report`
- Archive Report: `sdd/proto-worker-contract/archive-report` (this document)

This archive report was generated by `sdd-archive` phase executor on 2026-08-06.

---

## Files for Git

The following files were moved from the active change directory to the archive:

```
git mv openspec/changes/proto-worker-contract/ openspec/changes/archive/2026-08-06-proto-worker-contract/
```

No files were deleted. The proto files at `/Users/fernandogutierrezparamio/desarrollo/TibiOS/proto/` remain in place (they are not under `tibios-core/`, so they were already handled by `sdd-apply`). The spec at `openspec/specs/worker-wire-contract/spec.md` remains in place as the baseline (it was not a delta, so no merge was needed).

All commits related to proto files and the spec should be present already from prior phases. This archive phase adds only the archive folder and archive-report.md.
