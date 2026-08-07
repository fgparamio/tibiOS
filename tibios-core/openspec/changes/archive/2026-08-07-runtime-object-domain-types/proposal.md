# Proposal: runtime-object Data Family (Taxonomy + Domain Objects)

## Intent

`runtime-object` is currently a stub with no public types, blocking every future consumer (Scheduling, Storage, Replication, Object Store). Per the established pattern (`ExecutionContext` before `WorkerService`, `AllocationContract` before `runtime-allocation`'s ports), this change introduces the domain's vocabulary — pure data, no behavior — so later Port/Store work builds on a stable, spec-frozen semantic base instead of guessing at it mid-implementation.

## Scope

### In Scope
- `ObjectType` — closed enum, the object categories from `13-object-model.md:102`
- `ObjectLifecycle` — closed enum, the 8 states from `13-object-model.md:73-96`, no `Default`, no methods
- `LogicalObject` — immutable struct: `ObjectId` + `ObjectVersion` + `ContentHash` reference + `ObjectType`
- `ContentObject` — immutable struct: `ContentHash` identity, no back-reference to any `LogicalObject`

### Out of Scope
- `ObjectStore`, resolution, lookup, indexes, caching (Ports slice)
- Persistence, Object Lifecycle Log, event sourcing (Storage domain)
- Any `transition()`, `can_transition()`, or `validate()` method on `ObjectLifecycle`
- Replication, trust boundaries

## Capabilities

### New Capabilities
- `runtime-object`: promotes the crate from stub to a data-family spec (`ObjectType`, `ObjectLifecycle`, `LogicalObject`, `ContentObject`)

### Modified Capabilities
- None — `runtime-object`'s existing spec had no requirements beyond "stub"; this is additive within the same crate, written as a new full spec replacing the stub spec (analogous to how `worker-grpc-client-adapter` got a new full spec rather than a delta).

## Approach

Plain enums and immutable structs only, mirroring `AllocationContract`/`ExecutionContext`. `runtime-object` keeps depending on exactly `runtime-primitives` (`ObjectId`, `ObjectVersion`, `ContentHash` — no re-declaration). The content-addressability invariant (many `LogicalObject`s MAY share one `ContentObject`; `ContentObject` MUST NOT reference back) is encoded structurally: `ContentObject` has no `LogicalObject`/`ObjectId` field at all, making the wrong direction unrepresentable rather than just undocumented.

## Affected Areas

| Area | Impact | Description |
|------|--------|--------------|
| `crates/runtime-object/src/lib.rs` | Modified | Stub → `ObjectType`, `ObjectLifecycle`, `LogicalObject`, `ContentObject` |
| `openspec/specs/runtime-object/spec.md` | Modified | Stub spec → full data-family spec |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `ObjectType` enum closed now, but doc says "future types may be added" | Med | Document as a known, deliberate simplification (closed enum, same as `ExecutionEvent`'s six arms) — extension mechanism is a design-phase decision, not blocking this slice |
| Open Questions get silently answered by implementation instead of a future spec | Low | No methods exist on `ObjectLifecycle` in this slice — nothing to silently encode a transition-legality assumption into |

## Rollback Plan

Revert the commit; `runtime-object` returns to stub. No other crate depends on these types yet (dependency is out-of-scope for this change), so rollback has no downstream blast radius.

## Dependencies

- None beyond `runtime-primitives` (already satisfied)

## Open Questions

- **Q1 — Legal lifecycle transitions**: which of the 8 states may follow which? Can any be skipped or reversed? Deferred to the Ports/behavior slice.
- **Q2 — Transition ownership**: which component drives each lifecycle transition — `runtime-object` itself, Scheduler, Storage Engine, or the requesting consumer? Deferred to the Ports/behavior slice.
- **Q3 — Monotonic lifecycle progression**: can a state (e.g. `Created`) ever recur for the same Object after later states have already occurred? Deferred to the Ports/behavior slice — this data-family phase has no mechanism that could violate or enforce monotonicity either way.

## Success Criteria

- [ ] `runtime-object` compiles with `ObjectType`, `ObjectLifecycle`, `LogicalObject`, `ContentObject` public, no public methods beyond constructors/accessors
- [ ] `ContentObject` has no field referencing `LogicalObject`/`ObjectId` — content-addressability invariant is structurally enforced
- [ ] `runtime-object`'s only workspace dependency remains `runtime-primitives`
- [ ] Q1/Q2/Q3 recorded in the spec as explicit Open Questions, not silently resolved
