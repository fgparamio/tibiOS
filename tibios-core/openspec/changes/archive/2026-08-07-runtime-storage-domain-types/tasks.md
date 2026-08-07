# Tasks: runtime-storage Data Family (Stream Primitives)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~80-100 |
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
| 1 | Full data family (`StreamId`, `Sequence`) | PR 1 | Single PR, base main; tests included per type |

## Phase 1: StreamId

- [x] 1.1 RED — test: `StreamId::new`/`as_str` round-trip the exact name supplied
- [x] 1.2 RED — test: two `StreamId`s constructed to name the same stream are equal
- [x] 1.3 RED — test: two `StreamId`s constructed to name different streams are not equal
- [x] 1.4 GREEN — add `StreamId(String)` to `crates/runtime-storage/src/lib.rs` with `new(impl Into<String>)` / `as_str()`, `#[derive(Debug, Clone, PartialEq, Eq, Hash)]`

## Phase 2: Sequence

- [x] 2.1 RED — test: `Sequence::from_u64`/`as_u64` round-trip the exact value supplied
- [x] 2.2 RED — test: a later `Sequence` compares greater than an earlier one (same stream)
- [x] 2.3 GREEN — add `Sequence(u64)` to `crates/runtime-storage/src/lib.rs` with `const fn from_u64` / `const fn as_u64`, `#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]`; no `next()`, no `initial()`, no `Default`

## Phase 3: Domain-Agnosticism and Log-Is-Authority

- [x] 3.1 Review-only — Log-is-authority: no current-state type exists in this slice, so there is no runtime-passing test to write; verified by review that `StreamId`/`Sequence` are the only public types and neither represents materialized "current state" (deviation: mirrors `runtime-object`'s task 2.2 treatment of an untestable absence, documented inline in `lib.rs`)
- [x] 3.2 Review-only — confirm no public type references `runtime-object` or carries a payload field; confirm `crates/runtime-storage/Cargo.toml` still declares only `runtime-primitives`

## Phase 4: Crate Doc Comment and Verification

- [x] 4.1 Update `runtime-storage/src/lib.rs` crate-level doc comment: drop "stub" wording, still cite `21-runtime-storage-engine.md`
- [x] 4.2 Run `cargo test -p runtime-storage`, `cargo clippy -p runtime-storage --all-targets -- -D warnings`, `cargo check -p runtime-storage` — all clean
- [x] 4.3 Verify no public trait declared in `runtime-storage` (`rg "^pub trait" crates/runtime-storage/src/lib.rs` — no match)
