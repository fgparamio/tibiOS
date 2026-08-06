# Design: Worker gRPC Adapter (Rust codegen wiring)

This change operationalizes D3 of `openspec/changes/archive/2026-08-06-proto-worker-contract/design.md` (`:116-184`). That document settled *where* generated code lives and *that* two new guard tests must exist; it deliberately left the mechanism of each open (`:179-182`). This document settles the mechanisms. Decisions are numbered **D5–D8** so the two documents can be read side by side without collision.

Nothing here reopens D1–D4. The `.proto` is frozen (`openspec/specs/worker-wire-contract/spec.md`), the crate placement is fixed, and the workspace stays at 16 members.

## Decision Summary

| # | Question | Decision |
|---|---|---|
| D5 | How does `protoc` reach `build.rs`? | **Require it in `PATH` (or `PROTOC`), with a preflight in `build.rs` that fails with an install command.** `protoc-bin-vendored` rejected: the repo already assumes system `protoc`, and vendoring creates two compilers at two versions for one frozen contract. |
| D6 | Shape of the per-crate external allowlist | **`EXTERNAL_ALLOWED: &[(&str, &[&str])]` — the same assoc-list shape as `ALLOWED`, exhaustive over all 16 members, reusing `diff_dependencies`.** Plus one table-level test pinning `{prost, tonic, tonic-build}` to exactly one row. |
| D7 | Public-surface assertion mechanism | **A source-token containment scan inside `architecture_guard.rs`, on stable, with zero new tooling.** Assert the *stronger* invariant — no transport token outside `src/adapters/` — instead of trying to compute a public API. `cargo public-api` and rustdoc JSON rejected. |
| D8 | Vendored `proto/` drift detection | **Repo-root `proto/` + a `shasum -a 256 -c`-compatible manifest + three tests in `crates/runtime-worker/tests/proto_drift.rs`.** Two always run; the umbrella comparison runs only when `../proto/` is present. |

---

## D5 — `protoc` is a required system tool, not a vendored crate

### Decision

`build.rs` uses the system `protoc`, located by `prost-build`'s existing rules (`PROTOC` env var first, then `PATH`). Before invoking `tonic-build`, `build.rs` runs an explicit preflight and, on failure, panics with a message that names the fix:

```rust
// crates/runtime-worker/build.rs (shape, not final code)
println!("cargo:rerun-if-env-changed=PROTOC");
if std::env::var_os("PROTOC").is_none() && !path_contains("protoc") {
    panic!(
        "runtime-worker needs the protobuf compiler to generate the Worker \
         wire adapter from proto/.\n\
         Install it:  macOS `brew install protobuf`  |  Debian/Ubuntu \
         `apt-get install -y protobuf-compiler`\n\
         Or point at an existing binary:  PROTOC=/path/to/protoc cargo check \
         -p runtime-worker\n\
         Background: proto/README.md"
    );
}
```

(`path_contains` scans `std::env::split_paths(PATH)` for `protoc` / `protoc.exe`.) `protoc-bin-vendored` is **not** added. `runtime-worker`'s external allowlist stays exactly `{prost, tonic, tonic-build}` (D6).

### Rationale

**`protoc` is not a new assumption in this repo — it is an existing, exercised one.** The change that froze the contract verified it with the system binary: `2026-08-06-proto-worker-contract/tasks.md:29` records *"`protoc` found at `/opt/homebrew/bin/protoc` (`libprotoc 34.1`)"*, `:30` records the compile invocation, and `verify-report.md:30` records `EXIT:0`. That change's own proposal lists it under Dependencies (`proposal.md:76`: *"Tooling: `protoc` or `buf` for lint/compile verification"*). The contract's lint gate needs `protoc` whether or not Rust does. Adding a vendored copy does not remove the requirement; it duplicates it.

**Duplication is the actual cost, and it is a correctness cost, not a convenience one.** With `protoc-bin-vendored`, the repository compiles the *same frozen `.proto`* with two different compilers: the system one for the spec's lint gate, and a pinned bundled one for Rust codegen. When they disagree — a newer edition keyword, a stricter unused-import diagnostic — the `.proto` passes verification and fails the build, or vice versa, and the contributor has no reason to suspect two compilers exist. One contract, one compiler.

**The debuggability comparison favours the explicit failure, not the silent success.** The failure mode of D5 is a build error, at the first line of `build.rs`, naming the package manager command for the contributor's OS and the `PROTOC` escape hatch — one screen, zero prior knowledge required. The failure mode of `protoc-bin-vendored` is *no error at all* until someone builds on a target triple the crate ships no binary for; then the error surfaces from inside a transitive crate the contributor never added, with no mention of protobuf in the message. The first is a five-second fix; the second is an afternoon.

**There is no CI to protect yet, so "CI has no `protoc`" is a hypothesis, not a constraint.** The repository contains no `.github/`, no `Makefile`, and no `justfile` — verified. Whoever writes CI must install `protoc` regardless, because the `.proto` lint gate above needs it. Installing one tool in one workflow step is cheaper than carrying a binary-bundling dependency in every build forever.

**And the allowlist discipline cuts the same way.** `02-project-structure.md:155` draws the line at *protocols* — `prost`, `tonic` — and the guard machine-enforces the set (`architecture_guard.rs:77`, generalized by D6). A crate whose entire purpose is to embed a prebuilt binary is precisely the kind of entry that should require a reviewed allowlist edit. Keeping it out is not dogma: it means that if CI ever genuinely needs it, adding it is a visible, argued, one-line diff — which is the property the allowlist exists to provide.

### Alternatives Considered

| Alternative | Why rejected |
|---|---|
| **`protoc-bin-vendored` as a build-dependency** | Two compilers for one frozen contract; widens the allowlist with an opaque binary blob; converts an obvious missing-tool error into an obscure unsupported-target error. Kept as a named, reversible fallback (see Consequences), not the default. |
| **`protox` (pure-Rust `.proto` compiler)** | Removes `protoc` *and* the blob, but replaces the reference implementation with a reimplementation: the frozen contract would then be *verified* by `protoc` and *compiled* by something else. Two parsers, one contract — the same defect as vendoring, with an added semantic-divergence surface. |
| **Bare `tonic-build` call with no preflight** | `prost-build`'s own not-found message is serviceable but generic; it names neither the install command nor `proto/README.md`, and it appears mid-build rather than first. The preflight costs eight lines. |
| **`buf` / BSR remote generation** | Already rejected at proposal decision #1: external service plus network access inside a build, for two files. |

### Consequences

- **`proto/README.md` becomes the single onboarding page** for this dependency: install commands, the `PROTOC` override, and the re-vendor procedure from D8.
- **`build.rs` must be explicit about its inputs**: `cargo:rerun-if-changed` for each vendored `.proto` and for the manifest file, plus `cargo:rerun-if-env-changed=PROTOC`. Without them, editing the contract does not regenerate.
- **`build_server(false)`** (proposal Scope): `tibios-core` is the client. Not generating a server trait removes the sharpest edge of the "no public traits" tension before privacy has to do any work.
- **Multi-package codegen needs a single entry point.** The contract spans two proto packages (`tibios.primitives.v1`, `tibios.worker.v1`, `identity.proto:13` / `worker.proto`), and `prost` emits cross-package references as `super::super::…` paths that only resolve inside a correctly nested module tree. Two bare `include_proto!` calls will **not** compile. Use the builder's `include_file(...)` single-file mode and one `include!(concat!(env!("OUT_DIR"), "/_generated.rs"))` in `adapters/grpc/mod.rs`. If the pinned `tonic-build` does not expose `include_file` on its `Builder`, fall back to a `prost_build::Config` passed through the `*_with_config` entry point — same output, more ceremony. This is the one place `sdd-apply` should expect friction.
- **Escape hatch, pre-argued**: if a future CI target genuinely cannot install `protoc`, adding `protoc-bin-vendored` is a `[build-dependencies]` line plus one `EXTERNAL_ALLOWED` entry (D6) plus a spec amendment. Reversible, visible, and reviewed — which is why it does not need to be paid for today.
- **Two deviations surfaced during `sdd-apply`, both preserving this design's intent**: `build.rs` sets `.compile_well_known_types(true)` so `google.protobuf.Duration` (used by `AllocationContract`/`ExecutionReport`) is generated locally instead of requiring a direct `prost-types` dependency — keeping `runtime-worker`'s external allowlist at exactly `{prost, tonic, tonic-build}` per D6. The generated `Duration` type's upstream doc comments embed non-Rust code samples that rustdoc tried to compile as doctests, so `runtime-worker/Cargo.toml` sets `[lib] doctest = false` — this is `prost-build`'s own documented workaround and affects doctests only, not the crate's unit/integration test suite (verified: 23 unit + 3 integration tests still run and pass).

---

## D6 — `EXTERNAL_ALLOWED`: an exhaustive assoc-list, sharing `diff_dependencies`

### Decision

`PRIMITIVES_EXTERNAL` (`architecture_guard.rs:77`) is replaced by a table with the **same shape as `ALLOWED`** (`:16-74`) — an assoc-list of `(crate, &[dep])`, not a `HashMap`:

```rust
/// Per-crate external (non-workspace) dependency allowlist, `Normal` and
/// `Build` kinds only. Same shape as `ALLOWED`, so both tables read alike
/// and share `diff_dependencies`. EVERY member must appear: a missing row
/// is a violation, never a pass. That is what makes "and nowhere else" hold.
const EXTERNAL_ALLOWED: &[(&str, &[&str])] = &[
    ("runtime-primitives", &["serde", "ulid"]),
    ("runtime-worker", &["prost", "tonic", "tonic-build"]),
    ("runtime-object", &[]),
    // … the 12 remaining stubs, each `&[]` …
    ("runtime", &[]), // `cargo_metadata` is a dev-dependency; dev kinds are not scanned
];

/// The transport dependencies whose containment this change exists to
/// guarantee. Asserted to appear in exactly one `EXTERNAL_ALLOWED` row.
const TRANSPORT_CRATES: &[&str] = &["prost", "tonic", "tonic-build"];
```

Two tests replace `primitives_external_dependencies_are_allowlisted` (`:252-278`):

1. `every_crate_declares_exactly_its_allowed_external_dependencies` — loops all packages; computes the external set with the *existing* code at `:264-270` (invert the `member_names.contains` filter, keep the `Normal | Build` kind filter at `:169`); a package with no row pushes `"{name}: not present in the EXTERNAL_ALLOWED matrix"`, mirroring `:180-185`; otherwise delegates to `diff_dependencies` (`:121-136`) and collects violations into one assertion.
2. `transport_dependencies_are_allowlisted_for_exactly_one_crate` — a **table-only** test, no `cargo metadata`: each name in `TRANSPORT_CRATES` appears in exactly one row, and that row is `runtime-worker`.

`ALLOWED`, `EXPECTED_MEMBERS`, and the meta-tests at `:286-315` are unchanged.

### Rationale

**Reusing `diff_dependencies` is worth more than any structural elegance.** It already produces `"{crate}: unexpected={…} missing={…}"`, and it is the only function in the file covered by dedicated meta-tests (`:286-315`, the *"Drift is caught"* / *"Missing required edge is caught"* spec scenarios). A `HashMap<&str, &[&str]>` would buy O(1) lookup over 16 rows — irrelevant — while forcing either a duplicated comparison or a lifetime dance to keep sharing one. Same shape, same helper, same failure message, same meta-coverage.

**Exhaustiveness is the mechanism, not a stylistic preference.** The proposal's criterion is that the guard *"asserts `{tonic, prost, tonic-build}` on `runtime-worker` and nowhere else, and fails when any other crate gains them"*. Per-crate set *equality* plus a mandatory row for every member delivers exactly that, with no negative test: the day `runtime-network` declares `tonic`, its row says `&[]` and the diff reports `unexpected=["tonic"]`. Thirteen `&[]` rows also state a true fact the workspace currently relies on and nothing else records — verified: every crate except `runtime-primitives` declares zero external `Normal`/`Build` dependencies.

**The table-level test guards the table, which metadata cannot.** Equality catches a crate that *gains* `tonic`. It does not catch the more likely regression: a contributor turning the guard green by pasting `"tonic"` into a second row. Test 2 fails on the table alone, in-process, so spreading the protocol dependency requires deleting a test with an explanatory doc comment — a reviewable act rather than a silent one. This is the difference between D3's containment being a guarantee and being a convention (`archive/…/design.md:179`).

**The `Normal | Build` filter is already correct and must not be widened.** `tonic-build` is a `[build-dependencies]` entry, and `:169` already admits `DependencyKind::Build` — which is why a build-dep is caught by the same row rather than needing a parallel table. Dev-dependencies stay out: `runtime`'s `cargo_metadata` (`runtime/Cargo.toml:31-32`) is one, and D8 adds `sha2` as another.

### Alternatives Considered

| Alternative | Why rejected |
|---|---|
| **`HashMap<&str, &[&str]>`** | Needs a `LazyLock` or a per-call build for a 16-row lookup; diverges from `ALLOWED`'s shape for no benefit; makes "every member has a row" harder to read at a glance. |
| **Keep `PRIMITIVES_EXTERNAL`, add a second `WORKER_EXTERNAL`** | Two constants today, sixteen eventually. Says nothing about the other fourteen crates, so "nowhere else" stays unasserted — the exact gap D3 flagged. |
| **Allowlist only the crates that have external deps; treat absent rows as `&[]`** | Silently converts a *new* crate into an unguarded crate. A missing row must be loud. |
| **Include `DependencyKind::Development`** | Would forbid `runtime`'s `cargo_metadata` and D8's `sha2` — both legitimate — and would need a third column for test-only deps. Dev-deps neither ship nor enter the public API. Accepted, documented limitation: a `tonic` dev-dependency on another crate would pass. It cannot leak into a public API or a built artifact, so the containment property survives. |

### Consequences

- The `runtime-primitives` spec scenario *"External deps stay within the allowlist"* (`openspec/specs/runtime-primitives/spec.md:19-23`) is now satisfied by a row rather than a bespoke test. Note the spec says *subset* while the guard asserts *equality* — equality is the stricter reading and stays; no spec edit needed.
- `runtime-primitives`' containment against `prost`/`tonic` (`02-project-structure.md:155`) is preserved verbatim by its row, exactly as `archive/…/design.md:178` predicted.
- Declared dependencies only: `cargo metadata --no-deps` plus `package.dependencies` never sees transitives, so `prost` arriving under `tonic` is invisible and correct — the table records *intent*, not the resolved graph.
- `sdd-tasks` gets a mechanical unit: replace one constant, replace one test, add one test, touch nothing else in the file.

---

## D7 — Public-surface guard: a source-token containment scan, on stable, no new tooling

### Decision

The public-surface assertion lives in `runtime/tests/architecture_guard.rs` and reads source with `std::fs`. It asserts a **stronger and simpler** invariant than "no transport type in the public API":

> Outside `crates/runtime-worker/src/adapters/`, no non-comment line may contain a transport token, and the identifier `adapters` may occur exactly once — in the non-`pub` module declaration.

```rust
const WORKER_SRC: &str = "crates/runtime-worker/src";
const TRANSPORT_TOKENS: &[&str] =
    &["tonic::", "prost::", "tonic_build::", "include_proto!", "OUT_DIR"];
```

Three tests, all resolving paths through the existing `workspace_root()` helper (`:99-104`), all skipping lines whose trimmed form starts with `//`:

1. `runtime_worker_transport_types_stay_inside_the_private_adapter_module` — walk `WORKER_SRC/**/*.rs` excluding `adapters/`; no line contains a `TRANSPORT_TOKENS` entry.
2. `runtime_worker_never_reexports_the_adapter_module` — in the same file set, `adapters` occurs exactly once, on a line whose trimmed form is exactly `mod adapters;` in `lib.rs`.
3. `runtime_worker_generated_code_is_included_once_in_a_private_module` — `adapters/mod.rs` declares `mod grpc;` with no `pub`; `adapters/grpc/mod.rs` contains exactly one generated-code include.

Paired with, in `runtime-worker/src/lib.rs`, `#![deny(private_interfaces, private_bounds)]` — the compiler enforcing at build time what tests 1–3 enforce at test time.

### Rationale

**The existing mechanism is not merely a convention to match — it is incapable here, and that is the "strong reason".** `cargo_metadata` describes packages and edges; it cannot see an item's visibility. So *some* new mechanism is required. The property to preserve from the existing guard is the one its own doc comment states (`:1-7`): no extra crate, no extra tool, runs under plain `cargo test`. A source scan preserves all three; the candidates below preserve none.

**Do not compute the public API — assert containment, which implies it.** Classifying "is this line part of the public surface?" needs signature parsing: multi-line generics, `pub(crate)`, type aliases, trait impls, re-exports. Every heuristic there produces false negatives, and a guard with false negatives is worse than no guard because it is trusted. Containment sidesteps the whole problem: if `tonic::`/`prost::` never appears outside a private module, then no public item can name one — by construction, whatever the syntax. It is also *true by design* (D3, `archive/…/design.md:135`), so it costs nothing to maintain.

**Test 2 closes the hole tokens alone leave open.** `pub use crate::adapters::grpc::WorkerExecutionClient;` contains no transport token and would sail past test 1. Pinning the identifier `adapters` to a single occurrence — the module declaration itself — makes every re-export path, `pub use` or return type alike, a test failure. This is the concrete form of *"MUST NOT be re-exported"* (`archive/…/design.md:167`).

**The stated assumptions are cheap and must be written down.** Comment lines are stripped, so the crate doc can explain the adapter design in prose; block comments are not used in this crate and the guard says so; the scan is textual, so a contributor determined to defeat it can. The guard's job is to make an accidental leak impossible and a deliberate one obvious in review — the same bar `ALLOWED` sets.

### Alternatives Considered

| Alternative | Why rejected |
|---|---|
| **`cargo public-api`** (named as an option at `archive/…/design.md:169`) | Requires `cargo install` plus a nightly toolchain for API extraction. In `cargo test` it must either fail on every clean machine or skip when absent — and a guard that skips silently is a guard that reports green while enforcing nothing. Viable later as a CI-only extra check; not as the primitive. |
| **rustdoc JSON scrape** | `--output-format json` is nightly-only with an explicitly unstable schema; the workspace pins stable `rust-version = "1.93"` (`Cargo.toml:26`). Pins the guard to a moving format. |
| **Rely on Rust privacy alone** | Privacy stops a *private* type escaping. It does nothing about `pub fn f() -> tonic::Status`, since `tonic`'s types are public. `private_interfaces` is real but orthogonal — hence both, not either. |
| **A `trybuild`/compile-fail test proving the module is unreachable** | Adds a dev-dependency and a second test framework to prove what `mod adapters;` already proves syntactically, and still says nothing about `tonic::Status` in a signature. |

### Consequences

- One guard file remains the single place a reviewer looks; the file's doc comment gains a sentence explaining that it now enforces two kinds of invariant, graph and source.
- Workspace lints (`Cargo.toml:48-50`) set `missing_docs = "warn"`; clippy runs with `-D warnings` from the command line, not the manifest. Generated code therefore needs `#[allow(missing_docs, clippy::all, clippy::pedantic)]` **on the `mod grpc;` declaration** in `adapters/mod.rs` — a lint attribute on a module declaration covers the included file's contents, so one attribute suffices and nothing crate-wide is relaxed (proposal Risks).
- Test 1's token list is the extension point: a future `tonic-health` or `prost-types` adds a token, not a new test.
- Cost of the tests is a directory walk over four or five files — no measurable test-time impact.

---

## D8 — Vendored `proto/` at the repo root, `shasum`-compatible manifest, three tests

### Decision

**Layout** (mirroring the umbrella tree exactly, so `-I proto` produces byte-identical import paths — `worker.proto` imports `tibios/primitives/v1/identity.proto` by that path):

```
tibios-core/
├── proto/
│   ├── README.md                   provenance, protoc install (D5), re-vendor procedure
│   ├── PROTO_MANIFEST.sha256       machine-checked; no comments, no blank lines
│   └── tibios/
│       ├── primitives/v1/identity.proto
│       └── worker/v1/worker.proto
└── crates/runtime-worker/
    ├── build.rs                    reads ../../proto
    └── tests/proto_drift.rs        the three tests below
```

**Manifest format** — exactly `shasum -a 256` output: one line per file, `<64-hex><two spaces><path relative to proto/>`, sorted by path, LF-terminated, **no comment lines** (GNU `sha256sum -c` treats them as malformed input). Regenerate and verify with no project tooling at all:

```sh
cd proto && fd -e proto -t f . | sort | xargs shasum -a 256 > PROTO_MANIFEST.sha256
cd proto && shasum -a 256 -c PROTO_MANIFEST.sha256      # the same check, by hand
```

**Tests** in `crates/runtime-worker/tests/proto_drift.rs`, using `sha2` as a **dev-dependency** (added to `[workspace.dependencies]`):

| Test | Runs | Fails when |
|---|---|---|
| `manifest_covers_every_vendored_proto_file` | always | the set of `**/*.proto` under `proto/` differs from the set of manifest paths — in either direction |
| `vendored_proto_digests_match_the_manifest` | always | any digest differs; message names the file, both digests, and the regeneration command |
| `vendored_proto_matches_umbrella_source_when_present` | only if `../proto/` (or `$TIBIOS_PROTO_UPSTREAM`) exists | any vendored file differs byte-for-byte from its umbrella counterpart, or the umbrella has a `.proto` the vendored tree lacks |

Upstream root = `workspace_root().join("..").join("proto")`, i.e. `/…/TibiOS/proto`, overridable via `TIBIOS_PROTO_UPSTREAM`. Absent → the test passes and prints a one-line note to stderr; the *test name* is the documentation that it is conditional.

### Rationale

**Repo root, not `crates/runtime-worker/proto/`, because D2's ownership rule applies to the vendored copy too.** `identity.proto` is produced by `runtime-primitives`, not by the Worker domain (`archive/…/design.md:91`, citing `02-project-structure.md:325` — *"Data contracts belong to the domain that produces them"*). Nesting the whole tree under `runtime-worker` would nail the primitives contract inside the Worker crate — the precise failure D2 rejected for the single-file layout (`:95`) — and would send the next projection (`26-runtime-api.md`) reaching into another domain's crate directory for `ObjectId`. The proto root is a workspace-level asset; it lives at the workspace root.

**Two invariants, deliberately separated, because they answer different questions.** *Integrity* — "is the vendored copy the one that was reviewed?" — is answerable in any clone and must always run. *Freshness* — "has upstream moved?" — is only answerable where upstream exists. Collapsing them would force one of two bad outcomes: a standalone clone with an unguarded contract, or a standalone clone that cannot pass its own test suite. Splitting them means a standalone clone still gets a fully immutable, checksum-pinned contract; only the extra freshness signal is unavailable, and the tree it would compare against is unavailable too. That is a real limit, honestly bounded, not a hole.

**Set equality in test 1 catches the direction people forget.** Digest checking alone guards the files someone remembered to list. A third `.proto` added to `proto/` and not to the manifest would be compiled by `build.rs` and guarded by nothing. Comparing sets both ways makes the manifest exhaustive by construction.

**Manifest-format discipline buys tool independence.** Byte-compatibility with `shasum -a 256 -c` means the check is reproducible by any contributor, in any shell, with no Rust and no project script — and it means the *regeneration* command and the *test* cannot disagree about the format, because both are just SHA-256. That is why provenance prose (upstream path, commit, date) goes in `README.md` and not into the manifest: a comment line would break `-c` compatibility for a field no machine reads.

**`sha2` as a dev-dependency is free under D6's rules, and that is a design choice, not a loophole.** The guard scans `Normal | Build` kinds only (`architecture_guard.rs:169`), so a dev-dependency does not widen `runtime-worker`'s external allowlist `{prost, tonic, tonic-build}` and does not enter any shipped artifact. The alternative — shelling out to `shasum`/`sha256sum`, whose names and flags differ across platforms — trades a hermetic library for a non-hermetic subprocess. D6's Alternatives table records this exclusion explicitly so it stays a decision rather than an accident.

**The test lives with the artifact it guards.** `architecture_guard.rs` is about the dependency graph, per its own doc comment (`:1-7`). Proto drift is an input-integrity concern of one crate, and it belongs next to the `build.rs` that consumes those files — where a reviewer of `crates/runtime-worker/` cannot miss it.

### Alternatives Considered

| Alternative | Why rejected |
|---|---|
| **Git submodule for `proto/`** | `proto/` is tracked by the umbrella repo and has no remote of its own (proposal decision #1, verified: no `.gitmodules`, no `proto/.git`). A submodule needs a URL that does not exist. When one exists, the vendored path becomes the mount point with no layout change — this decision is forward-compatible by construction. |
| **Vendor into `crates/runtime-worker/proto/`** | Violates D2's ownership split; forces the next projection to depend on the Worker crate's directory for identity types. |
| **Fail when the umbrella is absent** | Makes a standalone clone unbuildable and untestable — which the vendoring exists to enable. |
| **Skip the checksum, compare only against the umbrella** | Zero guarantee in a standalone clone, and no protection against local edits in the monorepo either (an edit to both copies passes). |
| **A single combined digest of the whole tree** | Fails with "the tree changed" and names no file. Per-file digests cost nothing and name the culprit. |
| **`build.rs` performs the drift check** | Build scripts must not fail on environment shape (the umbrella may be legitimately absent), and a failure there is far harder to read than a failed test. `build.rs` declares `rerun-if-changed`; the test judges. |

### Consequences

- `proto/README.md` carries the two commands above plus the D5 install instructions, and records the upstream path and revision the copy was taken from. That revision line is **manual and unchecked** — stated plainly so nobody mistakes it for a guarantee. The checked facts are the digests and, when available, the byte comparison.
- `build.rs` resolves `proto/` as `CARGO_MANIFEST_DIR/../../proto` and emits `rerun-if-changed` for both `.proto` files and for `PROTO_MANIFEST.sha256`.
- Reading files outside the package directory means `cargo package`/`publish` would not include `proto/`. These are unpublished members of a virtual workspace, so it is inert today; if publishing ever happens, either `include` the path or set `publish = false`. Noted, not solved here.
- Updating the contract becomes a three-step, reviewable ritual: re-vendor, regenerate the manifest, commit both. The diff shows the `.proto` change and the digest change together.

---

## Carried Forward: the `runtime-primitives` API shape

Proposal decision #2 settled *that* primitives need fallible text constructors; the exact shape is design-level and is fixed here so `sdd-apply` does not re-derive it.

The five wire messages carry `string value` (`identity.proto:17-54`) — including `ObjectVersion` (`:24-26`), an intentional widening recorded at `openspec/specs/worker-wire-contract/spec.md:113` (proto `string`, Python `int`). So the ULID newtypes and `ObjectVersion` need *different* additions:

- **`ulid_newtype!` macro** (`crates/runtime-primitives/src/identity.rs:16-45`) gains, inside the existing `impl` block: `pub fn parse(text: &str) -> Result<Self, IdentityParseError>` (delegating to `Ulid::from_string`, already available under the `{serde, ulid}` allowlist) and `pub fn as_ulid(&self) -> Ulid`. Text out is the existing `Display`.
- **`ObjectVersion`** (`:85-100`) gains `pub const fn from_u64(u64) -> Self` and `pub const fn as_u64(&self) -> u64`; the wire→domain step is `text.parse::<u64>()` inside `convert.rs`, so the numeric constructor is all primitives owes.
- **`IdentityParseError`** is a small public struct/enum in `runtime-primitives` — a *type*, not a trait, so *"No Public Traits In This Change"* (`openspec/specs/runtime-primitives/spec.md:47-55`) survives untouched. Implementing `core::fmt::Display` on it is a std-trait impl, permitted by *"Zero Domain Logic"* (`:35-37`, *"trait impls needed for identity/serialization"*), exactly as `Display` already is.
- Deliberately **not** `FromStr`: `parse()` keeps the error type visible at the call site and adds no trait surface to argue about.

## File Changes

| File | Action | Description |
|---|---|---|
| `proto/{README.md,PROTO_MANIFEST.sha256,tibios/**}` | Create | vendored contract + provenance + digests (D8) |
| `crates/runtime-worker/build.rs` | Create | protoc preflight, `build_server(false)`, single-file include (D5) |
| `crates/runtime-worker/src/adapters/{mod.rs,grpc/mod.rs,grpc/convert.rs}` | Create | private module tree, generated include, `TryFrom` layer |
| `crates/runtime-worker/src/lib.rs` | Modify | `mod adapters;` (no `pub`), `#![deny(private_interfaces, private_bounds)]` |
| `crates/runtime-worker/tests/proto_drift.rs` | Create | the three D8 tests |
| `crates/runtime-worker/Cargo.toml` | Modify | `+tonic, +prost`; `[build-dependencies] tonic-build`; `[dev-dependencies] sha2` |
| `crates/runtime-primitives/src/identity.rs` | Modify | `parse`/`as_ulid`, `ObjectVersion::{from_u64,as_u64}`, `IdentityParseError` |
| `crates/runtime-primitives/src/lib.rs` | Modify | export `IdentityParseError` |
| `runtime/tests/architecture_guard.rs` | Modify | `EXTERNAL_ALLOWED` + `TRANSPORT_CRATES` (D6); three source-scan tests (D7) |
| `Cargo.toml` (workspace) | Modify | `[workspace.dependencies]`: `tonic`, `prost`, `tonic-build`, `sha2` — members unchanged |
| `openspec/specs/{runtime-worker,runtime-primitives,worker-wire-adapter}/spec.md` | Modify/Create | deltas per proposal Capabilities |

## Testing Strategy

| Layer | What | How |
|---|---|---|
| Unit | `TryFrom` rejects invalid ULID, unset message, unset `oneof`; each is `ErrorClass::Permanent` (`error.rs:12-22`) | `#[cfg(test)]` in `convert.rs` |
| Unit | primitives round-trip: `parse(Display(x)) == x`; `parse("not-a-ulid")` errs; `ObjectVersion` numeric round-trip | `#[cfg(test)]` in `identity.rs` |
| Integration | proto integrity, manifest coverage, umbrella freshness | `crates/runtime-worker/tests/proto_drift.rs` (D8) |
| Architecture | per-crate external allowlist; transport table pin; transport containment; no re-export; single include | `runtime/tests/architecture_guard.rs` (D6, D7) |
| Build | generated code compiles from vendored `proto/` | `cargo check -p runtime-worker` |

## Open Questions

None blocking. Two items to watch during apply, both with pre-decided fallbacks: whether the pinned `tonic-build` exposes `include_file` on its `Builder` (fallback: `prost_build::Config` via the `*_with_config` entry point, D5 Consequences), and whether a future CI target forces `protoc-bin-vendored` (fallback pre-argued, D5 Consequences).

## Inputs to Downstream Phases

- **`sdd-spec`** — D7's three assertions and D8's three tests are directly expressible as scenarios; the `runtime-worker` requirement rename ("Stub Crate, No Public Traits" → "Generated Transport Code Stays Private") and the external allowlist extension are enumerated at `archive/…/design.md:165-171`.
- **`sdd-tasks`** — the four natural slices from proposal Risks map cleanly onto this design: (1) primitives round-trip, (2) vendor `proto/` + manifest + drift tests + `build.rs` + private module, (3) `convert.rs`, (4) guard + specs. Slice 2 is the largest and the only one with build risk; slices 1 and 4 are independently mergeable.
- **`sdd-apply`** — D5's multi-package `include_file` note is the single highest-friction item; everything else is mechanical.
