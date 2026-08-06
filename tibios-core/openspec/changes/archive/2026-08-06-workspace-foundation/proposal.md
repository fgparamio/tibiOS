# Proposal: Workspace Foundation

## Intent

`docs/architecture/` is frozen at `architecture-v1.0` (commit `8f11d0a`), but `src/lib.rs` still holds the cargo-new placeholder. Nothing in the repo enforces the frozen Project Layout, Dependency Rule, or Domain Isolation. Build the skeleton that structurally encodes the architecture now, before any domain code exists and drift becomes expensive.

## Scope

### In Scope

1. Root workspace `Cargo.toml` (virtual manifest, shared lints/profile/deps).
2. All 16 crates created empty: `lib.rs` with module stub + doc comment naming the architecture doc it implements; per-crate `Cargo.toml` declaring ONLY the edges in the table below.
3. Fundamental types in `runtime-primitives`: `ObjectId`, `NodeId`, `RuntimeId`, `WorkloadId`, `AllocationId`, `SessionId`, `TenantId`, `Lease`, `Timestamp`, `ContentHash`, `ObjectVersion`, `ErrorClass` — newtype-wrapped ULIDs unless noted.
4. Dependency-graph enforcement so drift fails the build.

### Out of Scope

- Any domain logic or business behavior.
- Defining each domain's public traits / Inbound Ports (follow-up change, after this lands).
- Async runtime, transport, persistence, or CLI wiring.

## Capabilities

### New Capabilities
- `workspace-layout`: the 16 crates, their names, ownership mapping to architecture docs, and workspace manifest.
- `runtime-primitives-types`: the 12 fundamental types, their newtype/ULID representation, and the no-domain-logic guardrail.
- `dependency-graph-enforcement`: machine-checked allowed-edge matrix, Composition Root exemption, primitives external-dep allowlist.

### Modified Capabilities
- None.

## Approach

### Allowed dependency matrix (FINAL — derived from `02-project-structure.md` + each domain's Ownership section)

| Crate | Depends on (workspace crates) | Owns |
|---|---|---|
| `runtime-primitives` | — | `02-project-structure.md` |
| `runtime-object` | primitives | `13`, `23` |
| `runtime-scheduler` | primitives, object | `14`, `16` |
| `runtime-allocation` | primitives, scheduler, object | `15` |
| `runtime-admission` | primitives, state | `20` |
| `runtime-worker` | primitives, allocation, object | `18` |
| `runtime-network` | primitives | `22` |
| `runtime-storage` | primitives | `21` |
| `runtime-security` | primitives | `08` |
| `runtime-observability` | primitives | `09` |
| `runtime-state` | primitives, object, scheduler, network | `17`, `19` |
| `runtime-replication` | primitives, object, storage | `24` |
| `runtime-deployment` | primitives ONLY | `29` |
| `runtime-api` | primitives, admission, object, state, allocation, storage, network | `26` |
| `runtime-federation` | primitives, network, replication, api | `31` |
| `runtime` (bin, Composition Root) | ALL — sole exemption | `02` Composition Root |

Invariants beyond the table: `runtime-deployment` is wired to other domains only by the Composition Root, never directly. `runtime-api` may reference only each domain's public Inbound Port contracts and shared types, never internal implementation modules. `runtime-primitives` external deps ⊆ `{serde, ulid}` and it holds no domain logic — it stays the most stable, minimal crate.

### Enforcement mechanism (the one open design question — recommendation)

**Recommended: a workspace test that reads `cargo metadata`, not `cargo-deny`.**

A test-only crate (`crates/architecture-tests`, empty lib, dev-deps `cargo_metadata`) hosts `tests/dependency_graph.rs`. It asserts, per crate, that the set of intra-workspace dependencies is *exactly* the row above — catching both forbidden edges and silently dropped ones — plus `runtime-primitives`' external allowlist. `runtime` is the single explicitly listed exemption.

Rationale: it runs under plain `cargo test --workspace` (no extra CI tool, no second config language), the allowed-edge matrix lives in Rust next to an assertion that explains the violation, and it can express set-equality. `cargo-deny`'s `[bans] wrappers` only expresses inbound restrictions, cannot detect missing edges, and needs a separate binary in CI; keep `cargo-deny` in reserve for licenses/advisories later, not for the graph.

Open sub-question for `sdd-design`: whether the guard lives in a 17th test-only member crate or in the `runtime` package's `tests/`. Test-only crate is preferred — it keeps the Composition Root free of guard code.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `Cargo.toml` (root) | Modified | Package manifest → virtual workspace manifest |
| `src/lib.rs` | Removed | Placeholder `add()` + default test deleted |
| `crates/runtime-*/` | New | 16 crates: manifest + stub `lib.rs` |
| `crates/architecture-tests/` | New | Dependency-graph guard |
| `openspec/` | New | SDD artifact trail |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Matrix mistranscribed vs. frozen docs | Med | `sdd-spec` cites the owning doc per crate; verify phase diffs table against `02-project-structure.md` |
| Guard rejects a legitimate future edge, tempting devs to delete the test | Med | Changing the matrix is a deliberate, reviewed edit with a doc citation in the commit body |
| `runtime-api` "public ports only" is not machine-checkable at crate granularity | High | Accepted: enforced by review + the follow-up ports change; guard covers crate-level edges only |
| Empty crates trip `clippy -D warnings` / dead-code lints | Low | Workspace-level lint config; doc comments on every stub module |

## Rollback Plan

Nothing here is deployed and no behavior exists. Revert the branch, or `git checkout architecture-v1.0 -- .` for tracked files and delete `crates/`. The frozen docs are untouched by this change.

## Dependencies

- Frozen `docs/architecture/` corpus at `architecture-v1.0`.
- External crates: `serde`, `ulid` (primitives); `cargo_metadata` (dev-only, guard).

## Success Criteria

- [ ] `cargo check --workspace` passes.
- [ ] `cargo test --workspace` passes, including the dependency-graph guard.
- [ ] `cargo clippy --workspace -- -D warnings` and `cargo fmt --check` pass.
- [ ] All 16 crates exist with the exact names above; each `lib.rs` cites its owning architecture doc.
- [ ] Adding a forbidden edge (e.g. `runtime-deployment` → `runtime-object`) makes `cargo test --workspace` fail.
- [ ] `runtime-primitives` declares only `serde` and `ulid` and contains no domain logic.
