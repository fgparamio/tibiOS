# Tasks: runtime-object Data Family (Taxonomy + Domain Objects)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~150-200 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Full data family (`ObjectType`, `ObjectLifecycle`, `LogicalObject`, `ContentObject`) | PR 1 | Single PR, base main; tests included per type |

## Phase 1: ObjectType

- [x] 1.1 RED — test: `ObjectType` has exactly 10 variants matching `13-object-model.md:102` (`Workload, Message, Actor, Service, Dataset, Tensor, Checkpoint, Configuration, Artifact, Model`)
- [x] 1.2 GREEN — add `ObjectType` enum (10 variants, `Debug, Clone, Copy, PartialEq, Eq`) to `crates/runtime-object/src/lib.rs`

## Phase 2: ObjectLifecycle

- [x] 2.1 RED — test: `ObjectLifecycle` has exactly 8 variants (`Created, Validated, Registered, Available, Referenced, Updated, Archived, Deleted`)
- [x] 2.2 Review-only — `ObjectLifecycle` does not implement `Default` (deviation: Rust has no stable way to assert trait *absence* in a passing test; verified by review instead, documented inline in `lib.rs`)
- [x] 2.3 GREEN — add `ObjectLifecycle` enum (8 variants, `Debug, Clone, Copy, PartialEq, Eq`, no `Default` impl, no `transition`/`can_transition`/`validate` method)

## Phase 3: LogicalObject

- [x] 3.1 RED — test: constructor + accessors (`id`, `version`, `content_hash`, `kind`) round-trip the exact values supplied
- [x] 3.2 RED — test: `LogicalObject` implements `Clone`
- [x] 3.3 GREEN — add `LogicalObject` struct (`id: ObjectId, version: ObjectVersion, content_hash: ContentHash, kind: ObjectType`) with `new()` + accessors, `#[derive(Debug, Clone, PartialEq, Eq)]`

## Phase 4: ContentObject

- [x] 4.1 RED — test: constructor + `hash()` accessor round-trips the value supplied
- [x] 4.2 RED — test: `ContentObject` implements `Clone`
- [x] 4.3 RED — test: two distinct `LogicalObject`s (different `ObjectId`s) construct successfully with the same `ContentHash` value (content-addressability invariant)
- [x] 4.4 GREEN — add `ContentObject` struct (`hash: ContentHash` only — no `ObjectId`/`LogicalObject` field), `#[derive(Debug, Clone, PartialEq, Eq)]`

## Phase 5: Crate Doc Comment and Verification

- [x] 5.1 Update `runtime-object/src/lib.rs` crate-level doc comment: drop "stub" wording, still cite `13-object-model.md` and `23-object-store.md`
- [x] 5.2 Run `cargo test -p runtime-object`, `cargo clippy -p runtime-object --all-targets -- -D warnings`, `cargo check -p runtime-object` — all clean (also re-verified `cargo test --workspace` and `cargo clippy --all-targets -- -D warnings` clean)
- [x] 5.3 Verify no public trait declared in `runtime-object` (`rg "^pub trait"` — no match) — confirms the MODIFIED requirement's "no public traits" scenario
