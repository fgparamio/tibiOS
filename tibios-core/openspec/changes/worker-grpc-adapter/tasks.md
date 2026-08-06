# Tasks: Worker gRPC Adapter (Rust codegen wiring)

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines (total, all phases) | ~1,350-1,450 across code + vendored proto + already-written spec deltas. Breakdown: `runtime-primitives/src/identity.rs` ~110 (macro additions, `ObjectVersion` numeric ctor, `IdentityParseError`, unit tests) + `lib.rs` ~3; `crates/runtime-worker/build.rs` ~70; `crates/runtime-worker/Cargo.toml` ~8; `Cargo.toml` (workspace) ~6; `src/adapters/{mod.rs,grpc/mod.rs}` ~35; `src/lib.rs` (worker) ~6; `tests/proto_drift.rs` ~100; `src/adapters/grpc/convert.rs` ~300 (impls + unit tests); `runtime/tests/architecture_guard.rs` ~200 net (table swap + 5 new tests); vendored `proto/README.md` ~40 + `PROTO_MANIFEST.sha256` ~2 + `identity.proto` ~60 + `worker.proto` ~280 (**mechanical, byte-identical copies of already-frozen content — see note below**); spec deltas already written in `sdd-spec` (`runtime-worker` ~30, `runtime-primitives` ~35, `worker-wire-adapter` new ~96) |
| Vendored-proto line-count treatment | **Should not count toward authored-review budget, but will count toward any automated diff-size label.** ~342 of the ~1,350 total lines are `identity.proto`/`worker.proto` copied verbatim from the frozen umbrella source (`archive/2026-08-06-proto-worker-contract`) — zero new decisions, checked mechanically by `PROTO_MANIFEST.sha256`, not by human line-reading. Recommend reviewers verify via checksum + `diff` against umbrella, not line-by-line, and that any PR-size tooling exclude `proto/tibios/**` (e.g. `.gitattributes` `linguist-generated` or an equivalent PR annotation). Excluding it, authored content is ~1,010 lines; including it, ~1,350. |
| Files touched | New: `crates/runtime-worker/{build.rs,src/adapters/mod.rs,src/adapters/grpc/mod.rs,src/adapters/grpc/convert.rs,tests/proto_drift.rs}`, `proto/{README.md,PROTO_MANIFEST.sha256,tibios/primitives/v1/identity.proto,tibios/worker/v1/worker.proto}`. Modified: `crates/runtime-worker/{Cargo.toml,src/lib.rs}`, `crates/runtime-primitives/src/{identity.rs,lib.rs}`, `runtime/tests/architecture_guard.rs`, `Cargo.toml` (workspace). Already modified in `sdd-spec` (no new edits needed, confirmation only): `openspec/specs/{runtime-worker,runtime-primitives,worker-wire-adapter}/spec.md`. |
| 400-line budget risk | **High** — the proposal flagged this in Risks and it holds: only one 5-way slice below (Phase 2, vendoring) is close to/over budget on raw line count, and only because of mechanical proto copies; every other phase is comfortably under 400 authored lines. |
| Chained PRs recommended | **Yes** — 5 phases below (one more slice than the proposal's original 4-way split; Phase 2/vendor and Phase 3/build+module were split apart specifically to keep every code-bearing PR under 400 lines). Phases 1, 2 are independently mergeable; 3 depends on 2; 4 and 5 both depend on 3 and can ship in either order or in parallel. |
| Decision needed before apply | **Yes** — `delivery_strategy` is `ask-on-risk`; the orchestrator must ask the user: (a) accept 5 chained PRs as scoped below, with Phase 2 annotated as vendored/non-authored content, or (b) record a maintainer-approved `size:exception` and ship fewer, larger PRs. |
| Delivery strategy | `ask-on-risk` (cached) — **triggered**, see above |

---

## Sequencing Notes

- Phase 1 (`runtime-primitives`) has no dependency on any other phase and can be authored, reviewed, and merged first, independently of everything else.
- Phase 2 (vendor `proto/` + manifest) has no code dependency on Phase 1; it can proceed in parallel with Phase 1, but must complete before Phase 3, since `build.rs` reads the vendored tree and `proto_drift.rs` reads the manifest.
- Phase 3 (`build.rs` + private module tree + drift tests) depends on Phase 2 (vendored files must exist) and on the workspace-level dependency additions being in place; it does **not** depend on Phase 1.
- Phase 4 (`convert.rs`) depends on Phase 3 (generated wire types must exist to convert against) **and** on Phase 1 (`parse`/`as_ulid`/`ObjectVersion::from_u64`/`as_u64` must exist to implement `TryFrom`).
- Phase 5 (`architecture_guard.rs`) depends only on Phase 3 (transport deps declared, module tree shaped) — it does **not** depend on Phase 4's `convert.rs` contents. Phases 4 and 5 can therefore be authored and reviewed in parallel once Phase 3 lands.
- Within Phase 3, tasks 3.9-3.11 (drift tests) depend only on 3.1-3.2 (the `sha2` dev-dependency) and Phase 2, not on 3.3-3.8 (build.rs/module tree) — the two sub-groups can be authored in parallel.
- Within Phase 5, tasks 5.1-5.5 (D6, dependency-table tests) and 5.6-5.9 (D7, source-scan tests) are independent of each other and can be authored in parallel; 5.10-5.14 are read-only confirmation/cross-check tasks that run last.

---

## Phase 1: `runtime-primitives` Round-Trip Constructors/Accessors

*(independently mergeable; satisfies `runtime-primitives/spec.md` — "Identity Primitives Round-Trip Through Text Or Number"; design.md "Carried Forward: the `runtime-primitives` API shape")*

- [x] 1.1 Inside the `ulid_newtype!` macro's `impl` block (`crates/runtime-primitives/src/identity.rs:22-31`), add `pub fn parse(text: &str) -> Result<Self, IdentityParseError>` delegating to `Ulid::from_string`, and `pub fn as_ulid(&self) -> Ulid` — applies uniformly to all 7 ULID-backed newtypes (`ObjectId`, `NodeId`, `RuntimeId`, `WorkloadId`, `AllocationId`, `SessionId`, `TenantId`).
- [x] 1.2 Add `impl ObjectVersion { pub const fn from_u64(u64) -> Self; pub const fn as_u64(&self) -> u64 }` next to the existing `initial()`/`next()` methods (`:87-100`).
- [x] 1.3 Define `IdentityParseError` — a small `pub` struct or enum (not a trait), with a doc comment; implement `core::fmt::Display` for it. Deliberately not `FromStr` (design D-carried-forward: "keeps the error type visible at the call site").
- [x] 1.4 Export `IdentityParseError` from `crates/runtime-primitives/src/lib.rs`'s public API.
- [x] 1.5 Unit tests in `identity.rs`'s existing `#[cfg(test)] mod tests`: valid ULID text round-trips (`parse(Display(x)).unwrap() == x`, and `as_ulid()`'s rendered text matches the original); invalid ULID text (wrong length, bad charset, empty) is rejected with `Err`, never panics, never substitutes `Self::default()`; `ObjectVersion::from_u64` / `as_u64` round-trips (via a `parse`-style wrapper if the numeric constructor itself is infallible — confirm the *fallible* text-parsing entry point required by the spec is `text.parse::<u64>()` composed with `from_u64`, exercised here); non-numeric/negative/empty/overflowing text is rejected, never substitutes `ObjectVersion::initial()`.
- [x] 1.6 Self-review: confirm no method added implements scheduling/allocation/storage/domain behavior ("Zero Domain Logic"), no new hand-written `trait` declaration exists ("No Public Traits In This Change"), and the external allowlist stays exactly `{serde, ulid}` (no new dependency — `Ulid::from_string` is already available).

---

## Phase 2: Vendor `proto/` + Checksum Manifest

*(mechanical; independently mergeable in parallel with Phase 1; blocks Phase 3; design D8)*

- [ ] 2.1 Create `tibios-core/proto/README.md`: provenance (upstream path `../TibiOS/proto/`, revision the copy was taken from — **manual, unchecked, stated plainly as such**), `protoc` install commands per OS (D5: macOS `brew install protobuf`, Debian/Ubuntu `apt-get install -y protobuf-compiler`), the `PROTOC=` override, the manifest regenerate/verify commands, and the 3-step re-vendor ritual (re-vendor, regenerate manifest, commit both).
- [ ] 2.2 Vendor `tibios/primitives/v1/identity.proto` byte-identically from `../TibiOS/proto/tibios/primitives/v1/identity.proto` (frozen state) into `tibios-core/proto/tibios/primitives/v1/identity.proto`. No edits during vendoring.
- [ ] 2.3 Vendor `tibios/worker/v1/worker.proto` byte-identically into `tibios-core/proto/tibios/worker/v1/worker.proto`. No edits during vendoring.
- [ ] 2.4 Generate `PROTO_MANIFEST.sha256`: `cd proto && fd -e proto -t f . | sort | xargs shasum -a 256 > PROTO_MANIFEST.sha256` — one line per file, 64-hex + two spaces + path relative to `proto/`, sorted by path, LF-terminated, no comments, no blank lines (GNU `sha256sum -c` compatibility).
- [ ] 2.5 Verify: `cd proto && shasum -a 256 -c PROTO_MANIFEST.sha256` passes.
- [ ] 2.6 Self-review: the vendored tree mirrors the umbrella layout exactly (`tibios/primitives/v1/`, `tibios/worker/v1/`, sibling structure), so `-I proto` produces byte-identical import paths; if `../proto/` (or `../TibiOS/proto/`) is reachable locally, diff the vendored files against it to confirm zero drift before committing.

---

## Phase 3: `build.rs` + Private `adapters/` Module Tree + Drift Tests

*(depends on Phase 2; design D5, D7 module shape, D8 tests)*

- [ ] 3.1 `crates/runtime-worker/Cargo.toml`: add `tonic = { workspace = true }`, `prost = { workspace = true }` under `[dependencies]`; add `[build-dependencies] tonic-build = { workspace = true }`; add `[dev-dependencies] sha2 = { workspace = true }`.
- [ ] 3.2 Root `Cargo.toml`: add `tonic`, `prost`, `tonic-build`, `sha2` entries to `[workspace.dependencies]` — member list stays at 16.
- [ ] 3.3 `crates/runtime-worker/build.rs`: `protoc` preflight per D5's shape — check `PROTOC` env var, else scan `PATH` for `protoc`/`protoc.exe`; on failure, `panic!` with the OS-specific install command, the `PROTOC=` override, and a pointer to `proto/README.md`. Emit `cargo:rerun-if-env-changed=PROTOC`.
- [ ] 3.4 `build.rs`: emit `cargo:rerun-if-changed` for each vendored `.proto` file and for `PROTO_MANIFEST.sha256`.
- [ ] 3.5 `build.rs`: resolve `proto/` as `CARGO_MANIFEST_DIR/../../proto`; configure the `tonic_build::Builder` with `.build_server(false)` (client-only) and single-file `include_file(...)` mode spanning both proto packages, to make `prost`'s cross-package `super::super::` references resolve (D8's two-package nesting risk — two bare `include_proto!` calls will not compile). **Fallback, pre-argued in design**: if the pinned `tonic-build` doesn't expose `include_file` on `Builder`, use `prost_build::Config` via the `*_with_config` entry point for the same output.
- [ ] 3.6 `crates/runtime-worker/src/lib.rs`: add non-`pub` `mod adapters;`; add `#![deny(private_interfaces, private_bounds)]` crate attribute. Confirm the existing `18-worker-model.md` doc-comment citation is untouched.
- [ ] 3.7 `crates/runtime-worker/src/adapters/mod.rs`: non-`pub` `mod grpc;` declaration, with `#[allow(missing_docs, clippy::all, clippy::pedantic)]` on that declaration — the only scoped allow in the crate, covering the generated content included transitively.
- [ ] 3.8 `crates/runtime-worker/src/adapters/grpc/mod.rs`: exactly one `include!(concat!(env!("OUT_DIR"), "/<generated-file-name>.rs"))` matching whatever filename 3.5's `include_file(...)` config emits; non-`pub` `mod convert;` declaration for Phase 4's conversion layer.
- [ ] 3.9 `crates/runtime-worker/tests/proto_drift.rs`: `manifest_covers_every_vendored_proto_file` — the set of `**/*.proto` paths under `proto/` equals the set of paths in `PROTO_MANIFEST.sha256`, checked both directions.
- [ ] 3.10 `proto_drift.rs`: `vendored_proto_digests_match_the_manifest` — recompute each file's SHA-256 with `sha2`, compare to the manifest; on mismatch, name the file, both digests, and the regeneration command.
- [ ] 3.11 `proto_drift.rs`: `vendored_proto_matches_umbrella_source_when_present` — resolve `workspace_root().join("..").join("proto")` or `$TIBIOS_PROTO_UPSTREAM`; when absent, pass with a one-line stderr note; when present, byte-compare every vendored file against its umbrella counterpart in both directions (an umbrella-only file also fails).
- [ ] 3.12 Self-review: `cargo check -p runtime-worker` succeeds, compiling generated code from the vendored `proto/`; manually grep `crates/runtime-worker/src` outside `adapters/` for `tonic::`/`prost::` and confirm zero matches, ahead of Phase 5 formalizing this as a guard test.

---

## Phase 4: `convert.rs` — Fallible Wire ↔ Domain Conversion

*(depends on Phase 3 and Phase 1; satisfies `worker-wire-adapter/spec.md` in full)*

- [ ] 4.1 `crates/runtime-worker/src/adapters/grpc/convert.rs`: private `ConversionError` enum with variants for — invalid ULID text (naming the identity type), invalid `ObjectVersion` text, unset required message field (naming the field), unset `ExecutionEvent` oneof, unset `ExecutionResponse` oneof. (spec: "Every Conversion Rejection Is Classified Permanent, Never Silent Or Panicking")
- [ ] 4.2 Implement `Classify` for `ConversionError` (`04-error-handling.md:119`) — every variant returns `ErrorClass::Permanent`.
- [ ] 4.3 `TryFrom<proto::ObjectId> for runtime_primitives::ObjectId` via `ObjectId::parse`, mapping the ULID parse failure to `ConversionError`; plus the reverse wire-construction path (`Display`/`as_ulid` → proto string) needed for the round-trip test. (spec: "Well-formed identity value round-trips"; "Invalid ULID text is rejected, not defaulted")
- [ ] 4.4 `TryFrom<proto::ObjectVersion> for runtime_primitives::ObjectVersion` — `text.parse::<u64>()` composed with `ObjectVersion::from_u64`; failure maps to `ConversionError`. (spec: "Invalid ObjectVersion text is rejected, not defaulted")
- [ ] 4.5 `TryFrom<proto::ContentHash> for runtime_primitives::ContentHash` — no invalid-content case of its own; only the container-level unset-field rejection (4.7) applies to it.
- [ ] 4.6 `TryFrom<proto::WorkloadId> for runtime_primitives::WorkloadId` and `TryFrom<proto::AllocationId> for runtime_primitives::AllocationId` — same ULID-parse shape as 4.3.
- [ ] 4.7 Identify, from the now-vendored `worker.proto`, the `Option`-wrapped required identity-wrapper field(s) inside the `ExecutionEvent` arms / `ExecutionResponse` that have no meaningful empty/absent domain variant; reject `None` there with a `ConversionError` naming the missing field rather than fabricating a placeholder. (spec: "Unset Required Message Fields Are Rejected")
- [ ] 4.8 `TryFrom<proto::ExecutionEvent> for <its representation>` — exhaustive match over the six oneof arms (`OutputChunk`, `Progress`, `Warning`, `CheckpointCreated`, `MetricsSnapshot`, `EndOfStream`); reject an unset oneof. (spec: "ExecutionEvent's Six Arms Decode Exhaustively, Rejecting An Unset Oneof")
- [ ] 4.9 `TryFrom<proto::ExecutionResponse> for <its representation>` — exhaustive match over both oneof arms (`event`, `report`); reject an unset oneof. (spec: "ExecutionResponse's Two Arms Decode Exhaustively, Rejecting An Unset Oneof")
- [ ] 4.10 Unit tests in `convert.rs`'s `#[cfg(test)] mod tests`: round-trip for each of the 5 identity messages; invalid ULID text rejected for `ObjectId`/`WorkloadId`/`AllocationId`; invalid `ObjectVersion` text rejected; unset required field rejected and names the field; all six `ExecutionEvent` arms convert individually; unset `ExecutionEvent` oneof rejected; both `ExecutionResponse` arms convert; unset `ExecutionResponse` oneof rejected; every `ConversionError` variant's `Classify::classify()` returns `Permanent`; no conversion path panics (no `unwrap()`/`expect()` in non-test code).
- [ ] 4.11 Self-review: confirm `TryFrom` is used exclusively — never `From` — at every fallible boundary in this file (proposal Scope).

---

## Phase 5: `architecture_guard.rs` — Per-Crate Allowlist + Public-Surface Scan

*(depends on Phase 3, not on Phase 4; design D6, D7)*

- [ ] 5.1 Replace `PRIMITIVES_EXTERNAL` (`:77`) with `EXTERNAL_ALLOWED: &[(&str, &[&str])]` — one row for every one of the 16 workspace members: `("runtime-primitives", &["serde", "ulid"])`, `("runtime-worker", &["prost", "tonic", "tonic-build"])`, the remaining 13 members (including `runtime`) each `&[]`, with a comment noting `runtime`'s `cargo_metadata` is a dev-dependency and therefore out of scope for this table.
- [ ] 5.2 Add `TRANSPORT_CRATES: &[&str] = &["prost", "tonic", "tonic-build"]`.
- [ ] 5.3 Remove `primitives_external_dependencies_are_allowlisted` (`:252-278`).
- [ ] 5.4 Add `every_crate_declares_exactly_its_allowed_external_dependencies` — loop all packages; compute each package's external (`Normal | Build` kind) set by inverting the existing `member_names.contains` filter at `:264-270`; a package absent from `EXTERNAL_ALLOWED` pushes `"{name}: not present in the EXTERNAL_ALLOWED matrix"`; otherwise delegate to `diff_dependencies`; collect all violations into one assertion.
- [ ] 5.5 Add `transport_dependencies_are_allowlisted_for_exactly_one_crate` — table-only test (no `cargo metadata`): every name in `TRANSPORT_CRATES` appears in exactly one `EXTERNAL_ALLOWED` row, and that row's crate name is `runtime-worker`.
- [ ] 5.6 Add `WORKER_SRC: &str = "crates/runtime-worker/src"` and `TRANSPORT_TOKENS: &[&str] = &["tonic::", "prost::", "tonic_build::", "include_proto!", "OUT_DIR"]`.
- [ ] 5.7 Add `runtime_worker_transport_types_stay_inside_the_private_adapter_module` — walk `WORKER_SRC/**/*.rs` excluding `adapters/`, via `workspace_root()`; skip lines whose trimmed form starts with `//`; assert no remaining line contains any `TRANSPORT_TOKENS` entry. (spec: "Public API carries no tonic/prost path")
- [ ] 5.8 Add `runtime_worker_never_reexports_the_adapter_module` — over the same file set, the identifier `adapters` occurs exactly once, on a line whose trimmed form is exactly `mod adapters;`, in `lib.rs`. (spec: "No re-export escapes the private module")
- [ ] 5.9 Add `runtime_worker_generated_code_is_included_once_in_a_private_module` — `adapters/mod.rs` declares `mod grpc;` with no `pub`; `adapters/grpc/mod.rs` contains exactly one generated-code include line. (spec: "Generated code module is not public")
- [ ] 5.10 Extend 5.9 (or add a 4th, dedicated test) to assert `crates/runtime-worker/src/lib.rs` contains the literal `#![deny(private_interfaces, private_bounds)]`. (spec: "private_interfaces lint is denied")
- [ ] 5.11 Update the file's top doc comment (`:1-7`) to state it now enforces two invariant kinds: dependency graph (`ALLOWED`/`EXTERNAL_ALLOWED`) and source containment (5.7-5.10).
- [ ] 5.12 Confirm, without editing: `ALLOWED`'s `runtime-worker` row (`:32-34`) already lists exactly `runtime-primitives`, `runtime-allocation`, `runtime-object`, matching spec "Declared dependencies match the allowed set"; `EXPECTED_MEMBERS` and the meta-tests (`:286-315`) are untouched.
- [ ] 5.13 Final cross-check against the proposal's Success Criteria (8 items) — for each, name the task above that satisfies it; flag and file a follow-up for any gap found.

---

## Requirement Coverage Map

| Spec / Requirement | Phase / Task(s) |
|---|---|
| `runtime-primitives` — Identity Primitives Round-Trip Through Text Or Number | 1.1-1.6 |
| `runtime-worker` — Exhaustive Dependency Set | 3.1-3.2, 5.1-5.2, 5.4-5.5, 5.12 |
| `runtime-worker` — Crate Doc Comment Cites the Owning Document | 3.6 (confirmation) |
| `runtime-worker` — Generated Transport Code Stays Private (all 4 scenarios) | 3.6-3.8, 5.7-5.10 |
| `worker-wire-adapter` — Identity Wrapper Messages Convert Losslessly And Reject Invalid Content | 4.3-4.6, 4.10 |
| `worker-wire-adapter` — Unset Required Message Fields Are Rejected | 4.7, 4.10 |
| `worker-wire-adapter` — ExecutionEvent's Six Arms Decode Exhaustively | 4.8, 4.10 |
| `worker-wire-adapter` — ExecutionResponse's Two Arms Decode Exhaustively | 4.9, 4.10 |
| `worker-wire-adapter` — Every Conversion Rejection Is Classified Permanent | 4.1-4.2, 4.10 |
| Design D5 (`protoc` preflight) | 3.3-3.4 |
| Design D6 (`EXTERNAL_ALLOWED`) | 5.1-5.5 |
| Design D7 (source-token scan) | 5.6-5.10 |
| Design D8 (vendored proto + manifest + drift tests) | 2.1-2.6, 3.9-3.11 |

## Risks

| Risk | Note |
|---|---|
| `tonic-build`'s `Builder` may not expose `include_file` | Pre-argued fallback in 3.5: `prost_build::Config` via `*_with_config` — same output, more ceremony. Design flags this as the single highest-friction item for `sdd-apply`. |
| Vendored proto files inflate the raw diff line count despite being non-authored | Phase 2 isolates them into their own PR/commit with an explicit "mechanical copy, verify by checksum" note; recommend excluding `proto/tibios/**` from any automated PR-size gate. |
| `architecture_guard.rs` Phase 5 tests are only meaningful once Phase 3's Cargo.toml/module changes exist | Sequencing Notes make this dependency explicit; do not merge Phase 5 ahead of Phase 3. |
| Task 4.7's exact field(s) needing unset-rejection are not enumerable until Phase 2's vendored `worker.proto` exists | Task 4.7 explicitly defers field identification to apply-time inspection of the vendored file, not to this planning pass. |
