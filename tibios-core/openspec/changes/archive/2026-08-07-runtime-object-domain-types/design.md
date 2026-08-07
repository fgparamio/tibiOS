# Design: runtime-object Data Family (Taxonomy + Domain Objects)

## Technical Approach

Four plain types added directly to `crates/runtime-object/src/lib.rs`, no submodules — same flat-file style as `runtime-allocation`'s `AllocationContract` (74 lines, one file). The crate stays a single file until the Ports slice gives it enough surface to justify splitting (mirrors `runtime-worker`'s `execution`/`ports` split, which only appeared once there was real behavior to separate). `runtime-object` keeps depending on exactly `runtime-primitives`; no new dependency.

## Architecture Decisions

### Decision: Single flat `lib.rs`, no submodules yet

**Choice**: All four types in `lib.rs`.
**Alternatives considered**: A `taxonomy.rs` + `object.rs` split now.
**Rationale**: `AllocationContract` precedent — a crate stays one file until a second concern (Ports) demands separation. Four small types (~120-150 lines total) doesn't warrant it yet; premature splitting here is exactly the kind of unrequested structure the project's own precedent avoids.

### Decision: `ObjectType` and `ObjectLifecycle` are closed, non-`#[non_exhaustive]` enums

**Choice**: Ordinary `pub enum`, no `#[non_exhaustive]`.
**Alternatives considered**: `#[non_exhaustive]` to anticipate `13-object-model.md`'s "future object types may be added" note.
**Rationale**: Every other closed-enum precedent in this codebase (`ExecutionEvent`'s six arms, `ExecutionPhase`'s six states) is a plain closed enum, not `#[non_exhaustive]` — adding a variant later is already a breaking MODIFIED-spec change by this project's own convention (see `runtime-worker` spec history). Deciding the extension mechanism now would be answering a question nobody asked yet; follow precedent, revisit only if a real 11th category shows up.

### Decision: `LogicalObject` stores `ContentHash` directly, not `ContentObject`

**Choice**: `LogicalObject`'s content-pointer field is typed `ContentHash`, not `ContentObject`.
**Alternatives considered**: `LogicalObject` embedding a full `ContentObject`.
**Rationale**: `ContentHash` is the identity; resolving it to an actual `ContentObject` is Object Store work (`23-object-store.md`'s `ResolveContent(ContentHash)`), explicitly out of scope here. Embedding `ContentObject` would smuggle a resolution/lookup dependency into pure data.

### Decision: No `Owner`, `Metadata`, `SecurityContext`, `Placement`, or `State` fields yet

**Choice**: `LogicalObject` carries only `ObjectId`, `ObjectVersion`, `ContentHash`, `ObjectType`. `ContentObject` carries only `ContentHash`.
**Alternatives considered**: Adding the full field set `13-object-model.md`'s "Object Identity" section lists (Type, Owner, Metadata, Security Context, Lifecycle, Placement, State).
**Rationale**: Matches `AllocationContract`'s own precedent of being "intentionally partial" — the proposal scoped exactly these fields, and `13-object-model.md`'s Persistence section confirms current lifecycle state is a *projection*, not a stored field, which is the same reasoning for why `ObjectLifecycle` isn't embedded in `LogicalObject` at all in this phase.

## Data Flow

    runtime-primitives                    runtime-object
    ┌─────────────────┐                  ┌──────────────────────────┐
    │ ObjectId         │─────────────────▶│ LogicalObject             │
    │ ObjectVersion     │─────────────────▶│  { id, version,          │
    │ ContentHash       │──────┬──────────▶│    content_hash, kind }  │
    └─────────────────┘        │           └──────────────────────────┘
                                │
                                └──────────▶┌──────────────────────────┐
                                            │ ContentObject             │
                                            │  { hash }                │
                                            └──────────────────────────┘

    ObjectType, ObjectLifecycle: standalone enums, no edges to the above structs in this phase.

## File Changes

| File | Action | Description |
|------|--------|--------------|
| `crates/runtime-object/src/lib.rs` | Modify | Stub → `ObjectType`, `ObjectLifecycle`, `LogicalObject`, `ContentObject` + unit tests |
| `openspec/specs/runtime-object/spec.md` | Modify (at archive) | Merge this change's delta |

## Interfaces / Contracts

```rust
pub enum ObjectType {
    Workload, Message, Actor, Service, Dataset,
    Tensor, Checkpoint, Configuration, Artifact, Model,
}

pub enum ObjectLifecycle {
    Created, Validated, Registered, Available,
    Referenced, Updated, Archived, Deleted,
}
// No Default. No transition/can_transition/validate methods.

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LogicalObject {
    id: ObjectId,
    version: ObjectVersion,
    content_hash: ContentHash,
    kind: ObjectType,
}
impl LogicalObject {
    pub fn new(id: ObjectId, version: ObjectVersion, content_hash: ContentHash, kind: ObjectType) -> Self;
    pub fn id(&self) -> ObjectId;
    pub fn version(&self) -> ObjectVersion;
    pub fn content_hash(&self) -> &ContentHash;
    pub fn kind(&self) -> ObjectType;
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ContentObject {
    hash: ContentHash,
}
impl ContentObject {
    pub fn new(hash: ContentHash) -> Self;
    pub fn hash(&self) -> &ContentHash;
}
```

`ObjectType` and `ObjectLifecycle` derive `Debug, Clone, Copy, PartialEq, Eq` (cheap value types, same as `ExecutionPhase`).

## Testing Strategy

| Layer | What to Test | Approach |
|-------|--------------|----------|
| Unit | `ObjectType`/`ObjectLifecycle` variant counts, no `Default` on `ObjectLifecycle` | `#[cfg(test)] mod tests` in `lib.rs`, plain assertions — same style as `identity.rs` |
| Unit | `LogicalObject`/`ContentObject` constructor+accessor round-trip, `Clone` | Same module |
| Unit | Two `LogicalObject`s sharing one `ContentHash` construct without error | Same module — proves the many-to-one invariant isn't accidentally blocked |
| Static | No `transition`/`can_transition`/`validate` method exists | Enforced by review — no such method is written; nothing to test at runtime for an absence |

No integration or E2E layer — this crate has no ports or transport yet.

## Migration / Rollout

No migration required. Additive-only; no other crate depends on `runtime-object` yet, so nothing downstream breaks.

## Open Questions

Carried from the spec — not resolved by this design, deferred to the Ports/behavior change: Q1 (legal transitions), Q2 (transition ownership), Q3 (monotonic progression).
