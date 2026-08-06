# Tasks: Workspace Foundation

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~800-900 (root manifest ~40, primitives types+macro+tests ~350-400, 14 domain stubs ~220-260, runtime + guard ~150-200) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 → PR2 → PR3 (see Work Units) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|---|---|---|---|
| 1 | Phase 1 root manifest + Phase 3 (all 14 domain-crate stubs, mechanical, no logic) | PR 1 | ~270 lines; base = main or tracker branch |
| 2 | Phase 2 `runtime-primitives` (12 types, macro, Pure Operations, tests) | PR 2 | ~350-400 lines; cohesive single crate, real logic — deserves isolated review; base = PR 1 branch if feature-branch-chain |
| 3 | Phase 4 `runtime` + `architecture_guard.rs` + Phase 5 workspace-wide verification | PR 3 | ~200 lines + fixups; base = PR 2 branch if feature-branch-chain |

## Phase 1: Root Workspace Manifest

- [x] 1.1 Delete `src/lib.rs`; rewrite root `Cargo.toml` as virtual `[workspace]` (no `[package]`): `members` = all 16 paths (`crates/runtime-*` ×15 + `runtime`), `resolver = "2"`. *(workspace-manifest: Virtual Workspace With Exact Members; No Business Logic At The Workspace Root)*
- [x] 1.2 Add `[workspace.package]` (edition `"2024"`, version, license), `[workspace.dependencies]` (`serde`, `ulid` w/ `features=["serde"]`, `cargo_metadata`, path entries for all 15 internal crates), `[workspace.lints]` (`unsafe_code="deny"`, `missing_docs="warn"`).

## Phase 2: `runtime-primitives` (TDD)

- [ ] 2.1 Create `crates/runtime-primitives/Cargo.toml` (workspace fields, `[lints] workspace=true`, deps `serde`,`ulid`) + `src/lib.rs` `//!` doc citing `02-project-structure.md`. *(Ownership Documented; Exhaustive Dependency Set)*
- [ ] 2.2 RED: write failing tests for `Lease::is_expired`/`remaining`, `ContentHash::matches`, `ObjectVersion::next`.
- [ ] 2.3 GREEN: implement `identity.rs` (`ulid_newtype!` macro → `ObjectId, NodeId, RuntimeId, WorkloadId, AllocationId, SessionId, TenantId`), `lease.rs`, `time.rs`, `content.rs`, `error.rs`; re-export all 12 from `lib.rs`. *(The 12 Fundamental Types)*
- [ ] 2.4 REFACTOR: confirm zero domain logic, no hand-written `trait` beyond derives, deps stay within `{serde, ulid}`. *(Zero Domain Logic; No Public Traits In This Change)*

## Phase 3: Domain Crate Stubs (dependency order)

Each task = `Cargo.toml` (allowed deps only) + `src/lib.rs` doc stub; satisfies that crate's own spec (`Exhaustive Dependency Set` + `Stub Crate, No Public Traits`).

- [x] 3.1 `runtime-object` — dep: primitives; cites `13`,`23`.
- [x] 3.2 `runtime-network` — dep: primitives; cites `22`.
- [x] 3.3 `runtime-storage` — dep: primitives; cites `21`.
- [x] 3.4 `runtime-security` — dep: primitives; cites `08`.
- [x] 3.5 `runtime-observability` — dep: primitives; cites `09`.
- [x] 3.6 `runtime-deployment` — dep: primitives ONLY; cites `29`.
- [x] 3.7 `runtime-scheduler` — deps: primitives, object; cites `14`,`16`.
- [x] 3.8 `runtime-state` — deps: primitives, object, scheduler, network; cites `17`,`19`; doc-note network edge is data-contract-only (Runtime Events, never Transport/Session).
- [x] 3.9 `runtime-allocation` — deps: primitives, scheduler, object; cites `15`.
- [x] 3.10 `runtime-replication` — deps: primitives, object, storage; cites `24`.
- [x] 3.11 `runtime-worker` — deps: primitives, allocation, object; cites `18`.
- [x] 3.12 `runtime-admission` — deps: primitives, state; cites `20`.
- [x] 3.13 `runtime-api` — deps: primitives, admission, object, state, allocation, storage, network; cites `26`.
- [x] 3.14 `runtime-federation` — deps: primitives, network, replication, api; cites `31`.

## Phase 4: Composition Root + Architecture Guard (TDD)

- [ ] 4.1 Create `runtime/Cargo.toml` (bin, deps: all 15 domain crates, `[dev-dependencies] cargo_metadata`) + `runtime/src/main.rs` stub citing `02-project-structure.md` Composition Root section. *(Golden Rule; No Public Traits In This Change)*
- [ ] 4.2 RED: write `runtime/tests/architecture_guard.rs` with the 16-name member-set assertion and an `ALLOWED` matrix deliberately missing one edge (e.g. `allocation→scheduler`); run `cargo test -p runtime`, confirm it fails naming the missing dependency.
- [ ] 4.3 GREEN: correct `ALLOWED` to the exact final Allowed Edge Matrix (design doc); confirm `cargo test -p runtime` passes, including member-set and `runtime-primitives` external-allowlist assertions. *(Architecture Guard Enforces The Dependency Matrix; Hosts The Architecture Guard)*
- [ ] 4.4 Meta-verify: temporarily add `runtime-deployment → runtime-object`, confirm `cargo test --workspace` fails naming the unexpected dep, then revert. *(Scenario: Drift is caught)*
- [ ] 4.5 Meta-verify: temporarily drop `runtime-scheduler`'s dep on `runtime-object`, confirm failure naming the missing dep, then revert; confirm no violation is reported for `runtime`'s own full dependency set. *(Scenario: Missing required edge is caught; No crate depends on runtime)*

## Phase 5: Workspace-Wide Verification

- [ ] 5.1 Run `cargo fmt` across the workspace; confirm `cargo fmt --check` passes.
- [ ] 5.2 Run `cargo check --workspace`, `cargo test --workspace`, `cargo clippy --workspace -- -D warnings`; fix any fallout (e.g. `missing_docs`) until all four success-criteria commands are green.
