# Design: Worker Contract — Capability Field On ExecutionContext

## Technical Approach

Additive, compiler-caught, no new dependency. One new wire message (`WorkerCapability`) + one new field (`ExecutionContext.worker_capability = 8`), one Rust newtype in `runtime-worker`'s existing `execution::context` module, one fallible conversion, four constructor call sites. The doc amendment (proposal D3) ships in the contract commit, not after it.

Decision numbering continues this change's **local** scheme (proposal used D1–D5), matching `worker-composition-root`, which restarted local numbering at D1 rather than continuing the global D1–D12 run.

---

## D6 — `WorkerCapability`, declared beside its siblings in `execution/context.rs`

**Choice**: D1 confirmed unchanged — wire `worker_capability`, Rust `WorkerCapability`. No new module: the type lives in `crates/runtime-worker/src/execution/context.rs`, declared after `ObservabilityContext` and before `ExecutionContext`, and is re-exported from `lib.rs:14-16` alongside `ObservabilityContext, ResolvedDependency, SecurityContext`. Shape copied from the **verified real** `ContentHash` (`crates/runtime-primitives/src/content.rs:14-27`) — a tuple newtype, `new(impl Into<String>)`, one `&str` accessor.

```rust
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct WorkerCapability(String);

impl WorkerCapability {
    #[must_use] pub fn new(name: impl Into<String>) -> Self { Self(name.into()) }
    #[must_use] pub fn name(&self) -> &str { &self.0 }
}
```

**Deviation from `ContentHash`, deliberate**: no `Serialize`/`Deserialize`. `runtime-worker/Cargo.toml` has no `serde` dependency and no `execution::context` type derives it; copying those derives would add a dependency the architecture guard's `ALLOWED` matrix would have to be widened for — for nothing.

**Rejected**: a new `execution/capability.rs` module (`ResolvedDependency`, `SecurityContext`, `ObservabilityContext` all already share `context.rs` — a one-type module would break that grouping); `ulid_newtype!` (proposal D2 — a namespaced name is not a ULID).

**Accessor name**: `name()`, not `value()`/`as_str()` — `ContentHash` names its accessor after the concept (`digest()`), not after the storage.

## D7 — Wire shape: message before `ExecutionContext`, field 8 last

`worker.proto` declares dependency messages before dependents (`ResolvedModelRef` → `AllocationContract` → `SecurityContext` → `ObservabilityContext` → `ExecutionContext`). The new message goes at **line 63**, between `ObservabilityContext` (ends :62) and `ExecutionContext` (:64), using this file's comment convention — a `// TypeName — prose` block closed by a `// docs/architecture/...` citation line:

```proto
// WorkerCapability — the behavior one execution requests the Worker
// perform (e.g. "chat.generate"), so a Worker fronting several providers
// can dispatch to the right one. Worker-local by design, NOT in
// primitives/v1/identity.proto: this is Worker-domain vocabulary, not
// cross-domain identity. Deliberately not named `Capability`: that word
// is already bound by 14-resource-model.md to a hardware/platform trait
// (GPU, CUDA, VRAM) that Scheduling filters on — a different concept
// under the same word (GLOSSARY.md:35, :88).
// docs/architecture/18-worker-model.md:52 — Execution Context.
message WorkerCapability {
  string value = 1;
}
```

`value = 1` matches every identity wrapper in `identity.proto` (the converters read `value.value`). The field addition is the last line of the `ExecutionContext` body:

```proto
  WorkerCapability worker_capability = 8;
```

`ExecutionContext`'s own doc block (`:64-72`) enumerates its fields; it gains `..., the requested Worker Capability, and Execution Parameters`.

## D8 — Canon amendment: two docs, both edits bidirectional

**`18-worker-model.md:52`** — insert into the enumeration between `Dependency References (…)` and `Execution Channel`: `Worker Capability,`. Append one sentence to the paragraph:

> Worker Capability names the behavior the execution requests (e.g. `chat.generate`) so a Worker fronting several providers can dispatch to the right one; it is not the hardware/platform Capability of `14-resource-model.md`.

**`GLOSSARY.md`** — the `Configuration Object` / `Deployment Configuration` precedent (:31 and :78) disambiguates **in both directions**. Follow it exactly:

- New row after :46 (`Execution Context`), keeping Worker Model rows contiguous:
  `| Worker Capability | `18-worker-model.md` | Worker Model | The behavior an Execution Context requests the Worker perform (e.g. `chat.generate`) — distinct from a Capability (`14-resource-model.md`). |`
- Amend :35 to close the loop: `… (GPU, CUDA, VRAM, …) — distinct from a Worker Capability (`18-worker-model.md`).`

A one-way row would leave a reader at :35 still unwarned — the very defect `GLOSSARY.md:88` names.

## D9 — Rejection reuses `MissingField`, and is read **last**

**Choice**: no new `ConversionError` variant. Both an unset message and a present-but-empty `value` produce `ConversionError::MissingField("worker_capability")`.

```rust
impl TryFrom<worker_proto::WorkerCapability> for crate::execution::context::WorkerCapability {
    type Error = ConversionError;
    fn try_from(value: worker_proto::WorkerCapability) -> Result<Self, Self::Error> {
        if value.value.is_empty() { return Err(ConversionError::MissingField("worker_capability")); }
        Ok(Self::new(value.value))
    }
}
```

In `ExecutionContext`'s `TryFrom` (`convert.rs:290`) this is the exact `.ok_or(MissingField(..))?.try_into()?` shape already used for `allocation_contract`, `object_id`, `content_hash`.

**Rationale**: `MissingField` is already the parameterized "required thing absent" variant and already classifies `Permanent`. Collapsing empty-into-missing has in-file precedent — `execution_phase_from_i32` (:238) collapses an unrecognized discriminant into the same rejection as tag-zero. A dedicated `EmptyWorkerCapability` variant would add a `Display` arm, a `Classify` arm, and an entry in `every_conversion_error_variant_classifies_permanent` (:750) to say nothing new.

**Load-bearing ordering**: the `worker_capability` read goes **after** `execution_parameters`, i.e. last in the function body. The existing test at `convert.rs:791-819` asserts `MissingField("allocation_contract")` on a context that will now also lack a capability; reading capability first would flip that assertion and force unrelated test churn.

## D10 — Eight positional args + one narrow `allow` (build-breaking gotcha)

`ExecutionContext::new` goes 7 → 8 positional parameters, new arg **last**, mirroring wire field order. No builder.

**Gotcha, verified**: `clippy::too_many_arguments` is warn-by-default with a threshold of **7**, and this workspace declares no `clippy.toml` and no `[workspace.lints.clippy]` (`Cargo.toml:53-55` sets only `rust` lints). The success criterion `cargo clippy --all-targets -- -D warnings` therefore **fails at 8 arguments**. Mitigation:

```rust
// Eight is the doc-mandated Execution Context set (18-worker-model.md:52),
// not accidental parameter growth; this value is complete-on-construction.
#[allow(clippy::too_many_arguments)]
#[must_use]
pub fn new(...) -> Self
```

**Alternatives rejected**:

| Option | Why rejected |
|---|---|
| Builder / `with_worker_capability` | Makes a partially-built `ExecutionContext` representable, contradicting `runtime-worker/spec.md:88` "ExecutionContext Is Immutable Data" and `worker-inbound-port`'s "constructible from plain values". Zero builder precedent exists in this workspace — the only `with_*` in the tree is a test helper (`port_is_testable_without_infrastructure.rs:107`) |
| `clippy.toml` with `too-many-arguments-threshold = 8` | Global relaxation for a local problem |
| Params struct | Same arity moved one level down; churns all 4 call sites harder |

The narrow, commented `#[allow]` on one item follows this crate's own established habit — `convert.rs:451-457`'s `#[allow(dead_code)]`, explicitly scoped to a single item "not at module scope".

## D11 — Two commits, one PR

`proto/`, `tibios-core/`, and `tibios-ray/` are sibling directories in **one** git repo, so the umbrella edit and the vendored re-copy genuinely fit in one commit (proposal Rollback Plan is mechanically feasible).

**Gotcha**: commit 1 does not compile on its own as the proposal implies. `prost` regenerates `worker_proto::ExecutionContext` with a new public field, and the struct literal at `convert.rs:793` immediately fails `E0063`. Since this project's norm is per-slice green (`worker-composition-root/design.md`: "Each slice compiles, tests, and reverts independently"), **commit 1 must include the one-line `worker_capability: None,` addition to that literal.** With D9's read-last ordering, that test's assertion is unchanged and stays green.

| Commit | Contents | ~lines |
|---|---|---|
| 1 — contract + canon | umbrella `.proto`, vendored `.proto`, `PROTO_MANIFEST.sha256`, `18-worker-model.md`, `GLOSSARY.md`, the one-line test-literal fix | ~45 |
| 2 — domain + adapter | `context.rs` (newtype, field, arg, accessor, unit tests), `lib.rs` re-export, `convert.rs` (2 impls + 3 tests), 3 call sites, 4 spec deltas | ~150 |

**Review Workload Forecast** — 400-line budget risk: **Low** (~195 changed lines). Chained PRs recommended: **No**. Recommendation for `sdd-tasks`: **one PR, two work-unit commits**. The standing `auto-chain` preference targets oversized work; splitting ~195 lines into two PRs would ship a contract change reviewable only against a doc that has not landed yet, which is exactly what proposal D3 forbids.

---

## Data Flow

```
umbrella proto/tibios/worker/v1/worker.proto   (source of truth)
   │ cp (manual ritual, proto/README.md)
   ▼
tibios-core/proto/… + PROTO_MANIFEST.sha256 ──> proto_drift.rs / shasum -c
   │ build.rs (tonic-build)
   ▼
worker_proto::ExecutionContext { …, worker_capability: Option<WorkerCapability> }
   │ TryFrom  (convert.rs:290, capability read LAST)
   │   None | value=="" ──> Err(MissingField("worker_capability"))  [Permanent]
   ▼
runtime_worker::ExecutionContext { …, worker_capability: WorkerCapability }
   │ .worker_capability() -> &WorkerCapability
   ▼
WorkerService::execute  (dispatch is a FUTURE change — out of scope)
```

## File Changes

| File | Action | Description |
|---|---|---|
| `../proto/tibios/worker/v1/worker.proto` | Modify | D7: message at :63, field 8, `ExecutionContext` doc block |
| `proto/tibios/worker/v1/worker.proto` | Modify | Byte-identical re-vendor |
| `proto/PROTO_MANIFEST.sha256` | Modify | Regenerated digest (`fd -e proto -t f . \| sort \| xargs shasum -a 256`) |
| `docs/architecture/18-worker-model.md` | Modify | D8 — line 52 enumeration + one sentence |
| `docs/architecture/GLOSSARY.md` | Modify | D8 — new Worker Model row + amend :35 |
| `crates/runtime-worker/src/execution/context.rs` | Modify | D6 newtype; field, 8th arg, `const fn worker_capability()`; unit tests |
| `crates/runtime-worker/src/lib.rs` | Modify | Re-export `WorkerCapability` |
| `crates/runtime-worker/src/adapters/grpc/convert.rs` | Modify | D9 — 2 impls; test literal :793; 3 new tests |
| `crates/runtime-worker/tests/port_is_testable_without_infrastructure.rs` | Modify | `sample_context()` :210 |
| `runtime/src/worker/in_process.rs` | Modify | Call site :258 |
| `runtime/src/main.rs` | Modify | `demo_context()` :46 |
| `openspec/specs/{worker-inbound-port,worker-wire-contract,runtime-worker,worker-wire-adapter}/spec.md` | Modify | Delta specs (owned by `sdd-spec`) |

`rg`-confirmed: exactly 4 `ExecutionContext::new(` sites — the 3 above plus `context.rs:245`'s own test helper.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit — `context.rs` | `WorkerCapability::new`/`name()` round-trip; `worker_capability()` returns the carried value verbatim | `#[cfg(test)] mod tests`, extend `sample_context` |
| Unit — `convert.rs` | Valid capability converts; **unset** message rejected as `MissingField("worker_capability")`, classifies `Permanent`; **empty `value`** rejected identically | Mirror `missing_allocation_contract_is_rejected_and_classifies_permanent` (:791) |
| Regression — `convert.rs` | `:791` still asserts `MissingField("allocation_contract")` after the literal gains `worker_capability: None` | Proves D9's read-last ordering |
| Integration | Port stays constructible with no infrastructure at 8 args | `port_is_testable_without_infrastructure.rs` compiles + passes |
| Contract | `shasum -a 256 -c PROTO_MANIFEST.sha256`; `proto_drift.rs` green vs. umbrella | Existing tests, unchanged |
| Lint | `cargo clippy --all-targets -- -D warnings` clean **with** the D10 `allow` | CI command |

## Migration / Rollout

No data migration — nothing persists an `ExecutionContext`, and no live peer consumes field 8 (`tibios-ray`'s server is a stub). Rollback = revert both commits; the 7-field message and 7-arg constructor return exactly. Hard follow-up, not a blocker: a `tibios-ray` change wiring `context.py:67`'s already-invented `capability: str` onto the now-contractual `worker_capability`.

## Open Questions

- [ ] None blocking. Confirm at review that the D10 `#[allow(clippy::too_many_arguments)]` is acceptable versus raising the workspace threshold — the design's position is the narrow, commented allow.
