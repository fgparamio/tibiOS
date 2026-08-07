# Exploration: runtime-object Data Family (Taxonomy + Domain Objects)

## Current State

`runtime-object` is a stub (`crates/runtime-object/src/lib.rs`, 3 lines, no public traits), depending only on `runtime-primitives`. Identity primitives it will build on **already exist and are tested** in `runtime-primitives`:

- `ObjectId` (ULID newtype, `identity.rs:94`)
- `ObjectVersion` (`u64` counter, `initial()`/`next()`, `identity.rs:129`)
- `ContentHash` (opaque algorithm-qualified digest string, `content.rs:14`)

So the user's originally-proposed "Slice 1: Identity" is already done — no work needed there. This change starts at Taxonomy + Domain Objects.

## Affected Areas

- `crates/runtime-object/src/lib.rs` — currently a stub; will gain `ObjectType`, `ObjectLifecycle`, `LogicalObject`, `ContentObject`
- `openspec/specs/runtime-object/spec.md` — currently "stub, no public traits"; will need a MODIFIED requirement replacing the stub constraint
- `docs/architecture/13-object-model.md` — source of truth for the taxonomy and the three-kind-of-object model

## Key Question 1: Does ContentHash identity allow many-to-one sharing?

**Yes — and this must be crystallized as an explicit invariant, not left implicit.**

Evidence:
- `13-object-model.md`'s own definition: "A Content Object is immutable content addressed by a `ContentHash`... it never changes once created." Content-addressing's entire value proposition (same precedent as Git blobs, container image layers, IPFS) is that identical bytes produce identical hashes regardless of which named ref points at them.
- Nothing in the doc scopes a `ContentHash` to a single owning `LogicalObject`. The "Model Reference" example even shows one `LogicalObject` (`ObjectId`) pointing to *different* hashes across versions — the inverse relationship (many `LogicalObject`s → one hash) is the natural dual case and is never prohibited.
- Consequence for the data model: `ContentObject` MUST NOT carry a back-reference to "its" `LogicalObject` (no owner-pointer field) — the reference direction is strictly `LogicalObject → ContentHash`, never the reverse. This is also why Content Objects are described as forming their own graph, independent of Logical Object identity.

This becomes a REQUIRED spec invariant: `LogicalObject`↔`ContentObject` is many-to-one/many-to-many, never one-to-one, and `ContentObject` has no knowledge of which `LogicalObject`(s) reference it.

## Key Question 2: Lifecycle — persistent? observable? forbidden transitions? transition ownership?

| Question | Answer | Source |
|---|---|---|
| All 8 states persistent? | Yes — every transition is an authoritative fact appended to that Object's own **Object Lifecycle Log** (per-aggregate event stream, `21-runtime-storage-engine.md:45`). Current state is a *rebuildable projection*, never separately stored (`13-object-model.md`'s Persistence section, `21-runtime-storage-engine.md:51`). | `21-runtime-storage-engine.md`, `13-object-model.md` |
| All 8 observable? | Yes — `13-object-model.md`'s Observability section explicitly lists "lifecycle" among what every Object exposes. | `13-object-model.md:176-178` |
| Forbidden transitions? | **Not specified anywhere.** The diagram (`13-object-model.md:73-96`) reads top-to-bottom but never states whether steps can be skipped, reversed, or re-entered (e.g. can `Archived` return to `Available`? can `Deleted` be reached directly from `Registered`?). **Open — must be decided in spec, not inferred.** | none found |
| Who owns each transition? | **Not specified.** `13-object-model.md` defines Object *ownership* (one logical owner per Object) but never says which Runtime domain/actor is authorized to *drive* a given lifecycle transition (e.g. does `runtime-object` itself own `Created`→`Validated`, does `runtime-storage` confirm `Registered`, does a consumer trigger `Referenced`?). **Open — must be decided in spec.** | none found |

These two "open" rows are exactly the invariants the user asked to freeze before writing code. Recommend resolving them explicitly in the proposal/spec phase rather than guessing — options to weigh: (a) a strict linear state machine mirroring the diagram literally (no skips, no reversals except a documented exception set), vs (b) a partial-order/guard-based model where only certain edges are legal and `runtime-object` owns transition validation centrally regardless of which domain requests it.

## Approaches (for the Taxonomy + Domain Objects data family itself)

1. **Plain enums/structs, no trait, mirroring `runtime-allocation`'s `AllocationContract` precedent** — `ObjectType` as a closed enum (10 variants per the doc), `ObjectLifecycle` as a closed enum (8 states, no `Default`, same pattern as `ExecutionPhase` in `runtime-worker` which also has no `Unspecified`/`Default`), `LogicalObject`/`ContentObject` as plain immutable structs.
   - Pros: consistent with two already-established precedents (`AllocationContract`, `ExecutionContext`/`ExecutionPhase`); trivially testable without async/transport.
   - Cons: none identified — this is the only approach used elsewhere in the codebase for a "data family" phase.
   - Effort: Low.

2. **Guarded state machine with a `transition()` method enforcing legality** — bakes the (currently undecided) transition rules into `ObjectLifecycle` itself.
   - Pros: makes illegal transitions unrepresentable.
   - Cons: premature — the legal-transition set isn't decided yet (Key Question 2); would force that decision inside this same change instead of the dedicated spec/design step. Also starts to smell like a Port/behavior, which the user explicitly wants deferred to Slice "Ports".
   - Effort: Medium.

## Recommendation

Approach 1, matching the `AllocationContract`/`ExecutionContext` precedent. Resolve Key Questions 1 and 2 as explicit spec requirements (with scenarios) rather than silently encoding a guess into the type — Question 1 has a clear answer (many-to-one allowed) and can be a hard invariant; Question 2 needs an explicit decision recorded in the proposal/spec, not inferred here.

## Risks

- Guessing at the legal-transition set for `ObjectLifecycle` without deciding it explicitly risks baking in an assumption that later needs a breaking MODIFIED spec (same cost the user is trying to avoid).
- `ObjectType`'s list ("Workload, Message, Actor, Service, Dataset, Tensor, Checkpoint, Configuration, Artifact, Model" per `13-object-model.md:102`, plus "Future object types may be added without modifying existing ones") signals this enum should probably NOT be declared `#[non_exhaustive]`-closed forever — but the doc also doesn't define an extension mechanism yet. Worth a design-phase decision: closed enum now (simplest, matches `ExecutionEvent`'s six-arm precedent) vs. deliberately open for future growth.

## Ready for Proposal

Yes. Scope: `ObjectType`, `ObjectLifecycle`, `LogicalObject`, `ContentObject` in `runtime-object`, no ports/store/persistence. Two open questions (legal lifecycle transitions, transition ownership) must be resolved as explicit decisions during proposal/spec — not deferred as ambiguity.
