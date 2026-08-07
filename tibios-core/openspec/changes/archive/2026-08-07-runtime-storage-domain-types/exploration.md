# Exploration: runtime-storage Data Family (Authoritative Event Stream Primitives)

## Current State

`runtime-storage` is a 3-line stub (`crates/runtime-storage/src/lib.rs`), depending only on `runtime-primitives`. Its stub spec (`openspec/specs/runtime-storage/spec.md`) mirrors what `runtime-object`'s stub spec used to say: exact dependency set = `runtime-primitives`, no public traits.

`docs/architecture/21-runtime-storage-engine.md` is a **principles-level doc, not a data-contract doc**. It defines four Storage Domains built on three mechanisms:

- **Content Store** — immutable, hash-addressed (Model Artifacts, Dataset Chunks, Binaries), content-addressing dedupes for free
- **Authoritative Event Streams** — one independently-ordered append-only stream per mutable aggregate (Admission, Trust, Allocation, **Object Lifecycle**, Checkpoint Lifecycle, ...) — explicitly *not* one global log (`21-runtime-storage-engine.md:23,60-65`)
- **Snapshot Store** — observational only, for replay/simulation/debugging, **never used for recovery**
- **Report Store** — immutable terminal facts (Execution Reports), no projection, no re-evaluation

No concrete Rust types are defined anywhere in this doc — no `ObjectLifecycleEvent` struct, no `Sequence`/timestamp/actor field names. It stays at the mechanism/principle level.

## Affected Areas

- `crates/runtime-storage/src/lib.rs` — currently a stub; will gain generic event-stream primitives
- `openspec/specs/runtime-storage/spec.md` — currently "stub, no public traits, deps = runtime-primitives only"; needs a MODIFIED requirement
- `docs/architecture/21-runtime-storage-engine.md` — primary source of truth for this domain
- `docs/architecture/23-object-store.md` — turned out to be equally essential (see Key Question 1 below); defines the ownership boundary between Object Store, `runtime-object`, and `runtime-storage`
- `docs/architecture/13-object-model.md:170` — corroborates the log-is-authority model from the Object Model side

## Key Question 1: Which of Q1/Q2/Q3 (from `runtime-object`'s Open Questions) does this domain resolve?

**Q2 (transition ownership) is ANSWERED — but not by `runtime-storage`.** `docs/architecture/23-object-store.md:174-180`:

> "The Object Store does not own Object Lifecycle. Lifecycle transitions originate in `runtime-object`. Whenever lifecycle changes occur, Object Store updates lookup structures accordingly. The authoritative source remains the Object Lifecycle Log (`21-runtime-storage-engine.md`)."

And the doc's own closing principles (`23-object-store.md:308-310`): "Every domain owns the services that speak its language. Storage owns durability. The Object Store owns resolution." Combined with `21-runtime-storage-engine.md`'s own Responsibilities section ("Storage Engine never... interprets business semantics" / "Storage owns durability; Runtime owns meaning"), this is unambiguous: **`runtime-object` owns and validates lifecycle transitions. `runtime-storage` is a pure fact-recording mechanism — ordered append, atomic commit, durability, replay — with no authority to accept or reject a transition as legal.**

**Q1 (legal transitions) — STILL OPEN.** Neither doc defines a transition table or addresses skip/reversal. `13-object-model.md:73-96`'s lifecycle diagram is illustrative (one linear path), not a formal state machine — this was already the finding when `runtime-object` recorded Q1 as open, and nothing in the storage docs adds a transition table.

**Q3 (monotonic progression) — STILL OPEN.** No doc anywhere discusses whether a state can recur after later states occurred.

**Correction to the working hypothesis**: the user's hypothesis was that `runtime-storage` itself validates and rejects illegal transitions. The docs say the opposite — validation belongs to `runtime-object`, which hasn't defined its rules yet either (that's exactly why Q1/Q3 are still open). `runtime-storage`'s job is strictly narrower: durably record whatever authoritative fact `runtime-object` decides to append, in order, per-Object.

## Key Question 2: Is the Object Lifecycle Log the authority, or a projection of something else?

**CONFIRMED: log-is-authority, current-state-is-projection. Not ambiguous — three independent docs agree verbatim:**

- `13-object-model.md:170`: "A Logical Object's current state is a rebuildable projection of its Object Lifecycle Log — not a separately-persisted 'metadata store'."
- `21-runtime-storage-engine.md:49-51` ("Why Metadata Store Disappeared"): an earlier draft had a separate Metadata Store for Logical Object metadata; it was removed as redundant, because "logical state evolves through new facts" — current metadata is simply the rebuildable projection of the Object Lifecycle Log, "exactly the same mechanism as Admission Log → Quota Projection or Trust Log → Trusted Node Set."
- `23-object-store.md:180`: "The authoritative source remains the Object Lifecycle Log."

One nuance for the design phase: `21-runtime-storage-engine.md:101` ("Conceptual Model vs Implementation") explicitly says not every aggregate needs a *literal* explicit event-sourced stream — an equivalent internal mechanism is acceptable as long as it preserves the same guarantees (per-consistency-domain ordering, durability, reconstruction, auditability). So "log-is-authority" is a hard conceptual invariant; "literal append-only event stream" is one conforming implementation, not the only one.

## Key Question 3: Dependency direction — does `runtime-storage` depend on `runtime-object`?

**No — and the current stub (deps = `runtime-primitives` only) is already correct for this slice.** `runtime-storage` is explicitly infrastructure-neutral (`21-runtime-storage-engine.md:11-13`: "It is not a database, it is not the Object Store — it is the infrastructure-neutral persistence layer that domain-specific services... are built on top of"). The Object Lifecycle Log is one instance of a generic per-aggregate event stream mechanism that also serves Admission, Trust, Allocation, and Checkpoint Lifecycle — none of which are `runtime-object` concerns. Coupling `runtime-storage` to `ObjectLifecycle`/`LogicalObject` types would invert the actual dependency: `runtime-object` (or a future composition point) depends on `runtime-storage`'s generic stream primitives, never the reverse. This corrects the user's originally-proposed chain shape slightly: the arrow between the two crates points `runtime-object → runtime-storage`, not the other way, and `runtime-storage`'s Slice 1 has no reason to add `runtime-object` as a dependency at all.

## Approaches

1. **Generic, domain-agnostic event-stream primitives (recommended)** — Slice 1 defines types like a `Sequence`/version-per-stream newtype and a stream/consistency-domain identifier, with no Object-specific payload. Mirrors `runtime-object`'s "Identity" precedent (`ObjectVersion` already exists as exactly this kind of generic counter in `runtime-primitives`).
   - Pros: matches the documented dependency direction and "Storage owns durability, Runtime owns meaning" principle exactly; unblocks Admission/Trust/Allocation/Object Lifecycle streams identically later, no premature coupling to `runtime-object`.
   - Cons: defers a concrete `ObjectLifecycleEvent` shape to a future `runtime-object`-side (or composition-root-side) change — slower to reach an end-to-end Object persistence story.
   - Effort: Low.

2. **Object-typed event log now** — define `ObjectLifecycleEvent` directly in `runtime-storage` using `runtime-object`'s `ObjectLifecycle`/`ObjectId`/`ObjectVersion`.
   - Pros: faster path to a usable Object Lifecycle Log end-to-end.
   - Cons: directly contradicts `23-object-store.md`'s documented ownership model (transitions originate in `runtime-object`, not `runtime-storage`); couples a generic infrastructure crate to one specific domain's enum; forces re-litigating Q1/Q3 as a side effect instead of a deliberate decision.
   - Effort: Medium, plus real architectural rework risk later.

## Recommendation

Approach 1. It's the only option consistent with `23-object-store.md`'s explicit ownership diagram and the "Storage owns durability, Runtime owns meaning" principle repeated in both `21-runtime-storage-engine.md` and `00-philosophy.md`.

**Recommended phased slice roadmap** (shape earned from the docs, not copied from `runtime-object`):

- **Slice 1 — Stream primitives**: generic, domain-agnostic data types only (e.g. a `Sequence` newtype for per-stream ordering, a stream/consistency-domain identifier type). No ports, no backend, no Object-specific payload. Deps stay `runtime-primitives`-only.
- **Slice 2 — Append/Replay ports**: generic, backend-agnostic traits (`append`, `replay`/`read`) parameterized over an opaque fact/payload type — still no concrete backend, still no coupling to any specific domain's event shape.
- **Slice 3 — A concrete backend** (in-memory first, matching the project's established "in-memory before real backend" pattern from `runtime-worker`). Content Store (hash-addressed, `ContentHash`-keyed) is a related but distinct mechanism from the event streams and may warrant its own parallel or later slice rather than being folded into Slice 1-3.
- Snapshot Store and Report Store are architecturally distinct mechanisms (no-replay-for-recovery, no-projection respectively) — out of scope for this initial roadmap, revisit only if a concrete need arises.

Q1 and Q3 remain genuinely open after reading every doc in scope for this domain — this change should defer them explicitly (same discipline as `runtime-object`'s `ObjectLifecycle` shipping without `Default`/`transition`/`validate`), not attempt to resolve them as a side effect of adding storage types.

## Risks

- If a future change defines `ObjectLifecycleEvent` inside `runtime-object` (the documented-correct location) before `runtime-storage`'s generic primitives exist, there's a risk of it being defined ad hoc without the `Sequence`/ordering vocabulary this change should establish first — worth sequencing deliberately.
- `21-runtime-storage-engine.md:101`'s "equivalent internal mechanism" escape hatch means Slice 3's concrete backend has some latitude in literal implementation; worth pinning down in the design phase so it doesn't quietly drift from "same guarantees" into something weaker.

## Ready for Proposal

Yes — Slice 1 (generic stream primitives, `runtime-primitives`-only deps, Q1/Q3 explicitly deferred, Q2 recorded as answered-elsewhere with a citation). One correction to flag to the user before drafting the proposal: the dependency arrow is `runtime-object → runtime-storage`, not the reverse, so this slice does **not** add `runtime-object` as a dependency.
