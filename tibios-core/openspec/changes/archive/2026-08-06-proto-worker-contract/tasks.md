# Tasks: Worker Wire Contract (`.proto`)

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~300-380 (identity.proto ~55-70; worker.proto ~250-310, incl. per-message doc-citation comments); plus a ~10-20 line documentation-only diff to `openspec/specs/worker-wire-contract/spec.md` removing its "Provisional" framing now that design is settled |
| Files touched | 2 new `.proto` files (`../TibiOS/proto/tibios/primitives/v1/identity.proto`, `../TibiOS/proto/tibios/worker/v1/worker.proto`); 1 existing spec doc edited (mapping table + notes section); 0 Rust files; 0 Python files; 0 `Cargo.toml`/manifest changes |
| 400-line budget risk | Low — pure addition of two `.proto` files with no downstream code, matching the proposal's Rollback Plan ("no Rust, no Cargo, no Python touched") |
| Chained PRs recommended | No |
| Decision needed before apply | No |
| Delivery strategy | ask-on-risk (cached) — not triggered; single PR is sufficient |

## Sequencing Notes

- Phase 1 must complete before any file authoring (directories must exist).
- Phase 2 (`identity.proto`) must be internally consistent before Phase 3 begins — `worker.proto` imports it (D2's one import edge).
- Within Phase 3: leaf/context messages (3.2-3.5) and the event-arm/envelope/RPC-request messages (3.7, 3.9, 3.10, 3.12) have no field dependency on each other and can be authored in parallel; `ExecutionContext` (3.6) depends on 3.2-3.5 existing as field types; `ExecutionResponse` (3.11) depends on 3.8 and 3.9; the service (3.13) depends on all preceding messages in the file.
- Phase 4 (invariant checks) runs only after Phase 3 is complete, but 4.1-4.9 are independent read-only checks over the same finished files and can run in parallel with each other.
- Phase 5 (lint/compile) requires Phase 3-4 complete; 5.1-5.3 are independent tool invocations against the same finalized files and can run in parallel; 5.4 (cleanup) is sequential-last.
- Phase 6 (mapping table finalization) can proceed in parallel with Phase 5 — it does not depend on lint/codegen success — but must complete before the change is considered done.

## Phase 1: Proto Root & Directory Setup

- [x] 1.1 Create the `../TibiOS/proto/` directory tree: `tibios/primitives/v1/` and `tibios/worker/v1/`, sibling to `tibios-core/` and `tibios-ray/`, owned by neither. (proposal Scope; design D2 exact layout)
- [x] 1.2 Document the verification tooling invocation (protoc/buf commands used in Phase 5) as a short comment block or scratch note — do NOT add a `buf.yaml`; a module/workspace file is explicitly deferred to the `worker-grpc-adapter` follow-up. (design D2 Alternatives Considered)

> **Tooling note (no `buf.yaml` added — deferred to `worker-grpc-adapter`):**
> - `protoc` found at `/opt/homebrew/bin/protoc` (`libprotoc 34.1`); `buf` not installed — `protoc` used for all Phase 5 checks.
> - Compile/lint: `protoc -I ../TibiOS/proto --include_imports -o /dev/null tibios/primitives/v1/identity.proto tibios/worker/v1/worker.proto`
> - Python codegen (scratch venv, discarded after use): `python -m grpc_tools.protoc -I ../TibiOS/proto --python_out=<scratch> --grpc_python_out=<scratch> tibios/primitives/v1/identity.proto tibios/worker/v1/worker.proto`
> - Rust `prost`/`tonic` scratch codegen (task 5.2): **not run** — no `protoc-gen-prost`/`protoc-gen-tonic` plugin is installed, and installing one requires `cargo install`, which compiles Rust and falls outside this proto-only change's verification scope. Recorded as a blocker for a human/CI decision, not silently skipped.

## Phase 2: `identity.proto` — Runtime Primitives Projection

- [x] 2.1 Write file header: `syntax = "proto3";`, `package tibios.primitives.v1;`. No service declaration. (design D2 Decision)
- [x] 2.2 Author `ObjectId` message with a leading citation comment.
- [x] 2.3 Author `ObjectVersion` message with a leading citation comment.
- [x] 2.4 Author `ContentHash` message with a leading citation comment.
- [x] 2.5 Author `WorkloadId` message with a leading citation comment noting it is the sole correlation key for `Cancel`/`Pulse`. (spec: "WorkloadId Is the Sole Correlation Key")
- [x] 2.6 Author `AllocationId` message with a leading citation comment citing `02-project-structure.md:116` (Runtime Primitives) and `15-allocation-model.md:41` (Allocation owns its own `AllocationId`, never `ObjectId`, because it carries mutable Runtime State and cannot be content-addressed). **Added in the post-verify fix batch**: `sdd-verify` found `ExecutionContext.allocation_id` reused `ObjectId`, conflating two primitives the architecture treats as distinct (spec.md "AllocationId Is a Distinct Primitive, Never ObjectId"); this task and 3.6's retype close that gap. Not part of the original design D2 4-message list — design.md D2 still reads "Nothing else" for `identity.proto` and was not amended in this batch (out of scope for this fix; `identity.proto` now has 5 messages, one more than D2 names).
- [x] 2.7 Self-review: confirm exactly these 5 messages exist (`ObjectId`, `ObjectVersion`, `ContentHash`, `WorkloadId`, `AllocationId`), no service, no import of `worker.proto` — the import edge is one-directional. (design D2 Consequences, as amended by the AllocationId fix)

Citation note for 2.2-2.6: these are Runtime Primitives (`02-project-structure.md:116`), not messages the Worker Model doc itself defines — cite the primitive's defining section, and additionally cite the `18-worker-model.md` line where the type is used as wire-crossing data (e.g., `WorkloadId` as correlation key), or, for `AllocationId`, the `15-allocation-model.md:41` line that names its shape. See Risks below re: the spec's literal wording.

## Phase 3: `worker.proto` — Worker Contract Projection

- [x] 3.1 File header: `syntax = "proto3";`, `package tibios.worker.v1;`, `import "tibios/primitives/v1/identity.proto";`, `import "google/protobuf/duration.proto";`. (design D2 Decision)
- [x] 3.2 Author `ResolvedModelRef` message with citation comment.
- [x] 3.3 Author `AllocationContract` message (uses `google.protobuf.Duration max_execution_duration`) with citation comment.
- [x] 3.4 Author `SecurityContext` message — deliberately small, supplied-only surface (tenant/principal + grant scope); MUST NOT contain `SessionId`, `NodeId`, `RuntimeId`, trust status, membership, lease, or credential fields. (design D1 Decision #1-2, Consequences; design Invariant #1, #2)
- [x] 3.5 Author `ObservabilityContext` message — trace identifiers as normative message fields, distinct from any transport-derived header. (design D1 Consequences; design Invariant #2, #3)
- [x] 3.6 Author `ExecutionContext` message: Workload, Allocation, `AllocationContract`, resolved dependency refs, `SecurityContext`, `ObservabilityContext`, Execution Parameters. No Channel field, no CancellationToken field. (spec: "ExecutionContext Reflects the Full Doc-Mandated Set"; proposal Approach #2) **Retyped in the post-verify fix batch**: `allocation_id` field changed from `tibios.primitives.v1.ObjectId` to `tibios.primitives.v1.AllocationId` (2.6) per spec.md "AllocationId Is a Distinct Primitive, Never ObjectId"; this is a wire-breaking type change, harmless today because no `worker-grpc-adapter` consumer exists yet.
- [x] 3.7 Author the six `ExecutionEvent` oneof arm messages: `OutputChunk`, `Progress`, `Warning`, `CheckpointCreated`, `MetricsSnapshot`, `EndOfStream` — each with a citation comment. (spec: "ExecutionEvent Is a Closed Six-Arm Union")
- [x] 3.8 Author `ExecutionEvent` message wrapping the 6-arm oneof from 3.7 — no 7th arm. (design Invariant #5)
- [x] 3.9 Author `ExecutionReport` message with citation comment — operational summary only, never application output; no retry/attempt-number/recovery-strategy field. (design D4 Rationale; design Invariant #9)
- [x] 3.10 Author `ExecutionPulse` message and `ExecutionPhase` enum with citation comments.
- [x] 3.11 Author `ExecutionResponse` message: `oneof payload { ExecutionEvent event = 1; ExecutionReport report = 2; }` — exactly two arms, no `WorkloadId` field. (design D4 Decision/R2; spec: "Response Stream Carries Both Events and a Terminal Report")
- [x] 3.12 Author `CancelRequest { WorkloadId workload_id = 1; }`, `PulseRequest { WorkloadId workload_id = 1; }`, and a named `CancelAck` message (not `google.protobuf.Empty`) meaning "request accepted", never "execution terminated". (design D4 R3; spec: "WorkloadId Is the Sole Correlation Key")
- [x] 3.13 Author the `WorkerExecution` service with exactly three RPCs: `SubmitJob(ExecutionContext) returns (stream ExecutionResponse)`, `Cancel(CancelRequest) returns (CancelAck)`, `Pulse(PulseRequest) returns (ExecutionPulse)`. (spec: "RPC Interface Is Closed to Three Methods")
- [x] 3.14 Self-review: confirm `worker.proto` imports `identity.proto` exactly once, no other intra-repo proto import — exactly one intra-repo edge total across both files. (design D2 Decision; design Invariant #4)

## Phase 4: Design Invariant Verification

One task per invariant in design.md's "Invariants This Design Imposes on the `.proto`" (9 items), checked against the files produced in Phases 2-3.

- [x] 4.1 Invariant 1 — grep both files for `SessionId|NodeId|RuntimeId|membership|trust|lease|credential`; confirm zero matches.
- [x] 4.2 Invariant 2 — confirm `SecurityContext` and `ObservabilityContext` fields are all plain supplied values, nothing negotiated or derived.
- [x] 4.3 Invariant 3 — confirm no message field represents transport metadata; confirm `ObservabilityContext`'s comment states the `traceparent` header is derived, never authoritative.
- [x] 4.4 Invariant 4 — confirm exactly 2 proto files exist, exactly 1 intra-repo import edge, both packages versioned `v1`.
- [x] 4.5 Invariant 5 — confirm `ExecutionEvent` oneof has exactly 6 arms and `ExecutionResponse` oneof has exactly 2 arms.
- [x] 4.6 Invariant 6 — confirm `ExecutionResponse`'s comment documents the report as exactly-one-per-stream-and-always-last, including for cancelled executions; flag that proto3 cannot enforce this structurally, so the comment + the spec scenario are the guard.
- [x] 4.7 Invariant 7 — confirm `Cancel` returns `CancelAck` (never `google.protobuf.Empty`) and its comment states "accepted, not terminated".
- [x] 4.8 Invariant 8 — confirm every message and enum in both files carries a leading citation comment. Fully resolved in final pass.
- [x] 4.9 Invariant 9 — grep both files for `retry|attempt|recovery`; confirm zero matches.

## Phase 5: `protoc`/`buf` Lint & Compile Verification

- [x] 5.1 Run `protoc -I ../TibiOS/proto --include_imports -o /dev/null tibios/primitives/v1/identity.proto tibios/worker/v1/worker.proto` (or `buf lint`/`buf build` equivalent) — confirm both files parse and resolve imports cleanly.
- [ ] 5.2 Run a scratch `prost`/`tonic` codegen invocation against both files (e.g. `tonic-build` inside a throwaway crate, or `protoc` with the Rust plugin) to confirm prost/tonic acceptance. Do not wire this into any real crate or add a `build.rs` — verification only, per the out-of-scope boundary. **BLOCKED**: neither `protoc-gen-prost` nor `protoc-gen-tonic` is installed; installing either requires `cargo install`, which compiles Rust and was judged out of policy for this proto-only change (global rule: never build). See Risks/final report.
- [x] 5.3 Run `python -m grpc_tools.protoc -I ../TibiOS/proto --python_out=<scratch> --grpc_python_out=<scratch> tibios/primitives/v1/identity.proto tibios/worker/v1/worker.proto` — confirm Python codegen succeeds and produces the expected absolute-import shape (`from tibios.primitives.v1 import identity_pb2`) that design D2 flags as the fragile edge.
- [x] 5.4 Discard all scratch codegen output from 5.1-5.3. Only the two `.proto` source files, the spec update (Phase 6), and this tasks doc are committed. (proposal Rollback Plan)

## Phase 6: Normative Mapping Table Finalization

- [x] 6.1 Cross-check every entry in `worker-wire-contract/spec.md`'s Mapping Table against the finished `.proto` files; confirm every `tibios_ray.execution.__all__` type has exactly one proto counterpart or a declared exception (`ExecutionChannel`, `CancellationToken`). (spec: "Bidirectional, Lossless Type Mapping")
- [x] 6.2 Confirm every proto-only addition (`WorkloadId`; `SecurityContext`/`ObservabilityContext` fields; Workload/Allocation identity in `ExecutionContext`) is explicitly recorded in the table as a Ray-side follow-up, not silently added. (spec: "Proto-only additions are recorded, not silent"; design D1 Consequences)
- [x] 6.3 Update `openspec/specs/worker-wire-contract/spec.md`'s "Notes (Provisional, Pending `sdd-design`)" section: remove the "Provisional" framing for the items design.md settled (envelope shape/names, Trust/Session applicability, file organization); keep the Rust-codegen-placement note as-is ("no bearing on this spec").
- [x] 6.4 Final review against proposal Success Criteria: exactly 3 RPCs; `WorkloadId` the sole correlation field on `Cancel`/`Pulse`; `ExecutionEvent` has exactly 6 arms; no retry/attempt/recovery field anywhere; every message cites a doc section; mapping table complete in both directions.

## Risks

| Risk | Note |
|---|---|
| Spec's citation requirement literally names `18-worker-model.md`, but `identity.proto`'s messages are Runtime Primitives defined in `02-project-structure.md` | Flagged in Phase 2's citation note and Invariant 4.8; fully resolved in final pass |
| `ExecutionResponse`'s "exactly one report, always last" invariant (design Invariant #6) cannot be enforced by proto3 structurally | Documented as a comment-only guard in task 4.6; genuine enforcement is a `sdd-verify`/adapter-level concern for the `worker-grpc-adapter` follow-up, not this change |
| Scratch codegen artifacts from Phase 5 could accidentally get committed | Task 5.4 makes cleanup an explicit, separate step |
