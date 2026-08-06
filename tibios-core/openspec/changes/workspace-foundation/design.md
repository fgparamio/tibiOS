# Design: Workspace Foundation

## Technical Approach

Encode `02-project-structure.md`'s Project Layout as a real Cargo workspace: a **virtual** root manifest with 16 members — 15 domain crates under `crates/` plus the `runtime/` Composition Root binary. Every non-primitives crate is a compiling stub; the only crate with content is `runtime-primitives`. Architectural drift is caught by an integration test inside `runtime`, not by a crate or an external CI tool.

## Architecture Decisions

### Decision: guard is a test in `runtime`, driven by `cargo metadata`

| Option | Tradeoff | Decision |
|---|---|---|
| 17th `architecture-tests` member crate | A crate that is not a domain violates "crates represent domains" | Rejected (superseded from proposal) |
| `cargo-deny [bans]` | Inbound-only, cannot detect *missing* edges, second config language + binary | Rejected; keep in reserve for licenses/advisories |
| Read each `crates/*/Cargo.toml` with `toml` | Must hand-roll dir walking, workspace-inheritance resolution, member detection | Rejected |
| **`cargo_metadata` dev-dep in `runtime/tests/`** | Adds a dev-only dep tree | **Chosen** |

Rationale: the guard is tooling, equivalent to a linter — swapping it must not move an architectural boundary. `runtime` already legitimately depends on everything, so hosting the test adds no edge. `cargo metadata --no-deps` returns exactly the workspace members with their *declared* dependencies (workspace inheritance already resolved), which is precisely the edge set to assert.

### Decision: `runtime` is a sibling directory, root manifest is virtual

`02`'s layout puts `runtime/` beside `crates/`, not at the manifest root. So the root `Cargo.toml` carries **no `[package]`** — pure `[workspace]`. This avoids the root-package-plus-workspace-root ambiguity entirely and makes `runtime/tests/` a normal package test dir. `src/lib.rs` is deleted.

### Decision: stubs are doc-comment only

Each stub `src/lib.rs` contains a `//!` module doc naming the crate's domain and citing its owning `docs/architecture/*.md`, and nothing else. No placeholder `pub mod` — speculative internal structure is modeling, which this change explicitly defers. Empty crates emit no lints.

### Decision: centralize versions and internal paths in `[workspace.dependencies]`

Root declares `serde`, `ulid`, `cargo_metadata`, **and all 15 internal crates by path**. Members then write one line per edge (`runtime-primitives.workspace = true`). Single place to bump versions; the guard still reads real per-crate edges from metadata.

## Allowed Edge Matrix (the guard's data — FINAL)

`p` = `runtime-primitives`; names below are without the `runtime-` prefix.

| Crate | Allowed workspace deps |
|---|---|
| `primitives` | — |
| `object` | p |
| `scheduler` | p, object |
| `allocation` | p, scheduler, object |
| `admission` | p, state |
| `worker` | p, allocation, object |
| `network` | p |
| `storage` | p |
| `security` | p |
| `observability` | p |
| `state` | p, object, scheduler, network |
| `replication` | p, object, storage |
| `deployment` | p |
| `api` | p, admission, object, state, allocation, storage, network |
| `federation` | p, network, replication, api |
| `runtime` | all 15 — sole exemption; nothing may depend on `runtime` |

Two edges are Data-Contract-only exceptions, not service dependencies: `allocation → scheduler` (granted by `02` §Domain Isolation for `AllocationPlan`/`Resource`) and `state → network` (State Assembler consumes Runtime Events Networking publishes — `TrustRevoked`, `MemberJoined`/`MemberLeft`, `HealthChanged`, `SessionEstablished`/`SessionClosed`, `PeerReachabilityChanged` — never Transport/Session internals). `deployment` is wired to other domains **only** by the Composition Root. `api` may reference only each domain's public Inbound Ports and shared types — not machine-checkable at crate granularity, enforced by review.

## File Changes

| File | Action | Description |
|---|---|---|
| `Cargo.toml` | Modify | Package manifest → virtual `[workspace]`: `members`, `[workspace.package]` (`edition = "2024"`, `rust-version`, `version`, `license`), `[workspace.dependencies]`, `[workspace.lints]` (`unsafe_code = "deny"`, `missing_docs = "warn"`) |
| `src/lib.rs` | Delete | cargo-new placeholder |
| `crates/runtime-<domain>/Cargo.toml` ×15 | Create | Inherits workspace package fields + `[lints] workspace = true`; declares only its allowed edges |
| `crates/runtime-<domain>/src/lib.rs` ×15 | Create | Doc-comment stub |
| `crates/runtime-primitives/src/{lib,identity,lease,time,content,error}.rs` | Create | The 12 fundamental types |
| `runtime/Cargo.toml` | Create | Bin package; depends on all 15; `[dev-dependencies] cargo_metadata` |
| `runtime/src/main.rs` | Create | Empty `fn main()` placeholder Composition Root |
| `runtime/tests/architecture_guard.rs` | Create | Dependency-graph guard |

## Interfaces / Contracts

`runtime-primitives` — ULID newtypes (`ObjectId`, `NodeId`, `RuntimeId`, `WorkloadId`, `AllocationId`, `SessionId`, `TenantId`) generated by one crate-private `ulid_newtype!` macro (7× identical `Debug/Clone/Copy/PartialEq/Eq/Hash/Serialize/Deserialize` + `new()` + `Display`); `Lease`, `Timestamp`, `ContentHash`, `ObjectVersion`, `ErrorClass` hand-written. Includes only the Pure Operations `02` names by hand: `lease.is_expired(now)`, `lease.remaining(now)`, `content_hash.matches(data)`, `object_version.next()`. `ulid` needs `features = ["serde"]`.

Guard shape:

```rust
const ALLOWED: &[(&str, &[&str])] = &[("runtime-primitives", &[]), /* … 16 rows */];
const PRIMITIVES_EXTERNAL: &[&str] = &["serde", "ulid"];
```

`MetadataCommand::new().manifest_path(<workspace root>/Cargo.toml).no_deps().exec()`, keep `DependencyKind::Normal | Build` (dev-deps exempt, so the guard's own `cargo_metadata` dep is legal), intersect with member names into a `BTreeSet`, and diff against the row. Accumulate **all** violations, then one `panic!` listing per crate `unexpected:` / `missing:`. A second assertion compares the member-name set to the 16 expected names, catching silent additions or renames.

## Testing Strategy

| Layer | What | How |
|---|---|---|
| Compile | Structure is real | `cargo check --workspace` |
| Integration | Edge set-equality, member set, primitives allowlist | `runtime/tests/architecture_guard.rs` |
| Unit | Pure operations | `#[cfg(test)]` in each primitives module |
| Meta | Guard actually fails | Manually add `runtime-deployment → runtime-object`, confirm red, revert |

## Migration / Rollout

No migration required — no behavior exists.

## Open Questions

- [ ] `Clock` / `RandomGenerator` Primitive Interfaces are **excluded** here (nothing to make testable yet); confirm they land with the ports follow-up.
- [ ] Dev-dependencies are exempt from the guard by design; revisit if a domain ever dev-depends across a forbidden boundary.
