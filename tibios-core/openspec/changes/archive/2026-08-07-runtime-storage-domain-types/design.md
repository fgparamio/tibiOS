# Design: runtime-storage Data Family (Stream Primitives)

## Technical Approach

Two plain value types in `crates/runtime-storage/src/lib.rs`: `StreamId` (opaque `String` newtype, mirroring `ContentHash`) and `Sequence` (`u64` newtype, mirroring `ObjectVersion`). No traits, no ports, no backend. The workspace dependency set stays exactly `runtime-primitives` and the external set stays empty — both already asserted by `runtime/tests/architecture_guard.rs:41,98`.

## Architecture Decisions

### Decision: `Sequence` is a `u64` newtype with no `next()`, no `initial()`, no `Default`

**Choice**: `pub struct Sequence(u64)` with only `from_u64` / `as_u64` (both `const`).
**Alternatives**: mirror `ObjectVersion` wholesale, including `initial()`/`next()`/`Default`; or use `u128`.
**Rationale**: `u64` follows `ObjectVersion`'s precedent and is amply sufficient for a per-stream ordinal. But `next()` would structurally encode a step-1 contiguity policy and `initial()`/`Default` would encode a fixed origin — precisely the questions the proposal flagged as unresolved (Risk 3). Following `ObjectLifecycle`'s "deliberately no `Default`" precedent: omit rather than pick an answer nobody asked for.

**Gap policy (explicit)**: gaps ARE permitted at the type level. `Sequence` is an ordinal, not a counter — it asserts only that a later position compares greater within one stream (`21-runtime-storage-engine.md:69`). **Contiguity is not a structural guarantee of this slice**, because this slice has no append behavior that could enforce or violate it. Whether append guarantees `+1` or merely strict monotonic increase is a Slice 2/3 decision.

### Decision: `StreamId` is an opaque `String` newtype, not a composite

**Choice**: `pub struct StreamId(String)` with `new(impl Into<String>)` / `as_str()` — `ContentHash`'s exact shape.
**Alternatives**: a composite `{ aggregate_kind, aggregate_id }`; or a ULID newtype like `ObjectId`.
**Rationale**: the composite needs an `aggregate_kind` vocabulary, and any such vocabulary is domain knowledge — it would drag `21-runtime-storage-engine.md:45`'s named streams (Admission Log, Trust Log, …) into a crate that must stay domain-agnostic. The ULID option fails twice: `ulid` is not allowlisted as an external dependency here, and a `new()` generator implies streams are *minted* randomly when a consumer must *derive* stream identity deterministically from its aggregate. An opaque string lets each consumer name its own stream while Storage learns nothing about what the name means.

### Decision: domain-agnosticism enforced structurally, not by comment

**Choice**: neither type has a payload field, a generic parameter, or any field typed from another domain crate. `StreamId` wraps `String`, `Sequence` wraps `u64`; both closed over `core`/`std`.
**Alternatives**: `Entry { stream, sequence, payload }` with an opaque byte payload.
**Rationale**: same enforcement style as `runtime-object`'s "`ContentObject` has no back-reference field" — a domain-specific fact shape is **unrepresentable** in this crate's public API, not merely discouraged. Add a payload slot now and the first consumer specializes it.

### Decision: single flat `lib.rs`, no submodules

**Choice**: both types in `lib.rs`.
**Alternatives**: a `stream.rs` module now.
**Rationale**: `runtime-object` / `runtime-allocation` precedent — a crate stays one file until Ports introduce a second concern. Two types (~60 lines) don't warrant a split.

### Decision: no `serde` derives

Only `runtime-primitives` derives serde (it feeds the wire adapter). Domain crates don't, and the guard allowlists **zero** external dependencies for `runtime-storage`.

### Derives

| Type | Derives | Why |
|------|---------|-----|
| `StreamId` | `Debug, Clone, PartialEq, Eq, Hash` | `ContentHash`'s set minus serde. `Hash` because Slice 3 keys streams in a map. Not `Copy` — owns a `String`. |
| `Sequence` | `Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash` | `ObjectVersion`'s set minus serde; `Ord` satisfies "later compares greater". |

## Data Flow

`runtime-object → runtime-storage`, never reversed; no edge back and no payload field. Nothing flows *through* these types in this slice — they are vocabulary, not a pipeline.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `crates/runtime-storage/src/lib.rs` | Modify | Stub → `StreamId`, `Sequence` + unit tests; doc comment keeps citing `21-runtime-storage-engine.md` |
| `openspec/specs/runtime-storage/spec.md` | Modify (at archive) | Merge this change's delta |

`Cargo.toml` unchanged. Gotcha: `runtime-primitives` stays declared although Slice 1 doesn't use it — the guard asserts the exact declared set and no `unused_crate_dependencies` lint is on.

## Interfaces / Contracts

```rust
pub struct StreamId(String);
impl StreamId {
    pub fn new(name: impl Into<String>) -> Self;
    pub fn as_str(&self) -> &str;
}

pub struct Sequence(u64);
impl Sequence {
    pub const fn from_u64(value: u64) -> Self;
    pub const fn as_u64(&self) -> u64;
}
// No next(), no initial(), no Default: gap policy and origin stay unencoded.
// No payload field on either type.
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|--------------|----------|
| Unit | `StreamId` round-trip; same name ⇒ equal; different name ⇒ not equal | `#[cfg(test)] mod tests` in `lib.rs`, plain assertions — `runtime-object` style |
| Unit | `Sequence` `from_u64`/`as_u64` round-trip; later value compares greater | Same module |
| Static | **Log-is-authority**: no public type represents materialized "current state" | Review-only. No current-state type exists in this slice, so there is no behavior to assert — a passing test would prove nothing. Same treatment as `runtime-object`'s "no `transition` method". Testable at Slices 2-3. |
| Static | No public trait; no payload field; no `runtime-object` reference | Review + the existing `architecture_guard.rs` dependency scan (covers the `Cargo.toml` half) |

No integration or E2E layer — no ports or transport exist yet.

## Migration / Rollout

No migration. Additive; nothing depends on `runtime-storage` yet. Slice 2 (`append`/`replay` ports) and Slice 3 (backend) are separate future changes, **not** designed here — including the deferred contiguity question.

## Open Questions

Carried from the spec, unresolved here: Q1 (legal lifecycle transitions) and Q3 (monotonic lifecycle progression), both owned by `runtime-object`. Q2 is resolved by reference (`23-object-store.md:174-176`).
