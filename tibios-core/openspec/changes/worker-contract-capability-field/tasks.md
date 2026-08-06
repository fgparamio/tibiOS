# Tasks: Worker Contract — Capability Field On ExecutionContext

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~195 (Commit 1 ~45, Commit 2 ~150) — carried forward verbatim from design.md D11 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Decision needed before apply | No |
| Delivery strategy | `auto-chain` (project default) — **not triggered**: the forecast does not recommend chaining, so this ships as **one PR, two work-unit commits** |
| Rationale for one PR | Splitting into multiple PRs would ship the contract/proto change reviewable only against a doc amendment that has not landed yet, which proposal D3 explicitly forbids — the doc amendment and the contract edit must land together (design.md D11) |

### Suggested Work Units

| Unit | Goal | Commit | Notes |
|---|---|---|---|
| 1 | Contract + canon: proto message + field, vendored re-copy, manifest, two doc amendments, one-line test-literal fix | Commit 1 | Structural only, exempt from RED/GREEN — see gotcha below |
| 2 | Domain + adapter: `WorkerCapability` newtype, `ExecutionContext` 8th field, 2 `TryFrom`/`From` impls, 3 new tests, 4 spec-delta merges | Commit 2 | RED/GREEN throughout, base = Commit 1 |

**Sequencing**: strictly sequential, not parallel. Commit 2 depends on Commit 1's regenerated `worker_proto::ExecutionContext` (new `worker_capability: Option<WorkerCapability>` field) to exist before any Rust domain/adapter code referencing it can compile.

**Gotcha carried from design.md D11 (load-bearing, do not drop)**: the moment the `.proto` gains field 8, `prost` regenerates `worker_proto::ExecutionContext` with the new field, and the existing struct literal at `crates/runtime-worker/src/adapters/grpc/convert.rs:793` (test `missing_allocation_contract_is_rejected_and_classifies_permanent`) fails to compile (`E0063`, missing struct field) unless it also gains `worker_capability: None,`. **This one-line fix ships in Commit 1**, not Commit 2, so Commit 1 alone compiles and tests green (this project's per-slice-green norm).

**Gotcha carried from design.md D10 (load-bearing, do not drop)**: `ExecutionContext::new` goes 7 → 8 positional parameters. `clippy::too_many_arguments` is warn-by-default at threshold 7, and this workspace declares no `clippy.toml`/`[workspace.lints.clippy]` table, so `cargo clippy --all-targets -- -D warnings` fails at 8 arguments unless a narrow, commented `#[allow(clippy::too_many_arguments)]` is added to the single `new()` item (never at module scope). This must land in the same task that adds the 8th argument, or Commit 2's own lint gate fails.

---

## Commit 1 — Contract + Canon (structural, exempt from RED/GREEN cycling; ~45 lines)

*No test-first cycling applies to this commit: it is proto/doc/manifest editing plus one mechanical compiler-driven literal fix, not new behavior. Verify by compiling + running the existing test suite, not by writing a new failing test first.*

- [x] 1.1 (structural, exempt) In `../proto/tibios/worker/v1/worker.proto` (the umbrella source of truth), add `message WorkerCapability { string value = 1; }` at line 63, between `ObservabilityContext` (ends :62) and `ExecutionContext` (:64), using the file's `// TypeName — prose` + `// docs/architecture/...` citation comment convention (design.md D7 gives the exact comment text — reuse it verbatim, including the explicit disambiguation from `GLOSSARY.md:35`/`:88`'s hardware/platform `Capability`).
- [x] 1.2 (structural, exempt) In the same umbrella file, add `WorkerCapability worker_capability = 8;` as the last field of `ExecutionContext` (after `execution_parameters = 7`), and update `ExecutionContext`'s own doc block (`:64-72`) to enumerate the new field (`..., the requested Worker Capability, and Execution Parameters`) per D7. Fields 1-7 keep their exact tags and types; none is marked `reserved`.
- [x] 1.3 (structural, exempt) Byte-identical re-vendor: copy the umbrella `../proto/tibios/worker/v1/worker.proto` to `proto/tibios/worker/v1/worker.proto` (manual ritual per `proto/README.md`). Diff the two files to confirm byte-identity before proceeding.
- [x] 1.4 (structural, exempt) Regenerate `proto/PROTO_MANIFEST.sha256`'s `worker.proto` digest: `fd -e proto -t f . | sort | xargs shasum -a 256` from `proto/`, replacing only the `tibios/worker/v1/worker.proto` line; the `identity.proto` line stays unchanged since that file is untouched.
- [x] 1.5 (structural, exempt) Amend `docs/architecture/18-worker-model.md:52`: insert `Worker Capability,` into the Execution Context enumeration between `Dependency References (…)` and `Execution Channel`; append the one clarifying sentence design.md D8 specifies distinguishing it from the hardware/platform Capability of `14-resource-model.md`.
- [x] 1.6 (structural, exempt) Amend `docs/architecture/GLOSSARY.md` bidirectionally per D8: add a new `Worker Capability` row after the `Execution Context` row (line 46), keeping Worker Model rows contiguous; amend the existing `Capability` row (line 35) to append `— distinct from a Worker Capability (`18-worker-model.md`).` A one-way row is explicitly rejected by the design — do not skip the line-35 amendment.
- [x] 1.7 (structural, exempt — compiler-driven, not TDD) In `crates/runtime-worker/src/adapters/grpc/convert.rs`, add `worker_capability: None,` to the `worker_proto::ExecutionContext` struct literal at line 793 (test `missing_allocation_contract_is_rejected_and_classifies_permanent`). This is the single line that keeps Commit 1 compiling on its own once `prost` regenerates the wire type with the new field — do not defer it to Commit 2.
- [x] 1.8 Verify Commit 1 in isolation: `shasum -a 256 -c PROTO_MANIFEST.sha256` from `proto/`; `cargo build --workspace` (regenerates `worker_proto` via `build.rs`/`tonic-build`); `cargo test -p runtime-worker --lib adapters::grpc::convert` — confirm `missing_allocation_contract_is_rejected_and_classifies_permanent` still asserts `MissingField("allocation_contract")` (proves the literal fix didn't change the assertion). Do not run the full workspace clippy gate yet — Commit 2 hasn't landed the `#[allow]` for the not-yet-existing 8-arg constructor.

---

## Commit 2 — Domain + Adapter (RED/GREEN throughout; base = Commit 1; ~150 lines)

### Slice A — `WorkerCapability` newtype in `execution/context.rs`

- [ ] 2.1 RED — In `crates/runtime-worker/src/execution/context.rs`'s `#[cfg(test)] mod tests`, add `worker_capability_new_and_name_round_trip`: `WorkerCapability::new("chat.generate").name() == "chat.generate"`. Fails to compile — `WorkerCapability` does not exist yet.
- [ ] 2.2 GREEN — Declare `WorkerCapability` in `execution/context.rs`, after `ObservabilityContext` and before `ExecutionContext` (D6): `#[derive(Debug, Clone, PartialEq, Eq, Hash)] pub struct WorkerCapability(String);` with `pub fn new(name: impl Into<String>) -> Self` and `pub fn name(&self) -> &str`, both `#[must_use]`. Deliberately no `Serialize`/`Deserialize` (D6 deviation — no serde dependency in this crate). Doc comment cites `18-worker-model.md:52` and the disambiguation from `14-resource-model.md`'s Capability, matching D7's proto comment in spirit.

### Slice B — `WorkerCapability` wire conversion (independent of `ExecutionContext`'s own field)

- [ ] 2.3 RED — In `convert.rs`'s test module, add three tests: `worker_capability_round_trips_through_wire` (domain → wire `From` → wire `TryFrom` → equal original); `worker_capability_rejects_unset_message` (`worker_proto::ExecutionContext.worker_capability: None` — this is deferred to Slice C since it needs the `ExecutionContext` field; here instead test the standalone message: build a `worker_proto::WorkerCapability { value: String::new() }` and assert `TryFrom` on it, not on `None`, rejects); `worker_capability_rejects_empty_value` (`worker_proto::WorkerCapability { value: String::new() }` → `Err(MissingField("worker_capability"))`). Fails to compile/fails assertion — no `TryFrom<worker_proto::WorkerCapability>`/`From<...>` impl exists yet.
- [ ] 2.4 GREEN — In `convert.rs`, add the 2 impls per D9: `From<crate::execution::context::WorkerCapability> for worker_proto::WorkerCapability` (wraps `.name()` into `value`) and `TryFrom<worker_proto::WorkerCapability> for crate::execution::context::WorkerCapability` (empty `value` → `Err(ConversionError::MissingField("worker_capability"))`, matching the in-file precedent of collapsing an unset-message case into an existing parameterized variant — no new `ConversionError` variant). Mirrors the `ContentHash` `From`/`TryFrom` pair (`convert.rs:149-163`) in shape.

### Slice C — Wire `WorkerCapability` into `ExecutionContext` (field, constructor, accessor, all call sites)

- [ ] 2.5 RED — Update `context.rs`'s own `sample_context` test helper (`:236-254`) to pass a `WorkerCapability::new("chat.generate")` as an 8th positional argument to `ExecutionContext::new(...)`, and add `execution_context_worker_capability_accessor_returns_the_carried_value_verbatim` asserting `context.worker_capability().name() == "chat.generate"`. Fails to compile — arity mismatch (`ExecutionContext::new` still takes 7 args) and no `worker_capability()` accessor exists.
- [ ] 2.6 GREEN — In `execution/context.rs`: add `worker_capability: WorkerCapability` as the 8th (last) field of `ExecutionContext`, matching wire field order (D10); add it as the 8th positional constructor argument, last; add `#[allow(clippy::too_many_arguments)]` on `ExecutionContext::new` with the design-mandated comment ("Eight is the doc-mandated Execution Context set... not accidental parameter growth"); add `pub const fn worker_capability(&self) -> &WorkerCapability` accessor, mirroring `observability_context()`'s shape. This makes 2.5 pass but breaks every other `ExecutionContext::new(` call site — expected, fixed by 2.7.
- [ ] 2.7 GREEN (mechanical follow-through, same slice) — Update the three remaining call sites so the workspace compiles again: `crates/runtime-worker/tests/port_is_testable_without_infrastructure.rs:210`'s `sample_context`, `runtime/src/worker/in_process.rs:248`'s `context_with` (consumed by its own `sample_context` at `:269`), and `runtime/src/main.rs:46`'s `demo_context` — each gains a `WorkerCapability::new("chat.generate")` (or an equivalent literal) as the 8th constructor argument.
- [ ] 2.8 GREEN — In `crates/runtime-worker/src/lib.rs`, add `WorkerCapability` to the existing `pub use execution::context::{ ExecutionContext, ObservabilityContext, ResolvedDependency, SecurityContext };` re-export list (alphabetical-adjacent, additive only).
- [ ] 2.9 Verify Slice C in isolation: `cargo test -p runtime-worker -p runtime --lib --tests` green; `cargo clippy --all-targets -- -D warnings` clean (confirms the D10 `#[allow]` actually suppresses the lint at 8 arguments).

### Slice D — `ExecutionContext`'s `TryFrom` reads `worker_capability` last (load-bearing ordering)

- [ ] 2.10 RED — In `convert.rs`'s test module, add two tests against the full `worker_proto::ExecutionContext` struct literal (reusing the shape at `:793`, but with `allocation_contract: Some(...)` populated): `execution_context_missing_worker_capability_is_rejected_and_classifies_permanent` (`worker_capability: None` → `Err(MissingField("worker_capability"))`, classifies `Permanent`); `execution_context_empty_worker_capability_is_rejected_and_classifies_permanent` (`worker_capability: Some(WorkerCapability { value: String::new() })` → same `Err`). Also assert the pre-existing `missing_allocation_contract_is_rejected_and_classifies_permanent` (now carrying `worker_capability: None` since Commit 1's 1.7) still asserts `MissingField("allocation_contract")`, not `MissingField("worker_capability")` — this is the regression check for read-ordering. Fails — `ExecutionContext`'s `TryFrom` doesn't read `worker_capability` at all yet, so the domain construction call is missing an argument (compile failure).
- [ ] 2.11 GREEN — In `convert.rs`'s `TryFrom<worker_proto::ExecutionContext> for crate::execution::context::ExecutionContext` (`:290-335`), add the `worker_capability` read as the **last** step in the function body, strictly after the existing `execution_parameters` line (:323) and before the final `Ok(Self::new(...))` call: `let worker_capability = value.worker_capability.ok_or(ConversionError::MissingField("worker_capability"))?.try_into()?;` then thread it as `Self::new(...)`'s 8th argument. **Do not reorder** — placing this before `allocation_contract` flips which `MissingField` variant `:793`'s existing test observes and fails 2.10's regression assertion.
- [ ] 2.12 Verify Slice D: `cargo test -p runtime-worker --lib adapters::grpc::convert` green, all three new/updated assertions from 2.10 pass; `cargo clippy --all-targets -- -D warnings` clean.

### Slice E — Spec-delta merges (mechanical, confirmation-plus-merge)

*The four delta files already exist under `openspec/changes/worker-contract-capability-field/specs/` (written in sdd-spec) and are normative. This slice merges each into its corresponding live `openspec/specs/*/spec.md`, verbatim, at the exact location the delta specifies. No new authoring — copy the delta text in.*

- [ ] 2.13 Merge `specs/worker-inbound-port/spec.md` (ADDED) into `openspec/specs/worker-inbound-port/spec.md`: append the new requirement "ExecutionContext Carries A Mandatory Worker Capability" (with its 2 scenarios) to the `## Requirements` section.
- [ ] 2.14 Merge `specs/worker-wire-contract/spec.md` (MODIFIED) into `openspec/specs/worker-wire-contract/spec.md`: replace the "ExecutionContext Reflects the Full Doc-Mandated Set" requirement text (currently at line 53-55) with the six-member enumeration (adds Worker Capability) and its 3 scenarios (2 existing + 1 new "Worker Capability closes a previously uncontracted gap" + 1 new "Field 8 does not disturb fields 1-7"); update the Mapping Table's `ExecutionContext` row (line 116) and add the new `context.py capability: str -> WorkerCapability` row, per the delta file's exact text.
- [ ] 2.15 Merge `specs/runtime-worker/spec.md` (MODIFIED) into `openspec/specs/runtime-worker/spec.md`: replace the "ExecutionContext Is Immutable Data With No Channel And No Cancellation Field" requirement (currently at line 88) with the delta's extended text (adds the `WorkerCapability` field/accessor/mandatory-8th-arg sentence), preserving all 4 existing scenarios unchanged, and append the 2 new scenarios ("ExecutionContext::new() takes WorkerCapability as a required 8th argument", "WorkerCapability is readable via a public accessor").
- [ ] 2.16 Merge `specs/worker-wire-adapter/spec.md` (ADDED + MODIFIED) into `openspec/specs/worker-wire-adapter/spec.md`: append the new requirement "Worker Capability Field Is Rejected When Missing Or Empty" (3 scenarios) to `## Requirements`; replace "Every Conversion Rejection Is Classified Permanent, Never Silent Or Panicking" (currently at line 81) with the delta's extended enumeration (adds "a missing or empty `worker_capability` field") and its updated scenario list.
- [ ] 2.17 Self-review: diff each merged live spec.md against its delta file's intent — confirm no existing requirement/scenario was accidentally dropped, renamed, or reworded beyond what the delta specifies.

### Slice F — Full-commit gate

- [ ] 2.18 Verify: `cargo fmt --check`; `cargo clippy --workspace --all-targets -- -D warnings` (confirms the D10 `#[allow]` is the only new lint surface and nothing else regresses); `cargo test --workspace`; `shasum -a 256 -c PROTO_MANIFEST.sha256` from `proto/` (still green — Commit 2 touches no proto file); `cargo run -p runtime` still prints a terminal `ExecutionReport` (smoke-level confirmation `demo_context()`'s new 8th argument didn't break the composition root).

---

## Requirement Coverage Map

| Spec / Requirement | Task(s) |
|---|---|
| `worker-inbound-port` — ExecutionContext Carries A Mandatory Worker Capability (both scenarios) | 2.5-2.9, 2.13 |
| `worker-wire-contract` — ExecutionContext Reflects the Full Doc-Mandated Set (all 3 scenarios) + Mapping Table Update | 1.1-1.2, 2.14 |
| `runtime-worker` — ExecutionContext Is Immutable Data... (extended text + 2 new scenarios) | 2.1-2.2, 2.5-2.9, 2.15 |
| `worker-wire-adapter` — Worker Capability Field Is Rejected When Missing Or Empty (3 scenarios) | 2.3-2.4, 2.10-2.11, 2.16 |
| `worker-wire-adapter` — Every Conversion Rejection Is Classified Permanent (extended enumeration) | 2.10-2.11, 2.16 |
| Design D6 (`WorkerCapability` newtype shape, no serde) | 2.1-2.2 |
| Design D7 (proto message + field 8 placement, comment convention) | 1.1-1.2 |
| Design D8 (bidirectional doc/glossary amendment) | 1.5-1.6 |
| Design D9 (reuse `MissingField`, read-last ordering) | 2.3-2.4, 2.10-2.11 |
| Design D10 (8 positional args + narrow `#[allow]`) | 2.6, 2.9, 2.18 |
| Design D11 (two commits one PR; commit-1 literal-fix gotcha) | This document's structure; 1.7-1.8 |

---

## Open Items / Flags For `sdd-apply`

- **2.3's test naming**: the standalone-message rejection test (`worker_capability_rejects_unset_message`) tests `TryFrom<worker_proto::WorkerCapability>` on an *empty-value* message, not a truly absent (`None`) one, since `WorkerCapability` the wire message type has no "unset" state of its own at that level — "unset" only exists one level up, at `ExecutionContext.worker_capability: Option<WorkerCapability>`. That `None` case is exercised in Slice D (2.10), not Slice B. This is a naming/placement choice, not a scope gap — flagging so `sdd-apply` doesn't try to force a `None` test into Slice B where the type doesn't support it.
- **2.14's Mapping Table wording**: the delta spec's exact table markdown is normative; copy it verbatim rather than re-deriving the row text, to avoid an unintentional drift from what `sdd-spec` already committed.
- Design.md's own Open Question ("confirm at review that the D10 `#[allow(clippy::too_many_arguments)]` is acceptable versus raising the workspace threshold") remains unresolved — not a blocker for `sdd-apply`, but a reviewer-facing note to carry into the PR description.
