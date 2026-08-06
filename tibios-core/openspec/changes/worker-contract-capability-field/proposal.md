# Proposal: Worker Contract — Capability Field On ExecutionContext

## Intent

Both Worker implementations must know **which behavior** an execution requests (e.g. `chat.generate`) to dispatch to the right provider. Neither `worker.proto`'s `ExecutionContext` (7 fields) nor its Rust mirror (`context.rs:155-163`) carries it. `tibios-ray`'s Python `ExecutionContext` (`context.py:67`) already models `capability: str` **with no contractual source** — it is invented locally today.

`worker.proto:8-13` states the governing rule: *"would `local-infer` still need it? If yes, it is here as a message field, not as gRPC metadata."* Both implementations need it. Per the project's own test, it belongs on the message — not in `execution_parameters`, not in transport metadata.

Why now: `worker-composition-root` is archived (`91ac512`); the base is clean, and no live gRPC peer exists yet, so this is the cheapest moment to change the contract.

## Scope

### In Scope
- New field on `proto/tibios/worker/v1/worker.proto`'s `ExecutionContext` (umbrella source + `tibios-core/proto/` re-vendor + `PROTO_MANIFEST.sha256` regen, one commit — `proto/README.md` ritual).
- New typed field + accessor on Rust `ExecutionContext`; `new()` goes 7→8 args.
- A **`runtime-worker`-local string newtype** for the value (D2), plus its `TryFrom` mapping in `adapters/grpc/convert.rs:290`.
- Amend `18-worker-model.md:52`'s Execution Context set and add a GLOSSARY row (D3 — non-optional).

### Out of Scope
- All `tibios-ray` Python wiring — its own change.
- Runtime dispatch logic reading the value. This change makes it constructible and readable, nothing more.
- **Considered, deferred**: (a) tibios-ray's 6-field `AllocationContract` vs. the wire's 1 — Ray-side modeling, no contract impact; (b) Python's missing `Cancelled` phase — already on the wire and in Rust, a Ray-side gap.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `worker-inbound-port`: `ExecutionContext`'s field shape and constructor arity.
- `worker-wire-contract`: the normative wire shape (7→8 fields) and its Rust mapping table.
- `runtime-worker`: "ExecutionContext Is Immutable Data…" (spec.md:88) field enumeration.
- `worker-wire-adapter`: conversion fallibility for the new field.

## Approach — Decisions

**D1 — Do not name it `capability`.** `GLOSSARY.md:35` already binds `Capability` to "a typed hardware/platform trait of a Resource **or Worker** (GPU, CUDA, VRAM…)" (`14-resource-model.md`), matched by Scheduling's Capability Filter (`25-ai-runtime.md:21`). `chat.generate` is a different concept under the same word — `GLOSSARY.md:88` calls that a **corpus defect**. Resolve by *qualification*, the precedent the corpus already used (`Configuration Object` vs. `Deployment Configuration`, GLOSSARY:31): **Worker Capability** — wire field `worker_capability`, Rust newtype `WorkerCapability`. Qualification keeps vocabulary shared with tibios-ray; inventing an unrelated word (`operation`, `kind`) would not, and risks a fresh collision. Final identifier confirmed in `sdd-design`.

**D2 — Newtype in `runtime-worker`, not `runtime-primitives`.** `runtime-primitives/src/lib.rs:5-8`: adding a primitive is an architectural change (adding `RuntimeId` required reopening `02-project-structure.md`). A capability name is Worker-domain vocabulary, not cross-domain identity. Shape follows `ContentHash` (`new(impl Into<String>)` + accessor), **not** `ulid_newtype!` — a namespaced name is not a ULID. Same reasoning on the wire: a worker-local `WorkerCapability { string value = 1; }` message, not an addition to `primitives/v1/identity.proto` (identity-only, "imports nothing"). A bare `string` is rejected — every other `ExecutionContext` field is typed.

**D3 — The doc amendment is the real gate.** `worker.proto:3-7` declares itself "a projection, never the canonical model"; `18-worker-model.md:52` enumerates the Execution Context set and has no capability item. Adding to the projection without amending its canon makes the projection self-contradictory. The doc edit ships in this change or the change is incoherent.

**D4 — Additive and wire-safe.** Verified: **zero `reserved` statements** in the whole `proto/` tree; `ExecutionContext` uses 1-7 contiguously. Field `8` is free. proto3 additive-field rules make this backward-compatible both directions; no package version bump, no migration.

**D5 — Absent value is a protocol error.** `TryFrom` rejects an empty/missing capability, consistent with `worker.proto:186-189` ("an unset `payload`… is a protocol error the receiver MUST reject via `TryFrom`, never silently skip"). Safe today precisely because no live peer exists — `tibios-ray`'s server is still a stub — so nothing can break in flight.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `../TibiOS/proto/tibios/worker/v1/worker.proto` | Modified | Upstream source of truth; edited first |
| `proto/tibios/worker/v1/worker.proto` + `PROTO_MANIFEST.sha256` | Modified | Re-vendor + digest regen, same commit |
| `crates/runtime-worker/src/execution/context.rs` | Modified | Field, accessor, `new()` 7→8; newtype |
| `crates/runtime-worker/src/adapters/grpc/convert.rs` | Modified | `TryFrom` at :290 + test at :793 |
| `runtime/src/worker/in_process.rs`, `runtime/src/main.rs` | Modified | `new()` call sites |
| `crates/runtime-worker/tests/port_is_testable_without_infrastructure.rs` | Modified | `new()` call site |
| `docs/architecture/18-worker-model.md`, `GLOSSARY.md` | Modified | Canon amendment + collision-resolving row |
| `openspec/specs/{worker-inbound-port,worker-wire-contract,runtime-worker,worker-wire-adapter}/` | Modified | Delta specs |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Editing a **frozen**, tagged (`architecture-v1.0`) contract + arch doc | High | Requires explicit maintainer sign-off before `sdd-apply`; D3 makes the doc edit reviewable in the same diff |
| Cross-repo desync: umbrella `.proto` moves, `tibios-ray` does not follow | High | `proto_drift.rs` catches vendored-vs-umbrella drift; Ray-side change tracked separately as a hard follow-up |
| Naming (D1) diverges from tibios-ray's `capability` | Medium | Ray field is unwired today; rename cost is ~0 now, high later. Mapping documented in `worker-wire-contract` |
| Breaking `new()` arity ripples into every construction site | Medium | Only 4 call sites (`rg`-verified) + 1 converter; all in-repo, all compiler-caught |
| D5 rejection semantics block a future lenient peer | Low | No live peer exists; revisit only if a peer ships before its capability wiring |

## Rollback Plan

Single revert. The `.proto` edit, re-vendor, manifest digest, and doc amendment ship in one commit; the Rust change in a second. Reverting both restores the 7-field shape and the 7-arg constructor exactly — no data migration exists to unwind (nothing persists an `ExecutionContext`), and no peer consumes field 8.

## Dependencies

- `worker-composition-root` (archived, `91ac512`) — satisfied.
- Maintainer approval to amend `18-worker-model.md` and the frozen `.proto`.
- **Follow-up, not a blocker**: `tibios-ray` change wiring the field into `context.py`.

## Success Criteria

- [ ] `ExecutionContext` carries a typed capability field on the wire and in Rust, with a read accessor.
- [ ] `18-worker-model.md:52`'s Execution Context set names it; `GLOSSARY.md` disambiguates it from Resource Capability.
- [ ] `shasum -a 256 -c PROTO_MANIFEST.sha256` passes; `proto_drift.rs` green against the umbrella tree.
- [ ] `cargo test --workspace` and `cargo clippy --all-targets -- -D warnings` clean.
- [ ] A wire `ExecutionContext` with no capability is **rejected** by `TryFrom`, covered by a test.
- [ ] No new dependency in `runtime-primitives`; no new primitive type added there.
