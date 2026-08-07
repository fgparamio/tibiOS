# Proposal: runtime-scheduler Data Family (Scheduling Domain Types)

## Intent

`runtime-scheduler` is still a bare stub. Following the same two-slice discipline already applied to `runtime-object` and `runtime-storage`: freeze the domain's vocabulary before its behavior. This change gives the Scheduling Engine its language — `Resource`, `Candidate`, `FilterResult`, `Score`, `AllocationPlan` — with zero Ports, zero traits, zero algorithm.

## Scope

### In Scope
- `Resource` — capacity/capability envelope, Logical Object identity (`ObjectId`+`ObjectVersion`)
- `Candidate` — a Resource under evaluation during Candidate Discovery
- `FilterResult` — `Feasible | Infeasible(reason)` (`16-scheduling-engine.md`'s Filter phase)
- `Score` — continuous scoring output (Score phase)
- `AllocationPlan` — the Scheduler's pure-function output (Data Contract it owns, per `15-allocation-model.md`)

### Out of Scope
- `FilterPolicy`, `ScoringPolicy` traits and any Port
- `SchedulingStrategy`/`SchedulingEngine` — the pipeline/algorithm itself
- Cluster Snapshot type (owned by `19-state-assembler.md`, not this crate)
- Full GPU/CUDA/capability taxonomy — deferred, same "intentionally partial" precedent as `runtime-allocation`'s `AllocationContract`

## Capabilities

### New Capabilities
None — `runtime-scheduler` capability already exists as a stub spec.

### Modified Capabilities
- `runtime-scheduler`: replaces "Stub Crate, No Public Traits" with the data family; adds `Resource`, `Candidate`, `FilterResult`, `Score`, `AllocationPlan` requirements.

## Approach

Same shape as `runtime-object-domain-types`/`runtime-storage-domain-types`: plain value types in a single flat `lib.rs`, no submodules, no new external dependency (guard already allowlists zero for `runtime-scheduler`), TDD per type. `Resource` embeds `ObjectId`+`ObjectVersion` directly (mirrors `LogicalObject`'s identity fields) rather than depending on a `runtime-object` type — `runtime-object` stays a dependency because `Resource` is conceptually a specialized Logical Object per `14-resource-model.md`, even though this slice may not end up calling any of its code.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `crates/runtime-scheduler/src/lib.rs` | Modified | Stub → 5-type data family + tests |
| `openspec/specs/runtime-scheduler/spec.md` | Modified (at archive) | Merge this change's delta |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `Resource` capacity/capability fields drift into scheduler-internal or allocation state | Medium | Design phase freezes an explicit "observable capacity only" field set; no `current workload`/`reservation`/`lease` field |
| `Score` needs total ordering but wraps `f64` (no total order, NaN) | Medium | Design phase picks an explicit representation (reject-NaN-at-construction vs. integer scale) |
| Inventing capability vocabulary (CUDA/Metal/ROCm) prematurely | Medium | Keep `Resource`'s capability field minimal/opaque this slice, same as `AllocationContract`'s partial-field precedent |

## Rollback Plan

Revert the commit — additive change, nothing yet depends on `runtime-scheduler`'s public API.

## Dependencies

None beyond the already-declared `runtime-primitives`/`runtime-object`.

## Success Criteria

- [ ] `cargo test -p runtime-scheduler` and `cargo test --workspace` green
- [ ] `cargo clippy --all-targets -- -D warnings` clean
- [ ] No public trait declared; dependency set unchanged (`runtime-primitives`, `runtime-object`, zero external)
- [ ] `Resource` carries no scheduler-internal or allocation-owned field (workload/reservation/lease)
