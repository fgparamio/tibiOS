# Proposal: Worker gRPC Adapter (Rust codegen wiring)

## Intent

`proto-worker-contract` froze the wire contract at `../TibiOS/proto/` and deferred all Rust wiring here. Today `runtime-worker` is a 3-line stub with zero binding to that contract, and D3's containment (generated code stays private) is a convention with no machine guard. This change implements D3 exactly: `build.rs`, a private `adapters/` tree, a fallible conversion layer, and the two guard tests that make containment a guarantee.

## Decisions This Change Must Settle First

| # | Question | Decision |
|---|---|---|
| 1 | How does `../TibiOS/proto/` reach `build.rs` reproducibly? (left open by D3) | **Vendor to `tibios-core/proto/` + a committed SHA-256 manifest + a drift test.** `proto/` is tracked by the *umbrella* `TibiOS` repo, not by `tibios-core` (verified: no `.gitmodules`, no `proto/.git`) — a `tibios-core`-only clone cannot see it. Vendoring makes the build hermetic today; when `proto/` gets its own remote, the vendored path becomes the submodule mount point unchanged. `buf`/BSR rejected: external service + network in build for two files. |
| 2 | **New — blocks `convert.rs`.** `runtime-primitives` identity newtypes have no parse constructor and no accessor: `ObjectId(Ulid)` exposes only `new()`/`Default`/`Display`; `ObjectVersion(u64)` only `initial()`/`next()`. `TryFrom<proto::ObjectId>` is **impossible** as written. | Amend `runtime-primitives` with fallible text constructors + accessors. Its external allowlist stays `{serde, ulid}` (`Ulid::from_string` is already available), so `PRIMITIVES_EXTERNAL` and D3's "no prost/tonic in primitives" containment are untouched. |
| 3 | **New — bounds the conversion layer.** `runtime-worker`, `runtime-object`, `runtime-allocation` are all empty stubs; there is no `domain::ExecutionContext` to convert into. | Convert only across the boundary that exists: the 5 `identity.proto` messages ↔ their 5 primitives, plus total decoding of the two `oneof`s. Worker domain types stay out of scope. |

## Scope

### In Scope
- `crates/runtime-worker/build.rs` — `tonic-build` over the vendored `proto/`, **client-only** (`build_server(false)`): `tibios-core` is the gRPC client, `tibios-ray` is the server (design.md sequence diagram). Generating a server trait tibios-core never implements is what created D3's "public trait" tension in the first place.
- `crates/runtime-worker/src/adapters/{mod.rs,grpc/mod.rs,grpc/convert.rs}` — non-`pub` module tree; `include_proto!("tibios.worker.v1")`.
- `convert.rs` — `TryFrom` only, never `From`: ULID parsing, unset-message rejection, unset-`oneof` rejection (D4 R2). Private `ConversionError`, classified `ErrorClass::Permanent` (`04-error-handling.md:119`).
- `tibios-core/proto/` vendored copy + checksum manifest + drift test.
- Spec deltas: `runtime-worker` (2 requirements), `runtime-primitives` (1 new requirement).
- `runtime/tests/architecture_guard.rs` — `PRIMITIVES_EXTERNAL` → per-crate `EXTERNAL_ALLOWED` covering all 16 members; public-surface assertion for `runtime-worker`.

### Out of Scope
- Worker domain types, Inbound Ports, and their conversions — separate, later change.
- Any gRPC client *usage* (channel, tokio wiring, Composition Root) — this change compiles the adapter, it does not call it.
- Ray-side client/server; edits to the `.proto` (frozen); `workspace-manifest` (stays at 16 members).

## Capabilities

### New Capabilities
- `worker-wire-adapter`: fallible wire↔domain conversion — what `TryFrom` must reject and why (invalid ULID, unset message, unset `oneof`), and that rejection is `Permanent`, never silent.

### Modified Capabilities
- `runtime-worker`: "Stub Crate, No Public Traits" → "Generated Transport Code Stays Private"; "Exhaustive Dependency Set" gains external allowlist `{tonic, prost}` + build-dep `{tonic-build}`.
- `runtime-primitives`: new requirement — identity primitives round-trip through text (fallible parse in, `Display` out); `ObjectVersion` gains a numeric constructor/accessor. External allowlist unchanged.

### Unchanged, Explicitly Asserted
- `workspace-manifest` (16 members), `worker-wire-contract` (frozen).

## Approach

Rust's privacy rules do most of the work: a non-`pub` `mod adapters` makes every generated `pub` item invisible outside the crate. The gap is `pub use` re-export and the `private_interfaces` lint (warn-by-default) — so the guard asserts source-level that nothing re-exports `adapters`, and the crate escalates `private_interfaces` to `deny`. Generated code is exempted from workspace lints (`missing_docs = "warn"`, clippy) via `#[allow(...)]` on the private module only.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `crates/runtime-worker/build.rs` | New | `tonic-build`, the only place `protoc` runs |
| `crates/runtime-worker/src/adapters/**` | New | private generated module + `convert.rs` |
| `crates/runtime-worker/Cargo.toml` | Modified | `+tonic, +prost`, `[build-dependencies] tonic-build` |
| `crates/runtime-primitives/src/{identity.rs,lib.rs}` | Modified | fallible text constructors + accessors |
| `proto/` (in `tibios-core`) | New | vendored contract + checksum manifest |
| `runtime/tests/architecture_guard.rs` | Modified | per-crate external allowlist + public-surface assertion |
| `openspec/specs/{runtime-worker,runtime-primitives,worker-wire-adapter}/` | Modified/New | spec deltas + new capability |
| `Cargo.toml` (workspace) | Modified | `[workspace.dependencies]` entries only — members unchanged |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `tonic-build` needs a `protoc` binary in PATH (`prost-build` stopped vendoring it in 0.11) | High | Fail `build.rs` with an actionable message naming the install step; `protoc-bin-vendored` as fallback — but it widens the pinned external allowlist, so `sdd-design` decides |
| Vendored `proto/` drifts from the umbrella copy | Med | Checksum manifest + drift test that compares against `../../TibiOS/proto/` when present, and always detects local edits |
| Amending `runtime-primitives` is a second frozen-spec loosening D3 did not foresee | Med | Narrow: trivial constructors, permitted by "Zero Domain Logic"; adds no trait *declaration*, so "No Public Traits" survives; allowlist unchanged |
| Generated code trips `missing_docs`/clippy under `-D warnings` | High | `#[allow]` scoped to the private generated module, never crate-wide |
| Change exceeds the 400-line review budget | High | Natural slices: (1) primitives round-trip, (2) vendor + `build.rs` + private module, (3) `convert.rs`, (4) guard + specs — flag to `sdd-tasks` |

## Rollback Plan

Additive. Revert restores the 3-line stub; delete `crates/runtime-worker/{build.rs,src/adapters}`, `tibios-core/proto/`, and the three `Cargo.toml` deps. `runtime-primitives` constructors are purely additive and can stay or go independently. No consumer calls the adapter, so there is no migration to unwind. Guard and spec reverts are text-only.

## Dependencies

- `../TibiOS/proto/tibios/{primitives,worker}/v1/*.proto` at their archived, frozen state (source of the vendored copy).
- `protoc` on the build machine; crates `tonic`, `prost`, `tonic-build`; `ulid` (already a `runtime-primitives` dep).
- `openspec/specs/worker-wire-contract/spec.md` — normative, read-only here.

## Non-Goals

- Deciding mTLS vs. UDS peer credentials (D1 deferred it to `29-deployment.md` territory).
- Designing the Worker Inbound Port or `local-infer`.
- Publishing to a Buf Schema Registry.
- Adding a 17th workspace member — the answer stays no.

## Success Criteria

- [ ] `cargo check -p runtime-worker` succeeds with generated code compiled from the vendored `proto/`
- [ ] `mod adapters` carries no `pub`; no `pub use` in `runtime-worker` names it; `private_interfaces` is `deny`
- [ ] No `tonic::`/`prost::` path appears in `runtime-worker`'s public API
- [ ] `architecture_guard.rs` asserts `{tonic, prost, tonic-build}` on `runtime-worker` and nowhere else, and fails when any other crate gains them
- [ ] `cargo metadata` still lists exactly 16 members; `ALLOWED` matrix unchanged
- [ ] `TryFrom` rejects an invalid ULID, an unset required message, and an unset `oneof` payload — each with `ErrorClass::Permanent`
- [ ] The drift test fails when the vendored `proto/` diverges from its checksum manifest
- [ ] `cargo clippy --workspace -- -D warnings` is clean without crate-wide allows
