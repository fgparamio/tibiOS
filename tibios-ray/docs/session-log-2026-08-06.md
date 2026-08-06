# tibios-ray — Session Log, 2026-08-06

A working session covering the full bootstrap of `tibios-ray`'s architecture and its first three Spec-Driven Development (SDD) phases, done in close coordination with a parallel session working on `tibios-core`.

## 1. Starting context

The session opened by confirming shared context with a sibling `tibios-core` (Rust) session: `tibios-core` is the distributed-OS control plane, already at `architecture-v1.0` (frozen). `tibios-ray` is one of two Worker implementations for its Runtime — the heavy AI execution path, reached over gRPC (`local-infer`, in-process via llama.cpp, is the other). At session start, `tibios-ray` was a bare skeleton: one `pyproject.toml` with a single dependency (`ray`), and `src/tibios_ray/__init__.py` containing only `print("Hello from tibios-ray!")`.

Two architecture documents from `tibios-core` anchored everything that followed:
- `18-worker-model.md` — the Worker Contract itself (Execution Context, Channel, Events, Report, Pulse, cancellation, the four execution patterns).
- `25-ai-runtime.md` — confirms AI gets no special Runtime treatment: `local-infer` and `tibios-ray` are interchangeable Workers, chosen only by Scheduling's generic Capability Filter matching advertised capability against requirement. No AI-specific routing component may ever exist.

## 2. The functional map — capability-first design

Before any code, a long design conversation established the *shape* of tibios-ray's problem space, deliberately in terms of **capabilities, not concrete models** (so the design survives years of model churn):

- Workers should be organized by capability (`chat.generate`, `embedding.generate`, `rerank.documents`, `vision.understand`, `speech.transcribe`/`speech.synthesize`, `ocr.extract`), each advertising a *catalog* of supported model families/backends/flags instead of a hardcoded model list.
- Six official Workers were scoped for the MVP: Chat, Embedding, Reranker, Vision, Speech, OCR.
- Six strategic model families for Chat: Qwen, Llama, DeepSeek, Gemma, Mistral, Kimi.
- **The `local-infer` vs `tibios-ray` boundary must never be a hardcoded rule** (e.g. "small models locally, big ones remote") — it has to emerge purely from advertised capabilities/resources matched generically by the Scheduler. This was independently re-derived and confirmed multiple times throughout the session, and a permanent test now guards it.

### The terminology fight that mattered

A proposed "AI Convenience Library" / `Profile` concept (e.g. `Profile::Developer` resolving to `family: deepseek, reasoning: true`) was worked through in detail and ultimately rejected from tibios-ray's scope entirely: `27-sdk.md` establishes the generic TibiOS SDK projects the Runtime API 1:1 with **zero domain logic** — a `Profile` resolving intent to model preferences is domain logic, so it can never live in the SDK, and by extension never in tibios-ray (which sits on the opposite, provider side of the boundary). It belongs in a future, separate `Application → AI Convenience Library → TibiOS SDK → Runtime API` layer, out of scope here.

A second, more consequential naming fight: an earlier, independent `python-foundation` proposal had already reserved the word **"Worker"** exclusively for the gRPC Worker Contract entity, forbidding it from being reused for internal capability-dispatch units. Three candidate names were debated for those internal units — "Capability Handler" (rejected: implies a callback/endpoint, too small), "Model Family Adapter" (rejected: implies one unit per family, but a unit can serve several families) — and **"Capability Provider"** was chosen. `WorkerRuntime` was carved out as the *one* sanctioned exception, since it's the thing that directly drives the Worker Contract lifecycle. This rule became binding and is enforced by a permanent AST-based test (`test_naming_audit.py`) from that point forward.

## 3. Phase 1 — `ray-worker-runtime` (Foundation)

Scope: define, as interfaces only (no implementations), the four foundational concepts behind the Worker boundary — Worker Runtime, Capability Registry, Model Selection Policy, Backend Adapter.

Full SDD cycle: `sdd-propose` → `sdd-spec` + `sdd-design` (parallel) → `sdd-tasks` → `sdd-apply` × 7 chained PR slices → `sdd-verify` → fix findings → `sdd-archive`.

**Key design decisions (D1–D7), all still binding today:**
1. `typing.Protocol` everywhere, no base classes — structural typing, zero coupling from Providers/Adapters back to the framework.
2. `ObjectId`/`ContentHash`/etc. are **frozen dataclasses, never `NewType[str]`** — this is what makes model resolution *proof-carrying*: `NewType` is a runtime no-op, so `ObjectId("deepseek")` would type-check fine; a dataclass requiring a real `ContentHash` cannot be forged from a bare string.
3. No unified `BackendAdapter.infer()` — per-modality protocols (Text/Embedding/Rerank/Transcription) instead, since forcing everything into one signature would degrade to `dict[str, Any]` payloads.
4. Cooperative cancellation via a `CancellationToken`, never raw `asyncio.CancelledError` (which would skip the required acknowledge→cleanup→final-events→report sequence).
5. `CapabilityRegistry` is immutable, built once at the composition root from an explicit provider sequence — no `register()` mutation, no auto-discovery.
6. `ExecutionEvent` is a closed, exhaustive tagged union (`OutputChunk | Progress | Warning | CheckpointCreated | MetricsSnapshot | EndOfStream`).
7. **`ModelSelectionPolicy.plan()` accepts only an already-resolved `ResolvedModelRef`, never a bare model/family string** — picking *which* model is scheduling-time discovery, explicitly forbidden for Workers by `18-worker-model.md`. This is enforced by a pyright fixture (`reportUnnecessaryTypeIgnoreComment`) proving the guard is structural, not just documented.

A late finding during design: `Inference Intent` (an intent-enum layer between capability and policy) was explicitly considered and rejected for this phase via a simple YAGNI test — "can the system work without it? Yes." — and recorded as a **Deferred Design** section rather than left as a vague open question.

`sdd-verify` found 0 CRITICAL / 3 WARNING (fixed the two cheap ones: a stale spec sentence, a missing permanent anti-`local-infer`-routing test with mutation-test proof it actually catches violations; acknowledged the third — squashed git commits not proving RED-before-GREEN — as unfixable without fabricating history). Archived clean.

## 4. Git chaos, and how it got fixed

Around this point, real friction appeared from working in a **shared git checkout** while a parallel tibios-core session was active in the same directory:
- Background `sdd-apply` agents committed Phase 1's work directly onto whatever branch happened to be checked out — which turned out to be `tibios-core/workspace-foundation-pr3`, a tibios-core PR branch, mixing unrelated repos' commits together.
- A follow-up attempt to fix this by creating dedicated branches made things *worse* temporarily: because both sessions share one working tree and one `HEAD`, whichever branch either session leaves checked out is the one that silently receives the *other* session's next commit too. A tibios-core commit (`bccf2bb`, a Rust "composition root" commit) landed on a brand-new tibios-ray-only branch by pure accident of timing.
- The user's call, once the risk was understood: **"trabajemos con la misma rama"** — stop fighting it, just merge everything onto one branch and push. This was executed (fast-forward `main` to the unified tip, push).
- The durable fix, adopted from that point on: **`EnterWorktree`/`ExitWorktree`** for every new SDD change. Each change gets its own isolated worktree under `.claude/worktrees/<name>/`, so the two sessions never share a checked-out branch again. This held for the rest of the session with zero further collisions.

A structural quirk of the resulting worktrees, discovered the hard way: because `tibios-ray` now lives inside a `tibios` monorepo (also discovered mid-session — the sibling repos had been merged into one monorepo, `github.com/fgparamio/tibiOS`, by the user in another terminal), a worktree's root contains **both** `tibios-core/` and `tibios-ray/` as siblings — not `tibios-ray`'s content directly. An early `sdd-propose` agent got confused by this and wrote its output to a stray `openspec/` folder at the worktree root; every subsequent agent launch explicitly warned about this path structure and it did not recur.

A second recurring mechanical issue: **`sdd-propose`/`sdd-spec`/`sdd-design`/`sdd-archive` subagents have no Bash tool**, so they cannot run `git commit` themselves — several of them left proposal/spec/design files sitting uncommitted, and `sdd-archive` specifically tended to *copy* the change folder into `archive/` instead of `git mv`-ing it, leaving a duplicate. Both had to be caught and fixed manually (diff-verify identical, delete the duplicate, commit) after essentially every phase's propose/spec/design/archive step for the rest of the session.

Also discovered mid-session: an earlier claim that `mem_save` (the Engram memory tool) couldn't target a specific project explicitly was **wrong** — it does accept a `project` parameter, just untested the first time. Several memories that had been mis-filed under the wrong auto-detected project name ("tibios" instead of "tibios-ray") were re-saved correctly once this was found.

## 5. Phase 2 — `capability-providers`

Scope: implement the six Capability Provider modules (seven registrable classes — `speech.py` holds two, since `CapabilityDescriptor.capability` is singular) as real, correct catalogs with no real inference wired in yet.

Same full SDD cycle, 7 chained PR slices. Notable design decisions:
- **`execute()` raises `NoBackendAvailableError` rather than faking a completed report** — explicitly chosen over "delegate to a backend if one exists, else raise," because vision/OCR/speech-synthesis have no backend protocol defined yet at all (that's Phase 4); inventing three just to have something to delegate to was rejected as scope creep.
- Providers are **zero-field, frozen, slotted dataclasses** — this doubles as a mechanical guarantee that they hold no backend reference, later reinforced by a dedicated mutation-tested regression test added post-verify.
- The **FLC (Family Label Convention)** was established for `ModelFamily` labels: a pure, context-free function of a model's *published lineage name* — strip org/version/size/quant/tuning-stage/locale tokens, keep everything else. Verified against 20 real model names before being trusted. Two genuinely tricky findings: `paddleocr` must stay `paddleocr` (a naive "strip everything" rule would wrongly collapse it to `paddle`, a framework name, not a lineage), and `gemma` legitimately appears under **both** `chat.generate` and `vision.understand` — Google publishes no distinct "Gemma Vision" lineage, since Gemma 3 is natively multimodal — confirmed correct at every subsequent phase that touched it, never accidentally deduplicated.

`sdd-verify` found 0 CRITICAL / 2 WARNING (fixed the missing zero-fields guard with a live mutation test; acknowledged the same squashed-commit-history limitation as unfixable). This is also where the user set a new standing rule: **"Siempre ataquemos los Warnings"** — always fix WARNING-level verify findings before archiving, not just CRITICALs. Archived clean.

## 6. Phase 3 — `model-catalog`

Scope: real per-model reference data — concrete published model names, versions, context windows, minimum VRAM, backend/quantization compatibility — one layer more granular than the family-level catalogs Phase 2 built.

This phase explicitly, deliberately did **not** attempt to solve the still-open cross-repo blocker (see §7): no catalog type may carry or produce a `ResolvedModelRef`/`ObjectId`, and the catalog has **zero production callers** in this change — it's real, tested, internally-consistent data, inert until the Object Store resolution path exists on the tibios-core side.

8 chained PR slices (types+FLC / query-surface, split into 2a/2b when it ran over budget / Chat A / Chat B / Embedding+Rerank / Vision / Speech+OCR / final assembly+consistency harness), reaching 722 passing tests. Highlights:
- The FLC function was promoted from a test-only regex (Phase 2) to real production code, with its full four-phase algorithm worked out in design (org-prefix strip → tokenise with an alpha→digit boundary rule → unconditional drop table → head rule) — verified to correctly distinguish `e5` (keep) from `m3` (drop), two strings identical in shape, separable only by *position* in the token list.
- Two real, correctly-formed published model names were found to be **excluded from the catalog by deliberate curatorial choice**, not because the FLC function fails on them (it doesn't) — `meta-llama/Meta-Llama-3.1-8B-Instruct` and `deepseek-ai/DeepSeek-R1-Distill-Qwen-32B` derive cleanly but weren't included as data. `sdd-verify` caught and corrected a wrong assumption in the audit brief that these were *un*derivable.
- A genuine contradiction in the original proposal was found and fixed during design: "footprint varies by quantization" implied a per-quantization VRAM figure, but the proposal's sketch had one scalar `min_vram_bytes` per backend. Resolved by keying `BackendSupport` on (backend, footprint tier), so one backend can hold several rows.
- Reference data for Chat's six families was copied verbatim from a worked table in the design doc; embedding/rerank/vision/speech/OCR had no such table and had to be *derived* — real published models were chosen, and VRAM figures computed from a formula (`ceil(parameter_bytes × 1.2 / 1e9)`, i.e. whole decimal gigabytes with a 20% overhead factor) whose exact rounding convention had to be reverse-engineered by reproducing already-accepted figures (Qwen3-8B, Llama-3.3-70B) before trusting new calculations.

`sdd-verify` (0 CRITICAL / 3 WARNING) independently re-derived FLC labels by hand, mutation-tested the structural no-`ResolvedModelRef` guard and the full descriptor↔catalog consistency harness, and even checked out isolated detached worktrees to confirm two of the eight RED/GREEN commit pairs genuinely failed-then-passed rather than trusting the claim. All 3 WARNINGs (a misleadingly-named `min_vram_bytes` field that actually stored GB not bytes, an inherited off-by-one in a DeepSeek footprint figure, a stale spec sentence) were fixed in a follow-up batch. **Archive was the very last pending step when this session ended.**

## 7. Standing project rules established this session

These apply to every future SDD phase on `tibios-ray`:

1. Strict TDD Mode is permanently active (`uv run pytest` as the test runner) — installed by adding `pytest` as a dev dependency early in the session, which is also what flipped this flag on.
2. `delivery_strategy = auto-chain`: never stop to ask about chaining a large change into stacked PRs, just do it.
3. Always fix `sdd-verify` WARNINGs (not only CRITICALs) before archiving, unless truly unfixable without fabricating evidence (e.g. rewriting commit history) — in which case acknowledge honestly instead.
4. **New this session**: every `sdd-apply` unit of work must land as two separate commits — one with only the failing test (RED, confirmed failing), one with only the implementation (GREEN) — adopted specifically because squashed commits made TDD compliance unauditable from git history in the first two phases.
5. "Worker" is reserved exclusively for the gRPC Worker Contract entity; internal units are "Capability Provider," never "Handler" or "Adapter." `WorkerRuntime` is the sole sanctioned exception.
6. Every new SDD change gets its own isolated git worktree via `EnterWorktree` — never work directly in the shared root while a parallel tibios-core session might be active there.

## 8. The open cross-repo dependency

A `.proto` gRPC contract between `tibios-core` and `tibios-ray` doesn't exist yet (proposed shared location: `../TibiOS/proto/`). Coordinated directly with the parallel tibios-core session mid-session on its shape:
- **RPC shape**: server-streaming `SubmitJob() -> stream<Response>`, not a single bidirectional stream — `18-worker-model.md` already states this as the intended shape. Cancel and Pulse are separate RPCs.
- **Correlation ID**: confirmed missing everywhere (neither `ExecutionContext` nor `18-worker-model.md` has one); recommended reusing the already-established `WorkloadId` identity type rather than inventing a new one — left open whether retry/recovery semantics need a compound ID instead.
- **Pulse delivery**: a separate RPC, not a variant of the `ExecutionEvent` stream — confirmed by the fact that `ExecutionPulse` lives in a different module (`report.py`) from `events.py`'s closed union, and was never meant to join it.

tibios-core's own `proto-worker-contract` proposal (produced from that coordination) resolves `ExecutionReport`'s missing place in the wire format with an `ExecutionResponse{ oneof { event, report } }` envelope, and separately surfaces a real gap on the tibios-ray side: `ExecutionContext` is missing Security Context, Observability Context, and Execution Parameters relative to the authoritative doc — logged as pending debt, deliberately not retrofitted until the `.proto` pins exact shapes (to avoid guessing twice). As of session end, that tibios-core change had not yet progressed past its own proposal stage.

Until this contract exists, `worker.py`/`server.py` in tibios-ray remain docstring-only composition-root stubs, and Phase 4 (real backend integrations: llama.cpp, TensorRT-LLM, vLLM, ONNX Runtime, Faster-Whisper) cannot fully proceed.

## 9. Where things stand at session end

- **Archived**: `ray-worker-runtime` (Phase 1), `capability-providers` (Phase 2).
- **Implemented, verified, warnings fixed, not yet archived**: `model-catalog` (Phase 3) — 722 tests passing, sitting in the `worktree-model-catalog` git worktree, ready for `sdd-archive`.
- **Applied but never formally archived as its own SDD change**: `python-foundation` (Phase 0 tooling).
- **Not started**: Phase 4 (real backend integrations) — partly blocked on `proto-worker-contract` landing in tibios-core.
- A comprehensive `tibios-ray/README.md` was written this session covering the whole architecture, terminology, design decisions, capability map, and roadmap for anyone picking up the project cold.
