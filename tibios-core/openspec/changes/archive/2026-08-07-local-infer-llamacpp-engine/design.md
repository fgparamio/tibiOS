# Design: Local-Infer — llama.cpp Behind the Frozen Engine Port

## Technical Approach

One new file under a frozen port, one optional dependency, one feature flag, three guard edits. `engine/port.rs` stays byte-identical; `default_engine()`'s signature stays byte-identical; **`local_infer/mod.rs` is not modified at all** (D10 settles why).

Decision numbering continues this change's **local** scheme — the proposal used D1–D6, so this document opens at **D7**, matching `worker-local-infer-adapter` (proposal D0–D3 → design D4+). D1–D6 are confirmed unchanged and are not reopened; D10 narrows D4's *mechanism* while preserving all of its substance, and says so explicitly.

D7–D13 answer the seven questions the proposal deferred. **D14 is not in the proposal**: it records a defect discovered while tracing the guards — `engine_names_stay_inside_the_engine_module` is *vacuous* against the two identifiers this change actually introduces. The proposal's Intent #3 ("the containment guards hold") is false as written until D14 lands.

---

## D7 — Bindings crate: `llama-cpp-2` (utilityai). Fallback: `llama_cpp` (edgenai)

**Choice: `llama-cpp-2`**, `default-features = false`, pinned with an exact `=` requirement.

Four criteria, weighted. Both candidates satisfy D2 (each owns its `unsafe` inside its own `-sys` crate; workspace lints never apply to dependencies), so D2 is *not* the deciding criterion — it is a gate both candidates pass.

| Criterion | `llama-cpp-2` (utilityai) | `llama_cpp` (edgenai) | Weight |
|---|---|---|---|
| **Control flow of generation** | **Pull-based.** The caller drives every step: tokenize → `LlamaBatch` → `ctx.decode(&mut batch)` → sample → repeat. No callbacks, no inversion of control. | **Push/stream-based.** `session.start_completing_with(..)` returns a `CompletionHandle` that is an `Iterator` *and* a `Stream`, fed by a **crate-spawned background thread**. | **Decisive** |
| **Async surface** | None. Zero `Future`, zero `Stream`, zero tokio. | Ships a `Stream` impl and futures machinery on the ergonomic path. | **Decisive** |
| **Hidden threads** | None on the Rust side (llama.cpp's own C-side compute threads only — see the caveat in D9). | Spawns a completion thread per session. | High |
| **Maintenance signal** | Tracks upstream llama.cpp releases continuously; release cadence follows upstream. | Went quiet after its 2024 line; effectively dormant. | High |
| **Build toolchain** | Bundles llama.cpp as a submodule; `llama-cpp-sys-2`'s `build.rs` drives **cmake + a C/C++ compiler + libclang** (bindgen). | Same family of requirements. | Neutral (tie) |

### Why control flow decides it

`TokenSink::accept(&mut self, token) -> SinkVerdict` is a **pull** contract: the engine calls the sink, reads the verdict, and decides whether to take the next step. `llama-cpp-2`'s loop maps onto it one-for-one — `SinkVerdict::Stop` is implemented by *not calling `decode` again* (D9). Nothing is needed from the FFI layer to make cancellation work.

`llama_cpp`'s ergonomic path inverts this: a background thread produces tokens into a handle. Draining it as an `Iterator` and handing each item to the sink is possible, but `Stop` then means dropping the handle and hoping the producer thread notices — a second, invisible cancellation path outside `SinkVerdict`'s reach, which is exactly the property D6 of the prior design was built to prevent. It also plants a crate-owned background thread inside the Composition Root, which `05-async-concurrency.md:125` disfavours by name.

The async surface is the second decisive point and it is *mechanical*: `local_infer_engine_declares_no_async_surface` fails on any `async` or `await` identifier under `engine/`. A crate whose ergonomic API is a `Stream` puts the engine in permanent tension with a guard that is already green.

### Version pinning — an apply-time task with a hard acceptance criterion

This design does **not** name a version, because the design phase does not query crates.io and a fabricated version number is worse than none. `sdd-apply`'s first PR1 task resolves it:

- Choose the newest `llama-cpp-2` release that builds with `default-features = false` on the developer machine.
- Declare it as an **exact** requirement: `llama-cpp-2 = { version = "=X.Y.Z", default-features = false }` (proposal risk row: "Pin an exact version").
- Commit `Cargo.lock` (already committed for this workspace).
- Record the chosen version and the upstream llama.cpp revision it bundles in the PR description.

**Known API-drift hazard:** `llama-cpp-2`'s sampling surface changed across its history (an older `ctx.sample_token_greedy(candidates)` + `LlamaTokenDataArray` shape vs. a newer `LlamaSampler` chain). D9 specifies the loop's *shape*, not exact method names; the apply task adapts names to the pinned version. If the pinned version's sampler API cannot express plain greedy decoding in under ~10 lines, pin one minor version back rather than importing a sampling-configuration surface the proposal put out of scope.

**Fallback if PR1 discovers a blocker** (build cannot be made CPU-only, or the crate cannot link on the target): `llama_cpp` + `llama_cpp_sys` (edgenai), consumed **strictly through its synchronous `Iterator` interface**, never its `Stream`. That fallback costs one background thread and a weaker `Stop` guarantee, and it must be recorded as a deviation. It is a fallback, not a co-equal option.

## D8 — `--features llamacpp` alone selects the engine. No runtime condition, no silent fallback

**The proposal's fork is not actually open at the layer it was posed.** Trace the call chain:

```
worker/mod.rs   build_local_infer_worker()
   └─ LocalInferWorker::new()            ← construction, no ExecutionContext exists
        └─ engine::default_engine()      ← fn() -> Arc<dyn TextGenerationEngine>, ZERO arguments
...later, per execution...
LocalInferWorker::execute(context, channel)
   └─ spawn_blocking → run_off_executor(engine: &dyn TextGenerationEngine, .., context, ..)
        └─ context.execution_parameters()   ← the FIRST point where parameters exist
        └─ engine.generate(&request, &mut sink)
```

`execution_parameters` first exists **inside `run_off_executor`**, on the blocking thread, long after `default_engine()` has already returned a type-erased `Arc`. "Selection conditional on `model_path` presence" therefore cannot happen at `default_engine()` without giving it an argument — forbidden by the proposal's Scope ("`default_engine()`'s signature and every call site unchanged") and by the spec's sole-exit-point requirement.

That leaves only one place a runtime condition *could* live: inside a composite engine that holds both implementations and picks per call. **Rejected, and the reason is a correctness trap, not taste:** an operator who typos `model_path` would receive `DeterministicEngine`'s FNV hash bytes streamed back as if they were inference output — a fake answer presented as a real one, with `ExecutionPhase::Completed`. A clean `EngineError::Rejected` → `ExecutionPhase::Failed` with a legible message is strictly better, and it is what D4 already asked for. It would also make `DeterministicEngine` reachable in a build that asked for real inference, hollowing out D5's "the feature *means* real inference."

**Decision.** The gate is compile-time and total:

```rust
mod port;
// DeterministicEngine is unreferenced by production code once the real engine
// is selected (D5 keeps the file and its tests either way) — a targeted allow,
// not a deletion.
#[cfg_attr(feature = "llamacpp", allow(dead_code))]
mod reference;
#[cfg(feature = "llamacpp")]
mod llamacpp;

#[cfg(not(feature = "llamacpp"))]
pub(super) fn default_engine() -> std::sync::Arc<dyn TextGenerationEngine> {
    std::sync::Arc::new(reference::DeterministicEngine::new())
}

#[cfg(feature = "llamacpp")]
pub(super) fn default_engine() -> std::sync::Arc<dyn TextGenerationEngine> {
    std::sync::Arc::new(llamacpp::LlamaCppEngine::new())
}
```

Three consequences worth naming:

1. **`use reference::DeterministicEngine;` moves out of module scope** into the `#[cfg(not(..))]` body. Left at module scope it becomes an unused import under the feature → `-D warnings` failure. The `cfg_attr(.., allow(dead_code))` on `mod reference;` covers the type itself (lint attributes on a `mod` item apply to its contents).
2. **`LlamaCppEngine::new()` must be infallible** — `default_engine()` returns `Arc`, not `Result`. All fallible work (backend init, model load) is therefore deferred to first `generate()`, which is what D11 builds.
3. The `#[cfg]` surface outside `engine/` is exactly **one line** (D13's `real_engine` test module), which D14 turns into a machine-checked invariant.

## D9 — The decode loop: pull-based, one `decode` per token, `Stop` is "stop calling `decode`"

`generate()` is an ordinary synchronous function. Nothing in `local_infer/mod.rs` changes: `run_off_executor` already calls it on a `spawn_blocking` thread, and `ChannelSink::accept` already performs the one sanctioned `handle.block_on(channel.emit(..))`. The `spawn_blocking` / `Handle::block_on` boundary is **untouched by this change**.

```rust
fn generate(&self, request: &GenerationRequest, sink: &mut dyn TokenSink)
    -> Result<GenerationSummary, EngineError>
{
    let loaded = loaded_model()?;                       // D11: process-wide OnceLock; Rejected on failure

    // Fresh context per call — the KV cache must never span two executions (D11).
    let ctx = loaded.model
        .new_context(&loaded.backend, context_params())
        .map_err(reject)?;

    let prompt_tokens = loaded.model
        .str_to_token(&request.prompt, AddBos::Always)
        .map_err(reject)?;
    if prompt_tokens.len() >= n_ctx {                   // bounded prompt eval — see the caveat below
        return Err(EngineError::Rejected(format!(
            "prompt is {} tokens, which does not fit the {n_ctx}-token context window",
            prompt_tokens.len()
        )));
    }

    let mut batch = LlamaBatch::new(n_ctx, 1);
    batch.add_sequence(&prompt_tokens, 0, false).map_err(reject)?;
    ctx.decode(&mut batch).map_err(reject)?;            // ① prompt eval — ONE bounded FFI call

    let mut sampler = greedy_sampler();                 // D9: greedy only, no sampling knobs
    let mut position = prompt_tokens.len() as i32;
    let mut tokens_produced = 0u64;
    let mut stopped_early = false;

    for sequence in 0..request.max_tokens {
        let next = sampler.sample(&ctx, batch.n_tokens() - 1);
        sampler.accept(next);
        if loaded.model.is_eog_token(next) {
            break;                                      // ② natural end-of-generation
        }

        let bytes = loaded.model.token_to_bytes(next, Special::Plaintext).map_err(reject)?;
        tokens_produced += 1;
        if sink.accept(Token { sequence, bytes }) == SinkVerdict::Stop {
            stopped_early = true;
            break;                                      // ③ THIS is how Stop halts llama.cpp
        }

        batch.clear();
        batch.add(next, position, &[0], true).map_err(reject)?;
        position += 1;
        ctx.decode(&mut batch).map_err(reject)?;        // ④ one bounded FFI call per token
    }

    Ok(GenerationSummary { tokens_produced, stopped_early })
}
```

### How `SinkVerdict::Stop` actually halts a real decode loop

**It stops calling `decode`, and that is sufficient.** There is no early-stop API to call, and none is needed: `llama-cpp-2` exposes no callback and no background producer, so generation only advances when *we* advance it. `sink.accept` runs strictly **between** `decode` calls (④ happens after ③), so a `Stop` is observed with **no FFI call in flight**. Dropping `ctx` at the end of the function releases the KV cache; the model stays loaded (D11).

Abandonment latency is therefore bounded by **one `decode` step**, which is exactly the contract the existing abandonment test asserts and the proposal's risk row promises.

**One honest caveat, disclosed rather than hidden:** ① (prompt eval) is a single FFI call whose cost scales with prompt length, and a `Stop` cannot be observed during it, because `SinkVerdict` is only reachable through `accept(token)` and no token exists yet. Widening the port with a token-free `poll` is a **port change** — out of scope. Mitigation is the explicit `n_ctx` bound above, which converts an unbounded worst case into a bounded one; an over-long prompt is rejected before any FFI work happens. Recorded as an Open Question follow-up.

### Five details that are decisions, not incidentals

- **`token_to_bytes`, never `token_to_str`.** `OutputChunk.data` is `Vec<u8>`; the byte-level contract already exists. `token_to_str` can fail on a token that carries a partial UTF-8 codepoint (common with multi-byte scripts), turning a normal generation into an `EngineError`. Reassembly across chunk boundaries is the consumer's job and always was.
- **`sequence` counts *generated* tokens from 0.** Prompt tokens are never emitted. This keeps `ChannelSink`'s `fraction_complete = (sequence + 1) / max_tokens` correct and identical to `DeterministicEngine`'s behaviour, so the existing event-sequence assertions hold unchanged.
- **EOG ends generation with `stopped_early: false`.** The port documents `stopped_early` as "stopped before `max_tokens` *because the sink returned Stop*". An EOG token is a natural completion, so `tokens_produced < max_tokens` with `stopped_early: false` — which the adapter already maps to `ExecutionPhase::Completed`. No port change, no ambiguity, no new variant.
- **`cpu_spin_iterations` is ignored.** `port.rs:16-19` already grants this ("a real engine is free to ignore it"). Not read, not validated, not mentioned in the reason strings.
- **Greedy sampling only.** Deterministic output makes D12's repeat-run test possible and keeps "sampling parameters beyond `max_tokens`" out of scope, per the proposal.

### The one non-obvious interaction with the blocking boundary

`ChannelSink::accept` may `block_on` a full bounded channel (the existing backpressure test proves it parks and resumes) **while a `LlamaContext` is alive on the same blocking thread's stack**. This is safe — llama.cpp state is thread-confined and never moves — but it means resident KV-cache memory is held for the duration of a backpressure stall. No deadlock (the drain side is a separate task), no `unsafe`, no change required. Stated because a reader will otherwise wonder.

**llama.cpp's own compute threads** are C-side (pthreads/OpenMP inside `llama_decode`) and invisible to tokio; they are not "hidden background threads" in `05-async-concurrency.md:125`'s Rust sense. This change leaves `n_threads` at the crate default. Oversubscription against tokio's blocking pool on a constrained target is a real risk (Risks table); binding thread count to the `AllocationContract` is a named follow-up, not a knob added here.

## D10 — `model_path` is process-level, from the environment. `local_infer/mod.rs` is not modified

**This narrows proposal D4's mechanism. Every substantive commitment of D4 survives; only the transport changes. Flagged in Open Questions for maintainer confirmation.**

D4 says: read `execution_parameters["model_path"]` alongside `prompt` / `max_tokens` / `cpu_spin_iterations`. Traced against the actual call chain, that mechanism is unreachable. Two independent reasons:

**Reason 1 — there is no channel from `execution_parameters` to the engine.** `execution_parameters` is reachable only from `run_off_executor` (`local_infer/mod.rs:279-281`). The sole conduit from there into the engine is `GenerationRequest`, constructed at `local_infer/mod.rs:312`. Adding a `model_path` field to it is a **port change**, forbidden twice over: Out of Scope ("Any change to the engine port — traits, **structs**, error enum") and the success criterion "`engine/port.rs` is byte-identical before and after". The remaining smuggling routes were considered and rejected:

| Route | Why rejected |
|---|---|
| `GenerationRequest.model_path` | Port change. Also breaks `port.rs`'s byte-identity criterion and the struct's `PartialEq`-based tests. |
| Encode it in `prompt` | Self-evidently wrong; makes the prompt a lie. |
| Downcast `&mut dyn TokenSink` to reach the adapter | Needs `Any` + a trait change; the sink is an adapter type the engine must not know. Port change in substance. |
| Thread-local set by `run_off_executor` before `generate()` | Technically sound (same thread, synchronous, race-free) and technically *not* a port change — but it makes the port a lie by convention, and it puts an engine-configuration concept into `local_infer/mod.rs` while pretending it isn't there. Rejected: an invisible parameter is worse than an explicit one. |
| A second `pub(super)` free function in `engine/mod.rs` (`engine::configure(&params)`) called before `generate()` | Same hidden-global mechanism with more ceremony, plus it grows `default_engine()`'s module into a stateful API. Rejected. |

**Reason 2 — a per-execution model path implies exactly what the proposal put out of scope.** If the path can vary per request, the cache in D11 must be keyed by path and unbounded — which is **multi-model residency**, listed verbatim in the proposal's Out of Scope. One path per process is the only lifecycle coherent with the proposal's own boundaries. This reason stands even if Reason 1 were solved.

**Decision.** `engine/llamacpp.rs` resolves its model path itself, once per process, from `TIBIOS_LOCAL_INFER_MODEL_PATH`:

```rust
/// Operator-supplied, out-of-band, resolved exactly once per process.
/// No registry, no download, no WorkloadId→artifact mapping (proposal D4).
const MODEL_PATH_ENV: &str = "TIBIOS_LOCAL_INFER_MODEL_PATH";

/// Pure, injectable, FFI-free — so the resolution rules are unit-testable
/// without touching the process environment or loading a model (D12).
fn resolve_model_path(lookup: impl Fn(&str) -> Option<OsString>) -> Result<PathBuf, String> { .. }
```

Unset, empty, non-existent, or not a file → `Err(String)` → `EngineError::Rejected(reason)` → the adapter's existing `Failed` path (`local_infer/mod.rs:347-353`), unchanged. The reason string always names `TIBIOS_LOCAL_INFER_MODEL_PATH` so the failure is self-diagnosing.

**Precedent, and it is this repo's own:** `crates/runtime-worker/tests/proto_drift.rs:121` already uses a `TIBIOS_`-prefixed environment variable to supply an operator-owned, never-committed path. The naming convention and the "out-of-band, not in the manifest" posture are established here, not invented.

**Placement is legal.** Reading process configuration is a Composition Root responsibility, and `runtime/src/worker/local_infer/engine/` is inside the Composition Root binary. `main.rs` would be more canonical, but routing the path from `main.rs` to the engine requires a `default_engine()` parameter — explicitly forbidden. When the port eventually grows a real configuration surface (the already-named capability-keyed-dispatch follow-up), per-execution model selection becomes expressible and this env var retires.

**Net effect: `runtime/src/worker/local_infer/mod.rs` is removed from the Affected Areas list.** Zero lines change in it outside its `#[cfg(all(test, feature = "llamacpp"))] mod real_engine;` test hook (D13).

## D11 — Load the model once per process, lazily; a fresh context per call

**Choice: process-wide `OnceLock`-memoised model + backend; `LlamaContext` created and dropped per `generate()` call.**

```rust
struct LoadedModel { backend: LlamaBackend, model: LlamaModel }

/// Process-wide, not per-instance — see "why a static" below.
static LOADED: OnceLock<Result<LoadedModel, String>> = OnceLock::new();

fn loaded_model() -> Result<&'static LoadedModel, EngineError> {
    LOADED.get_or_init(|| {
            let path = resolve_model_path(std::env::var_os)?;
            load_model(&path)                        // free fn: init backend, load GGUF
        })
        .as_ref()
        .map_err(|reason| EngineError::Rejected(reason.clone()))
}

/// Zero-sized, exactly like DeterministicEngine. All state lives in LOADED.
pub(super) struct LlamaCppEngine;
```

### Why not load-per-call (the "deliberately dumb" option D4's spirit suggests)

Rejected on evidence:

- A 4–8 GB GGUF load is **0.5–30 s**. Every execution would pay it: the O1–O4 conformance suite (a fresh `LocalInferWorker` per test), the four `#[ignore]`d tests, and every real request.
- It makes the per-token cancellation contract **meaningless**: stop latency would be dominated by model load, not by one `decode` — directly contradicting the proposal's success criterion "cancellation stops a real decode loop within one token."
- It is **flatly incorrect** for llama.cpp's global backend. `LlamaBackend::init()` initialises process-global state and errors on a second call. A per-call load would fail on execution #2 of any process. This alone disqualifies it.

### Why not an LRU / path-keyed pool

Multi-model residency is out of scope (proposal), and under D10 there is exactly one path per process. A cache of size one *is* a `OnceLock`. Anything more is machinery for a requirement that does not exist.

### Why a `static`, not a field on `LlamaCppEngine`

Non-obvious and load-bearing: `cargo test` runs a crate's tests as threads **within one process**, and the conformance harness constructs a fresh `LocalInferWorker` — hence a fresh engine — in *every* test. A per-instance `OnceLock` would call `LlamaBackend::init()` once per test and fail from the second one onward. The exactly-once guarantee must be process-scoped because llama.cpp's own requirement is process-scoped.

The cost is real and disclosed: process-global state that cannot be reset between tests. D12 pays for it by keeping every decision rule (`resolve_model_path`) and every effect (`load_model`) in free functions that are testable without the static, leaving exactly one test that goes through it.

### Failures are cached deliberately

`OnceLock` stores the `Result`, so a failed load is remembered: executions 2..N fail instantly with the identical message instead of re-attempting a multi-gigabyte read per request. An operator who fixes the file must restart the process. For a compatibility engine with an operator-supplied model, fail-fast and legible beats self-healing and slow — and it matches D4's "deliberately dumb".

### Fresh context per call

`LlamaContext` owns the KV cache. Reusing one across executions would leak conversational state between unrelated `WorkloadId`s — an isolation bug, not an optimisation. Context construction is milliseconds against seconds for model load. The split is: **model cached, context per-call.**

### Verification gate — the first task of PR2

Mirroring D8's `Handle::block_on` spike precedent (`worker-local-infer-adapter/design.md:183`), PR2's **first** task is a ~10-line compile-time assertion, before any decode logic is written:

```rust
const fn assert_send_sync<T: Send + Sync>() {}
const _: () = { assert_send_sync::<LoadedModel>(); assert_send_sync::<LlamaCppEngine>(); };
```

`TextGenerationEngine: Send + Sync` and `static` both demand it. If `LlamaModel` or `LlamaBackend` turns out not to be `Send + Sync` in the pinned version, **Fallback B** applies **without touching the port or the adapter**: confine all llama.cpp state to a dedicated owner `std::thread` created on first use, with a bounded `std::sync::mpsc` request/response pair. `generate()` sends the request and blocks on the reply channel, relaying each returned token to `sink.accept` on the calling thread and forwarding the `SinkVerdict` back. `SinkVerdict` semantics are preserved exactly (one extra channel hop per token, still bounded, still synchronous, still zero `unsafe`). Everything stays inside `llamacpp.rs`.

## D12 — Three test tiers, split by what they require to run

| Tier | Requires | Command | `#[ignore]`? |
|---|---|---|---|
| **1** | Nothing. No toolchain, no feature, no model. | `cargo test --workspace` | No |
| **2** | Native toolchain (cmake, C/C++, libclang). **No model.** | `cargo test -p runtime --features llamacpp` | No |
| **3** | Toolchain **and** an operator-supplied GGUF. | `TIBIOS_LOCAL_INFER_MODEL_PATH=/abs/path/model.gguf cargo test -p runtime --features llamacpp -- --ignored` | **Yes** |

`-p runtime` is mandatory, not cosmetic: `--features` against a virtual workspace manifest requires a package selector.

### Tier 1 — the default build, unchanged plus four guards

Every existing test passes byte-identically. New, all in `runtime/tests/architecture_guard.rs`:

| Test | Asserts |
|---|---|
| `inference_engine_dependencies_are_allowlisted_for_exactly_one_crate` | Table-only, literal template of `async_runtime_is_allowlisted_for_exactly_one_crate`: every entry of `INFERENCE_ENGINE_CRATES` owns exactly the row `["runtime"]`. |
| `the_inference_engine_dependency_is_optional_and_off_by_default` | Via `cargo_metadata`: `runtime`'s `llama-cpp-2` dependency has `optional == true`, `features` contains a `llamacpp` key, and `features["default"]` does not list it. |
| `engine_names_stay_inside_the_engine_module` (**hardened**) | D14. |
| `the_feature_gate_is_named_on_exactly_one_line_outside_the_engine_subtree` | D14. |

Plus the existing `every_crate_declares_exactly_its_allowed_external_dependencies` now enforcing the amended row `("runtime", &["tokio", "llama-cpp-2"])`.

### Tier 2 — the feature compiles, links, and fails cleanly with no model

Runs in seconds; touches FFI but never loads a real model. In `engine/llamacpp.rs`'s own `#[cfg(test)]` module (plain `#[test]`, no runtime — the subtree stays async-free):

| Test | Asserts |
|---|---|
| `the_native_backend_links_and_initialises` | The link smoke test: the pinned crate's backend initialiser succeeds. Proves the toolchain story end-to-end, not just that the dependency *built*. |
| `an_unset_model_path_is_rejected_by_name` | `resolve_model_path(\|_\| None)` → `Err` whose message contains `TIBIOS_LOCAL_INFER_MODEL_PATH`. Pure, no FFI, no static. |
| `an_empty_or_nonexistent_model_path_is_rejected` | Same injectable helper, three cases: empty string, missing file, a directory. |
| `an_unloadable_model_file_is_rejected_not_panicked` | `load_model()` against a temp file of garbage bytes → `Err(String)`, **no panic, no abort**. This is the load-bearing FFI-robustness claim. |
| `a_missing_model_yields_rejected_through_the_engine` | The single test that goes through the `LOADED` static: `LlamaCppEngine.generate(..)` with the env var unset → `Err(EngineError::Rejected(_))`, and the sink received zero tokens. |

The static-poisoning hazard is handled by construction: only the last test touches `LOADED`, and it asserts the *failure* path, which is idempotent.

### Tier 3 — four `#[ignore]`d end-to-end tests, in `runtime/src/worker/local_infer/real_engine.rs`

They must run through `LocalInferWorker` and the real `MpscExecutionChannel` — that is the success criterion ("streams real tokens end-to-end through the existing O1-O4 harness, unmodified") — so they cannot live under `engine/` (they need `#[tokio::test]`, which the async-surface scan forbids there). A new sibling file keeps `local_infer/mod.rs`'s diff to two lines.

| Test | Shape | Asserts |
|---|---|---|
| `a_real_model_streams_tokens_end_to_end` | `#[tokio::test(flavor = "multi_thread")]`, `max_tokens = 8` | `ExecutionPhase::Completed`; `OutputChunk` sequences are contiguous `0..n` with `1 <= n <= 8`; `MetricsSnapshot["tokens_produced"] == n`; `EndOfStream` is last; the concatenated chunk bytes are valid UTF-8 and non-empty. **No assertion on generated content** — model-dependent expectations are the classic rot. |
| `cancelling_a_real_decode_loop_stops_well_before_max_tokens` | `max_tokens = 512`; `cancel()` after the first `OutputChunk` arrives | `ExecutionPhase::Cancelled` and chunk count `< 32`. Deliberately not "exactly one more token": the cancel lands at a scheduling-dependent index, so the honest claim is the same bounded one the existing abandonment test makes (`local_infer/mod.rs:556`). |
| `two_identical_requests_produce_identical_bytes` | Two sequential executions, same prompt | Byte-identical `OutputChunk` streams — pins greedy sampling (D9) and catches an accidental stochastic sampler. |
| `a_prompt_longer_than_the_context_window_is_rejected` | A prompt built to exceed `n_ctx` | `ExecutionPhase::Failed`, zero `OutputChunk`s, reason names the context window. Pins D9's prompt bound. |

All four share the one process-wide loaded model (D11) — the ignored suite pays the load cost once, not four times. That is the caching decision earning its keep in the test path too.

### What happens when the feature is on but no model exists

- **Tier 3 never runs.** `#[ignore]` means `cargo test -p runtime --features llamacpp` skips it entirely: no failure, no hang, no FFI.
- **`-- --ignored` without the env var fails instantly and legibly.** A shared helper opens every Tier-3 test:

  ```rust
  fn required_model_path() -> String {
      std::env::var("TIBIOS_LOCAL_INFER_MODEL_PATH").unwrap_or_else(|_| panic!(
          "these tests require an operator-supplied GGUF model. Run:\n  \
           TIBIOS_LOCAL_INFER_MODEL_PATH=/abs/path/model.gguf \
           cargo test -p runtime --features llamacpp -- --ignored"
      ))
  }
  ```

  A panic is the *correct* outcome here, and it is not the product panicking: it is a harness-misconfiguration report, raised before any FFI call, naming the exact fix.
- **The rejected alternative is `eprintln!` + `return`** — the `proto_drift.rs:125-132` skip pattern. It is right *there* because that test runs by default and must not break `cargo test`. It is wrong *here*: `--ignored` is an explicit opt-in, so a silent pass would let the one manual verification procedure this change relies on rot unnoticed. Different trigger, different answer.
- The invocation is documented in `engine/llamacpp.rs`'s module doc comment and in the spec — no new doc file.

**CI is unchanged in this change** (proposal D5). A model-cached CI job remains a named follow-up, and the proposal's "**High**" risk row ("the engine is never actually executed by automation") stands accepted, not mitigated.

## D13 — Two chained PRs: the build story, then the decode loop

Auto-chain, per the proposal's own split. Boundary chosen so that PR1 contains **all** the risky infrastructure and **zero** inference logic — the two hard things stay separated.

| | **PR1 — "the door and its lock"** | **PR2 — "the decode loop"** |
|---|---|---|
| **Decisions landed** | D7 (crate + exact pin), D8 (feature gate), D14 (guard hardening) | D9 (decode loop), D10 (`model_path`), D11 (lifecycle), D12 (Tier 2 + Tier 3) |
| `Cargo.toml` (workspace) | **Modify** — `[workspace.dependencies] llama-cpp-2 = { version = "=X.Y.Z", default-features = false }`. `[workspace.lints.rust]` untouched. | — |
| `runtime/Cargo.toml` | **Modify** — `llama-cpp-2 = { workspace = true, optional = true }`; `[features] llamacpp = ["dep:llama-cpp-2"]`. No `default` entry. | — |
| `engine/mod.rs` | **Modify** — `#[cfg(feature)] mod llamacpp;`, the two `#[cfg]`-split `default_engine()` bodies, `cfg_attr(.., allow(dead_code))` on `mod reference;` | — |
| `engine/llamacpp.rs` | **New (stub)** — `LlamaCppEngine`; `generate()` returns `Err(EngineError::Rejected("the llama.cpp engine is not implemented yet"))`. Module docs. Tier-2 `the_native_backend_links_and_initialises` only. | **Modify** — `LOADED` static, `resolve_model_path`, `load_model`, `context_params`, the full decode loop, the `Send + Sync` gate, the rest of Tier 2 |
| `local_infer/mod.rs` | — | **Modify (2 lines)** — `#[cfg(all(test, feature = "llamacpp"))] mod real_engine;` |
| `local_infer/real_engine.rs` | — | **New** — Tier 3's four `#[ignore]`d tests |
| `tests/architecture_guard.rs` | **Modify** — `EXTERNAL_ALLOWED` row; `INFERENCE_ENGINE_CRATES` + its table test; the optional/off-by-default metadata test; hardened containment scan + its meta-test; the feature-gate-line test | — |
| `docs/platform/TibiBox-Certification.md:73-76` | — | **Modify** — llama.cpp × `local-infer` → implemented/unvalidated |
| `openspec/specs/…` | Delta for `workspace-manifest` + the feature-gate half of `local-infer-llamacpp-engine` | Delta for the engine's behavioural half + `worker-local-infer-adapter` |
| **Est. changed lines** | **~140** | **~330** |

### What PR1 alone must be green as

1. **No toolchain, feature off** — `cargo build`, `cargo clippy --all-targets -- -D warnings`, `cargo test --workspace` all green, and behaviourally byte-identical to today (`default_engine()` still returns `DeterministicEngine`).
2. **Toolchain present, feature on** — `cargo build -p runtime --features llamacpp` and `cargo test -p runtime --features llamacpp` green. This is the whole point of the slice: it proves cmake + bindgen + the bundled llama.cpp source actually build and **link** on the target, with a stub whose only behaviour is a clean `Rejected`. The riskiest, messiest part of the change is reviewed on its own, with no inference logic competing for attention.
3. **All guards green**, including the hardened scan, and the meta-test proving the hardened scan would have caught `llama_cpp_2`.

Reverting PR2 alone leaves a compiling, green workspace with a feature flag whose engine rejects every request — the proposal's "safe intermediate state", now concrete.

### Review Workload Forecast

Estimated changed lines ≈ **470**. 400-line budget risk: **Medium** (as a single PR: High). Chained PRs recommended: **Yes** — already decided by the proposal's auto-chain call, and this design fixes the boundary. Decision needed before apply: **No** — the strategy is settled; `sdd-apply` implements PR1 only, then stops. Each slice is independently green, independently revertible, and individually inside budget.

## D14 — The containment guard is currently vacuous. Harden it in PR1 (not in the proposal)

**Finding.** `engine_names_stay_inside_the_engine_module` (`architecture_guard.rs:804`) uses `contains_identifier`, which matches **whole identifiers only** (`architecture_guard.rs:499-518`: a match is rejected if the adjacent byte is alphanumeric or `_`). Apply it to the two identifiers this change actually introduces:

| Candidate leak | `"llama"` | `"llama_cpp"` | `"ggml"` / `"candle"` | Caught? |
|---|---|---|---|---|
| `use llama_cpp_2::LlamaModel;` | next byte is `_` → no match | next byte is `_` → no match | absent | **No** |
| `#[cfg(feature = "llamacpp")]` | next byte is `c` → no match | absent | absent | **No** |
| `let m: LlamaModel = ..;` | case differs, and `Llama` is followed by `M` | absent | absent | **No** |

So `use llama_cpp_2::LlamaModel;` in `main.rs` passes the guard today. The proposal's Intent #3 — "the containment guards hold; this change is the first thing `engine_names_stay_inside_the_engine_module` actually constrains" — is **false as written** for the crate D7 selects. This is a defect in the guard, and the correct response is to fix the guard, not to pick a bindings crate whose spelling happens to trip a weak matcher.

**Fix (PR1), four parts:**

1. **Substring, case-insensitive, for this scan only.** Match lowercased `line.contains(term)` over `["llama", "ggml", "candle"]` — the technique the transport scan already uses. This subsumes `llama_cpp`, `llama_cpp_2`, `llamacpp`, `LlamaModel`, `LlamaBackend`, `LLAMA_*`. `contains_identifier` stays exactly as-is for `local_infer_engine_names_no_async_runtime` and `local_infer_engine_declares_no_async_surface`, where whole-identifier matching is correct (`async` must not flag `async_runtime_is_allowlisted…`).
2. **Skip comment lines (existing convention) and build-configuration attribute lines** — lines whose trimmed form starts with `#[cfg` and whose only offending term is the feature name. The invariant being expressed is precise: *the feature gate is a Composition-Root build concept and may be named where builds are configured; the engine's **API** may never leave `engine/`.*
3. **`the_feature_gate_is_named_on_exactly_one_line_outside_the_engine_subtree`** — a positive counterpart. Outside `LOCAL_INFER_ENGINE_SRC`, `llamacpp` occurs on exactly one line, in `runtime/src/worker/local_infer/mod.rs`, and that line is a `#[cfg(...)]` attribute. Converts part 2's exemption from a hole into a bounded, named allowance.
4. **A meta-test**, following `guard_logic_catches_an_unexpected_edge`'s precedent (`architecture_guard.rs:388`): feed the hardened matcher a synthetic `use llama_cpp_2::LlamaModel;` line and assert it reports a violation. This is what stops the hardening from silently regressing to whole-identifier matching later.

Plus the row and table the proposal already mandated:

```rust
const EXTERNAL_ALLOWED: &[(&str, &[&str])] = &[
    // ..
    ("runtime", &["tokio", "llama-cpp-2"]),
];

/// External crates whose presence signals a native inference backend
/// (`local-infer-llamacpp-engine/spec.md`): allowed for exactly one crate,
/// `runtime` — see `inference_engine_dependencies_are_allowlisted_for_exactly_one_crate`.
const INFERENCE_ENGINE_CRATES: &[&str] = &["llama-cpp-2"];
```

`EXPECTED_MEMBERS` stays at 16. `ASYNC_RUNTIME_CRATES` and `TRANSPORT_CRATES` are untouched.

---

## Data Flow

```
                        BUILD TIME
runtime/Cargo.toml  [features] llamacpp = ["dep:llama-cpp-2"]   (off by default — D5/D8)
        │
        ▼
engine/mod.rs  #[cfg(feature)] → default_engine()  ──────────► Arc<dyn TextGenerationEngine>
                     │                                                │
        feature OFF ─┘                                                └─ feature ON
        DeterministicEngine                                              LlamaCppEngine (ZST)

                        RUN TIME (unchanged above the engine — D9/D10)
LocalInferWorker::execute  ── async side: RegistrationGuard, Handle::current()
   ▼
tokio::task::spawn_blocking ───────────── executor boundary ─────────────────────┐
   ▼                                                              blocking pool  │
run_off_executor      prompt / max_tokens / cpu_spin_iterations from             │
   │                  execution_parameters  (NO model_path — D10)                │
   ▼                                                                             │
LlamaCppEngine::generate(&GenerationRequest, &mut dyn TokenSink)                 │
   │                                                                             │
   ├─ loaded_model()  ── OnceLock<Result<LoadedModel, String>>  (D11)            │
   │     │  first call only: resolve_model_path(env TIBIOS_LOCAL_INFER_MODEL_PATH)
   │     │                   → LlamaBackend::init() → LlamaModel::load_from_file │
   │     └─ Err ──► EngineError::Rejected ──► ExecutionPhase::Failed ────────────┤
   │                                                                             │
   ├─ model.new_context(..)          fresh KV cache, dropped at return           │
   ├─ str_to_token → n_ctx bound check → Rejected if over                        │
   ├─ ctx.decode(prompt batch)       ① one bounded FFI call                      │
   │                                                                             │
   └─ loop 0..max_tokens:                                                        │
        sample → is_eog? break ②                                                 │
        token_to_bytes                                                           │
        sink.accept(Token) ──► handle.block_on(channel.emit(OutputChunk))        │
             │                 then: ChannelClosed? → should_stop? → deadline?   │
             ◄── SinkVerdict::Stop ──► break ③  (no further decode — THIS is     │
             │                                   how Stop halts llama.cpp)       │
             ◄── SinkVerdict::Continue                                           │
        batch.clear(); batch.add(next, ..); ctx.decode ④  one FFI call per token │
                                                                                 │
   ▼ GenerationSummary { tokens_produced, stopped_early }                        │
emit MetricsSnapshot, EndOfStream; build ExecutionReport ────────────────────────┘
```

## File Changes

| File | Action | PR | Description |
|---|---|---|---|
| `Cargo.toml` (workspace) | Modify | 1 | `[workspace.dependencies] llama-cpp-2 = { version = "=X.Y.Z", default-features = false }`. `[workspace.lints.rust]` untouched; no new member. |
| `runtime/Cargo.toml` | Modify | 1 | `llama-cpp-2 = { workspace = true, optional = true }`; `[features] llamacpp = ["dep:llama-cpp-2"]` |
| `runtime/src/worker/local_infer/engine/mod.rs` | Modify | 1 | D8 — conditional `mod llamacpp;`, the two `default_engine()` bodies, `cfg_attr` dead-code allow on `mod reference;` |
| `runtime/src/worker/local_infer/engine/llamacpp.rs` | New | 1 (stub) → 2 (full) | D7/D9/D10/D11 — the only file naming llama.cpp |
| `runtime/tests/architecture_guard.rs` | Modify | 1 | D14 — `EXTERNAL_ALLOWED` row, `INFERENCE_ENGINE_CRATES` + table test, hardened scan + meta-test, feature-gate-line test, optional/off-by-default metadata test |
| `runtime/src/worker/local_infer/mod.rs` | Modify (2 lines) | 2 | D12 — `#[cfg(all(test, feature = "llamacpp"))] mod real_engine;` **only**; no production line changes (D10) |
| `runtime/src/worker/local_infer/real_engine.rs` | New | 2 | D12 Tier 3 — four `#[ignore]`d end-to-end tests |
| `docs/platform/TibiBox-Certification.md:73-76` | Modify | 2 | llama.cpp × `local-infer` → implemented/unvalidated |
| `openspec/specs/{local-infer-llamacpp-engine,worker-local-infer-adapter,workspace-manifest}/spec.md` | New/Modify | 1 + 2 | Spec deltas — owned by `sdd-spec` |

**Explicitly unchanged:** `engine/port.rs` (byte-identical), `engine/reference.rs`, `runtime/src/main.rs`, `runtime/src/worker/mod.rs`, `runtime/src/worker/any.rs`, `runtime/src/worker/conformance.rs`, `runtime/src/worker/registry.rs`, `EXPECTED_MEMBERS` (16), `ALLOWED`, `ASYNC_RUNTIME_CRATES`, `TRANSPORT_CRATES`, `[workspace.lints.rust]`, and every crate under `crates/`.

## Testing Strategy

Strict TDD is active: every test below is written **before** the code it constrains, and the free-function decomposition in D10/D11 (`resolve_model_path`, `load_model`) exists precisely so that FFI-free rules can be red-green-refactored without a GGUF file.

| Layer | What | Tier | Command |
|---|---|---|---|
| Guard — table | `INFERENCE_ENGINE_CRATES` owns exactly `runtime`; dependency is `optional` and not in `default` | 1 | `cargo test --workspace` |
| Guard — containment | Hardened `engine_names_stay_inside_the_engine_module`; feature-gate-line test; the hardening meta-test | 1 | `cargo test --workspace` |
| Guard — regression | `local_infer_engine_names_no_async_runtime`, `local_infer_engine_declares_no_async_surface` green over the **enlarged** subtree (now including `llamacpp.rs`) | 1 (feature off) + 2 (on) | both |
| Regression | Every existing test byte-identical; `default_engine()` still returns `DeterministicEngine`; `DeterministicEngine`'s own tests still run | 1 | `cargo test --workspace` |
| Compile gate — first task of PR2 | `assert_send_sync::<LoadedModel>()`; Fallback B if it fails | 2 | `cargo build -p runtime --features llamacpp` |
| Link | `the_native_backend_links_and_initialises` | 2 | `cargo test -p runtime --features llamacpp` |
| Unit — pure | `resolve_model_path` over unset / empty / missing / directory, message names the env var | 2 | same |
| Unit — FFI robustness | `load_model` on a garbage file → `Err`, no panic, no abort | 2 | same |
| Unit — through the static | Missing model → `EngineError::Rejected`, zero tokens delivered | 2 | same |
| End-to-end | Streaming, cancellation bound, determinism, over-long prompt — all through `LocalInferWorker` + `MpscExecutionChannel`, harness unmodified | 3 | `TIBIOS_LOCAL_INFER_MODEL_PATH=… cargo test -p runtime --features llamacpp -- --ignored` |
| Lint | `cargo clippy --all-targets -- -D warnings` with the feature both off and on; zero `unsafe`, zero `#[allow(unsafe_code)]` | 1 + 2 | both |

## Migration / Rollout

Nothing persists, nothing deploys, no wire contract moves. Default-off means the shipped artifact is byte-identical to today until someone builds with `--features llamacpp`.

Rollback is `git revert` of PR2, then PR1. Reverting PR2 alone leaves a green workspace whose `llamacpp` build rejects every request — safe, compiling, and diagnostic. Reverting PR1 restores `("runtime", &["tokio"])`, deletes the feature and the guard tests, and returns the tree to its current state; `port.rs` and `reference.rs` were never touched, so the reverted tree *is* the current tree.

## Open Questions

- [x] **Confirm at review — D10 narrows proposal D4's mechanism.** D4 said "read `execution_parameters["model_path"]`". Traced against the call chain, that is unreachable without a `GenerationRequest` field (a port change, forbidden twice) and it would require path-keyed multi-model residency (out of scope). D10 substitutes `TIBIOS_LOCAL_INFER_MODEL_PATH`, preserving every substantive D4 commitment — out-of-band, resolved once, no registry, missing/unloadable → `Rejected`. **Maintainer sign-off: confirmed 2026-08-07.**
- [x] **Confirm at review — D14 hardens an existing guard the proposal assumed was already sound.** The change is small and lands in PR1, but it does mean the proposal's Intent #3 was overstated for the crate D7 selects. Alternative, if hardening is unwanted: accept that `use llama_cpp_2::…` can leak outside `engine/` unchecked. The design's position is that a guard which cannot catch the one identifier the change introduces is worse than no guard, because it is *believed*. **Maintainer sign-off: confirmed 2026-08-07.**
- [ ] **Apply-time, bounded — D7's exact version.** The pinned `llama-cpp-2` version and its bundled llama.cpp revision are resolved in PR1's first task and recorded in the PR description. If the pinned version's sampler API cannot express greedy decoding in ~10 lines, pin one minor back.
- [ ] **Named follow-up, not a blocker** — cancellation cannot be observed during prompt eval (D9's caveat). Bounded today by the `n_ctx` rejection. A real fix needs a token-free `poll` on the port, i.e. a port change.
- [ ] **Named follow-up, not a blocker** — llama.cpp's C-side compute-thread count is left at the crate default and can oversubscribe tokio's blocking pool on a constrained target. Binding it to the `AllocationContract` is a separate change with its own resource-model concerns.
- [ ] **Named follow-up, not a blocker** — a CI job with a cached GGUF model. Until it exists, the proposal's **High** risk ("the engine is never executed by automation") stands *accepted*, and Tier 3 is a manual procedure documented in `llamacpp.rs`'s module doc.
- [ ] **Named follow-up, unchanged from the prior design** — extract `local_infer/engine/` into `crates/local-infer/`, now strictly cheaper because the bindings dependency is proven (proposal D1).
