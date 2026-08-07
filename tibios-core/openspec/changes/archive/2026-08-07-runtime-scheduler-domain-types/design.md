# Design: runtime-scheduler Data Family (Scheduling Domain Types)

## Technical Approach

Five plain value types in `crates/runtime-scheduler/src/lib.rs`, single flat file, no submodules (`runtime-object`/`runtime-storage` precedent). No traits, no Ports, no algorithm. Dependency set stays exactly `runtime-primitives` + `runtime-object`, zero external — both already asserted by `runtime/tests/architecture_guard.rs:24-27,93,129`.

## Architecture Decisions

### Decision: `Resource` owns its identity fields directly, does not wrap `LogicalObject`

**Choice**: `Resource { id: ObjectId, version: ObjectVersion, capacity: u64 }`.
**Alternatives**: embed `runtime_object::LogicalObject`.
**Rationale**: `LogicalObject` requires `ContentHash`+`ObjectType` — meaningless for `Resource` (not content-addressed, has no Object category). Forcing the wrap would either fabricate a fake `ContentHash`/`ObjectType` or leak an `Option`, both worse than owning the two fields Resource actually needs. `runtime-object` stays a declared dependency (matches the guard's exact-set assertion) but is unused in this slice — same "declared, not yet exercised" precedent as `runtime-storage`'s unused `runtime-primitives` in its own Slice 1.

### Decision: capacity is a plain `u64`, not a new `Capacity` newtype

**Choice**: `Resource::capacity(&self) -> u64`.
**Alternatives**: a `Capacity(u64)` newtype; a typed capability enum (GPU/CUDA/CPU/Memory).
**Rationale**: the user-confirmed scope names exactly five types (`Resource`, `Candidate`, `FilterResult`, `Score`, `AllocationPlan`) — adding a sixth expands agreed scope without a driving requirement. `14-resource-model.md`'s capability taxonomy (VRAM, CUDA, ROCm, ...) is explicit future work; inventing it now to give `u64` a wrapper would guess at a vocabulary nobody asked for yet. A raw `u64` costs nothing and is trivially promotable to a newtype later without breaking `Resource`'s shape.

### Decision: `Resource` excludes allocation-owned state by construction

**Choice**: no `current_workload`/`reservation`/`lease` field, anywhere.
**Rationale**: explicit constraint carried from exploration — `14-resource-model.md` calls capacity/allocated/available *observational*, and `15-allocation-model.md` already owns consumption (`Allocation`, `Lease`). Same enforcement style as `runtime-storage`'s "no payload field" — unrepresentable, not merely undocumented.

### Decision: `Candidate` pairs `NodeId` + `Resource`, nothing else

**Choice**: `Candidate { node: NodeId, resource: Resource }`.
**Alternatives**: also embed a Snapshot reference or Object Version list.
**Rationale**: `17-cluster-snapshot.md` places Snapshot construction in State Assembler, not here — `Candidate` only needs to say *which node, which resource*, matching "Candidate Discovery" in the `16-scheduling-engine.md` pipeline diagram.

### Decision: `FilterResult` reason is `String`, mirrors `IdentityParseError`

**Choice**: `enum FilterResult { Feasible, Infeasible(String) }`.
**Rationale**: `16-scheduling-engine.md`'s own pseudocode names this shape (`Feasible | Infeasible(reason)`); `String` for the reason matches `runtime-primitives::IdentityParseError`'s existing precedent for a free-text diagnostic.

### Decision: `Score` wraps `f64`, ordering via `f64::total_cmp`

**Choice**: `Score(f64)`, `Ord`/`Eq` implemented by delegating to `f64::total_cmp` (stable since 1.62) — never a fallible/NaN-rejecting constructor.
**Alternatives**: reject `NaN` in a fallible constructor; wrap a fixed-point integer.
**Rationale**: `total_cmp` gives a genuine total order over every `f64` value including `NaN`/signed zero with zero extra API surface — no `Result`, no external crate (matches the zero-external-dependency guard). A fixed-point integer would invent a scale nobody specified.

### Decision: `AllocationPlan` carries only `WorkloadId` + `Candidate` this slice

**Choice**: `AllocationPlan { workload: WorkloadId, candidate: Candidate }`. No Scheduling Metadata (`Priority`/`Cost`/`Affinity`/...), no dependency list.
**Rationale**: same "intentionally partial" precedent as `runtime-allocation`'s `AllocationContract` — `15-allocation-model.md`'s full metadata set and `17-cluster-snapshot.md`'s dependency-validation fields are real future requirements, not invented here. The core producer-owns-data-contract binding (which Workload, which Candidate) is the only fact this slice needs to freeze.

### Decision: no `serde` derives

Only `runtime-primitives` derives serde. Domain crates don't; the guard allowlists zero external dependencies for `runtime-scheduler`.

### Derives

| Type | Derives | Why |
|------|---------|-----|
| `Resource` | `Debug, Clone, Copy, PartialEq, Eq` | Small, `Copy`-friendly (two `Copy` identity fields + `u64`) |
| `Candidate` | `Debug, Clone, PartialEq, Eq` | Owns a `Resource` (Copy) + `NodeId` (Copy) — kept non-`Copy` for room to grow |
| `FilterResult` | `Debug, Clone, PartialEq, Eq` | Owns a `String` in one variant — not `Copy` |
| `Score` | `Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord` | Wraps `f64`; `Ord` via `total_cmp` |
| `AllocationPlan` | `Debug, Clone, PartialEq, Eq` | Owns a `Candidate` — not `Copy` |

## Data Flow

`runtime-object → runtime-scheduler` (declared, unused this slice). No edge back. `Resource` → `Candidate` → (`FilterResult`, `Score` — evaluated per `Candidate`, not stored on it) → `AllocationPlan`. Filter/Score outputs are pipeline products in this slice's tests, not fields of any stored type — storing them would presuppose the algorithm this change explicitly defers.

## File Changes

| File | Action | Description |
|------|--------|--------------|
| `crates/runtime-scheduler/src/lib.rs` | Modify | Stub → 5-type data family + unit tests |
| `openspec/specs/runtime-scheduler/spec.md` | Modify (at archive) | Merge this change's delta |

`Cargo.toml` unchanged.

## Interfaces / Contracts

```rust
pub struct Resource { /* id: ObjectId, version: ObjectVersion, capacity: u64 */ }
impl Resource {
    pub fn new(id: ObjectId, version: ObjectVersion, capacity: u64) -> Self;
    pub fn id(&self) -> ObjectId;
    pub fn version(&self) -> ObjectVersion;
    pub fn capacity(&self) -> u64;
}

pub struct Candidate { /* node: NodeId, resource: Resource */ }
impl Candidate {
    pub fn new(node: NodeId, resource: Resource) -> Self;
    pub fn node(&self) -> NodeId;
    pub fn resource(&self) -> &Resource;
}

pub enum FilterResult { Feasible, Infeasible(String) }

pub struct Score(f64);
impl Score {
    pub fn new(value: f64) -> Self;
    pub fn value(&self) -> f64;
}
// Ord/Eq via f64::total_cmp

pub struct AllocationPlan { /* workload: WorkloadId, candidate: Candidate */ }
impl AllocationPlan {
    pub fn new(workload: WorkloadId, candidate: Candidate) -> Self;
    pub fn workload(&self) -> WorkloadId;
    pub fn candidate(&self) -> &Candidate;
}
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|--------------|----------|
| Unit | `Resource` construction/accessors round-trip | `#[cfg(test)] mod tests` |
| Unit | `Resource` has no allocation-owned field | Review-only (structural, same as `runtime-storage`'s log-is-authority treatment) |
| Unit | `Candidate` construction round-trip | Same module |
| Unit | `FilterResult::Infeasible` reason round-trips | Same module |
| Unit | `Score` ordering (`higher > lower`) | Same module |
| Unit | `AllocationPlan` construction round-trip | Same module |
| Static | No public trait; dependency set unchanged | Review + `architecture_guard.rs` (existing) |

No integration/E2E layer — no Ports or transport exist yet.

## Migration / Rollout

No migration. Additive; nothing depends on `runtime-scheduler` yet. `FilterPolicy`/`ScoringPolicy`/`SchedulingStrategy` are a separate future change, not designed here.

## Open Questions

Carried from the spec: full capability taxonomy, `AllocationPlan`'s Scheduling Metadata and dependency list — both explicitly deferred, not answered here.
