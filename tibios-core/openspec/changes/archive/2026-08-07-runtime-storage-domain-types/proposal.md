# Proposal: runtime-storage Data Family (Authoritative Event Stream Primitives)

## Intent

`runtime-storage` is a stub with no public types, so the Authoritative Event Stream mechanism (`21-runtime-storage-engine.md:43-45`) that Admission, Trust, Allocation, Object Lifecycle, and Checkpoint Lifecycle all sit on has no shared vocabulary. Slice 1 introduces that vocabulary — pure data, no ports, no backend — following the established pattern (`ExecutionContext` before `WorkerService`, `AllocationContract` before allocation ports, `runtime-object`'s data family before `ObjectStore`). Establishing the ordering vocabulary here first prevents each future consumer from inventing its own ad-hoc sequence/stream concept.

## Scope

### In Scope
- `StreamId` — identifies exactly one per-aggregate consistency-domain stream (`21-runtime-storage-engine.md:45`: independently-ordered streams, no global log)
- `Sequence` — per-stream monotonic ordinal, the ordering primitive for `21-runtime-storage-engine.md:69` ("ordering is guaranteed only within a consistency domain")
- Crate doc comment citing `21-runtime-storage-engine.md`

### Out of Scope
- `append` / `replay` ports (Slice 2) and any concrete backend, in-memory or otherwise (Slice 3)
- Content Store, Snapshot Store, Report Store
- Any Object-specific payload type (`ObjectLifecycleEvent` and friends belong to `runtime-object`, per `23-object-store.md:174-176`)
- Q1 / Q3 (see Deferred Questions)

## Architectural Invariants Frozen By This Change

1. **Separation of responsibility.** `runtime-object` decides meaning — which lifecycle transition occurs (`23-object-store.md:174-176`). `runtime-storage` guarantees durability, ordering, and replay of whatever fact it is given (`21-runtime-storage-engine.md:13,19`: "Storage owns durability; the Runtime owns meaning" / "never... interprets business semantics"). Neither invades the other's responsibility.
2. **Log-is-authority (MUST-level, not observation).** Materialized/current state is ALWAYS a rebuildable projection of the log; the log is the only authoritative source. Three independent docs state this verbatim: `13-object-model.md:170`, `21-runtime-storage-engine.md:49-51`, `23-object-store.md:180`. This is settled, not ambiguous. It matters now because replay, snapshots, replication, recovery, and cross-node sync all follow for free once the contract holds — and none of them are recoverable if a "current state store" is allowed to become authoritative later.
3. **`runtime-storage` MUST remain domain-agnostic (NEW invariant, frozen now).** No public type in this crate may depend on `runtime-object` or assume any Object Lifecycle-specific concept. Payloads are opaque to Storage. Rationale: this crate serves Object Lifecycle, Admission, Trust, Allocation, and Checkpoint Lifecycle equally (`21-runtime-storage-engine.md:28-34`); the dependency arrow is `runtime-object → runtime-storage`, never the reverse.

## Capabilities

### New Capabilities
- `runtime-storage`: promotes the crate from stub to a stream-primitives data family (`StreamId`, `Sequence`)

### Modified Capabilities
- None — the existing stub spec has no requirements beyond "stub, no public traits"; this is additive within the same crate, written as a new full spec replacing the stub spec (same treatment as `runtime-object`). The "Exhaustive Dependency Set" requirement carries forward unchanged.

## Approach

Two plain value types, no traits, no behavior beyond constructors/accessors — mirroring `AllocationContract` and `runtime-object`'s data family. Generality is enforced structurally, not by comment: neither type carries a payload, so a domain-specific fact shape is unrepresentable in this crate's public API. Exact representations (`Sequence` backing integer, `StreamId` shape and whether it names a consistency domain by string or composite) are design-phase decisions.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `crates/runtime-storage/src/lib.rs` | Modified | Stub → `StreamId`, `Sequence` |
| `openspec/specs/runtime-storage/spec.md` | Modified | Stub spec → stream-primitives data-family spec |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| An Object-shaped type (`ObjectLifecycleEntry`, etc.) leaks into `runtime-storage`'s public API in a later slice, breaking crate generality | Med | Invariant 3 becomes a MUST-level spec requirement + Success Criterion; enforceable by the existing architecture-guard test pattern (dependency-set scan) |
| A future "current state" store is added and quietly becomes authoritative | Low | Invariant 2 frozen as MUST-level in the spec, with all three doc citations |
| `Sequence` semantics (gaps allowed? per-stream vs global?) resolved implicitly during implementation | Med | Per-stream scope is spec-frozen from `21-runtime-storage-engine.md:69`; gap policy is an explicit design-phase question |
| `21-runtime-storage-engine.md:101`'s "equivalent internal mechanism" latitude drifts into weaker guarantees at Slice 3 | Low | Out of scope here; flagged for Slice 3's design phase |

## Rollback Plan

Revert the commit; `runtime-storage` returns to stub. No crate depends on these types yet, so blast radius is zero.

## Dependencies

- None. `crates/runtime-storage/Cargo.toml` already declares exactly `runtime-primitives` — the correct and complete workspace dependency set for this slice. **No new workspace-crate dependency is added.** Design and tasks phases should not second-guess this.

## Resolved By Reference

- **Q2 — Transition ownership**: ANSWERED. `23-object-store.md:174-176` — "The Object Store does not own Object Lifecycle. Lifecycle transitions originate in `runtime-object`." `runtime-storage` has no authority over transitions; it records facts. Remove Q2 from `runtime-object`'s Open Questions when its spec is next touched.

## Deferred Questions (Explicitly Not Resolved Here — And Why)

- **Q1 — Legal lifecycle transitions** and **Q3 — Monotonic lifecycle progression**: the exploration established that `runtime-storage` *cannot* own these — it has no authority to validate or reject a fact (`21-runtime-storage-engine.md:19`). They belong to `runtime-object`'s future behavior/Ports phase. This change makes no attempt to resolve them and introduces no mechanism that could silently encode an answer.

## Success Criteria

- [ ] `runtime-storage` compiles with `StreamId` and `Sequence` public; no public traits, no behavior beyond constructors/accessors
- [ ] No public type in `runtime-storage` references `runtime-object` or any Object-specific concept, and no public type carries a payload
- [ ] `runtime-storage`'s only workspace dependency remains `runtime-primitives`
- [ ] Log-is-authority is written as a MUST-level requirement in the spec, citing all three docs
- [ ] Q1 and Q3 recorded as deferred with their reason; Q2 recorded as resolved-by-reference with citation
