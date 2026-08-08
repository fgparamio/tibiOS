# Design: TensorRT-LLM Text Backend

Decision numbering continues at **D30** (`provider-backend-composition` ended at D29). `LC*`/`VL*` refer to `llamacpp-backend` and `vllm-backend` decisions, inherited by citation rather than restated.

> **Evidence caveat.** This design phase had **no network access** (no `WebSearch`/`WebFetch` in the executing agent), so every decision below was originally written to be **stable under either outcome** of the verification it depends on. The orchestrator subsequently verified Gates 2, 3, and 4 directly against NVIDIA's LLM-API reference, an official streaming example, and a GitHub issue's real usage — see **Verification Gates** below; those three are no longer open. Gate 1 has real but inconclusive evidence (reinforces D30's marker as designed). Gates 5 and 6 still require a real engine artifact / real GPU and remain `sdd-tasks` obligations for the integration smoke test. Two proposal risks (A, B) are *resolved architecturally* — the Worker's code shape does not change under any plausible answer — while their *numeric* residue (wheel tags, version pin) is deferred to a gate task in `sdd-tasks`, not guessed here.

## Technical Approach

`engines/tensorrt.py` mirrors `engines/vllm.py` end to end: module-local structural Protocols for the SDK surface, a lazy `importlib` factory seam (LC11/VL8), one shared lazily-constructed refcounted `_ModelRuntime` (VL2), a lock guarding residency transitions only (VL5), and an await-free `finally` joined deterministically by `release()` (VL11/VL13). Three things genuinely differ, and all three are SDK-shape consequences, not taste: construction is **blocking** (D35), cancellation is **handle-scoped** rather than engine-scoped (D36), and the incremental token is a **separate field** rather than a sampling flag (D37).

The Core Principle ("engine compilation is a provisioning concern") is made structural by D39, not left to documentation.

## Data Flow

```
WorkerConfig.from_env()                       ← TIBIOS_RAY_TENSORRT_ENGINE_PATH
   └─ TensorrtLlmConfig(engine_path)
        └─ worker.py::build_runtime()          ← the ONLY constructor call site
             └─ TensorrtLlmTextBackend(engine_path=…)   ← opens nothing yet

  acquire(plan) ─┬─ lock ─┬─ _runtime is None → await factory(engine_path)
                 │        │                     └─ to_thread(LLM(model=…))   (D35)
                 │        └─ refcount += 1
                 └─→ BackendSession

  generate(session, req) → handle = engine.generate_async(prompt, params, streaming=True)
        async for out in handle:  yield TextChunk(out.outputs[0].text_diff, out.finished)   (D37)
        finally: schedule handle.abort()  ─── joined in release() ──→ to_thread(shutdown)
```

## Architecture Decisions

| # | Decision | Alternatives rejected | Rationale |
|---|---|---|---|
| **D30** | **The `tensorrt` extra carries `; python_version < '3.14'`**, verbatim in shape with the `vllm` extra, plus the same style of comment naming the revisit trigger | No marker; lowering the project's `requires-python`; a `[dependency-groups]` entry instead of an extra; a separate resolution environment | TensorRT-LLM ships interpreter-tagged Linux wheels pinned to a specific torch build; the repo is `requires-python = ">=3.14"` project-wide. Without a marker, an unresolvable extra breaks `uv lock`/`uv sync`/`uv run` **for everyone**, including the SDK-free unit tier that never imports it — the exact failure the `vllm` extra's comment already documents. This is the only option that is safe under *both* verification outcomes: if a cp314 wheel does exist, the marker is merely over-restrictive and drops in a one-line follow-up; if it does not (expected), the marker is load-bearing. Lowering `requires-python` inverts a project-wide decision to serve one optional extra. **Risk A resolved**: the isolation strategy is the marker, and the unit tier is unaffected either way because of LC11's seam |
| **D31** | **The deployment shape does not change: lazy-`importlib` optional extra, exactly like `vllm`/`llamacpp`.** Operators obtain an importable `tensorrt_llm` either from NVIDIA's prebuilt wheel index or from a prebuilt NGC container image; **the Worker never builds anything** | Making containerization a deliverable of this change; vendoring a build step; a subprocess-isolated engine process; blocking the change on wheel availability | **Risk B, answered as framed**: yes — an operator can install TensorRT-LLM without turning the Worker into a compilation environment, and this holds under *every* channel. The Worker's only requirement is that `importlib.import_module("tensorrt_llm")` succeeds; whether that module arrived via a wheel, a container image, or an operator's own source build is invisible to this codebase and is settled entirely **before** the process starts. That is precisely Invariant 2. So the worst-case verification outcome (wheel unusable, source build required) moves work into *image construction*, changes zero lines of `engines/tensorrt.py`, and changes one sentence of the install message (D32). Containerization is therefore an operator packaging choice this design *documents*, never a component it *builds* |
| **D32** | **No repo-wide extra index.** `pyproject.toml` gains no `[[tool.uv.index]]`; the index/container instruction lives in the `ModuleNotFoundError` message and the extra's comment | Adding `pypi.nvidia.com` as a project index; a `[tool.uv.sources]` pin; documenting it only in a README | A repo-wide index changes resolution for **every** dependency for **every** developer and CI job — none of which install this extra — to serve one optional engine. LC11's actionable-error precedent already puts install instructions where the failure occurs, at the moment it occurs. Cost accepted and named: `uv sync --extra tensorrt` alone will not suffice; the message must state the index flag explicitly |
| **D33** | **`_BACKEND_PREFERENCE = (vllm, tensorrt_llm, llama_cpp, onnxruntime)`** — TensorRT-LLM is inserted *second*, above llama.cpp, below vLLM. The order stays hardcoded in the Composition Root; it does **not** become operator-configurable | TensorRT-LLM first ("the operator who compiled an engine declared intent"); an env-configurable `TIBIOS_RAY_BACKEND_PREFERENCE`; a scoring policy | Decided on codebase evidence, not vendor benchmarks. `capabilities/dispatch.py::resolve_backend` builds `ServingConstraints(available_backends=frozenset(backends))` — selection is **catalog-blind and model-blind**; the catalog's `tensorrt_llm` rows (large/high-VRAM tiers only) never reach the policy. So preference order decides **every** chat request on the box, not just the large-tier ones, and VL4's inherited debt means `supports()` cannot verify the adapter serves `plan.model`. Putting TensorRT-LLM first therefore routes *all* chat traffic into one engine artifact locked to one model, one GPU SKU, one dtype and one TRT version. The failure asymmetry settles it: being wrong toward vLLM costs **latency** — observable, recoverable, and degrading gracefully under concurrency; being wrong toward TensorRT-LLM costs **availability**, and Invariant 3 forbids dynamic recovery, so a stale artifact after a driver or image upgrade is a hard stop. The "declared intent" argument is real but already served with **zero new mechanism**: an operator who wants TensorRT-LLM to win simply leaves `TIBIOS_RAY_VLLM_MODEL` unset — absent → `None` → unwired (`worker-configuration`). Intent is expressed by what you configure, not by a ranking. Config-by-omission also removes the only motive for an env-configurable order, which D28 independently disfavours (the tuple is a *deployment belief owned by the Composition Root*; moving it to env needs `BackendId`-list parsing, unknown-id validation, and ordering-vs-availability semantics — its own change). Bonus, and the reason this is the low-regret choice: the change's only non-additive edit degenerates from a **reorder** into an **insertion**, so no existing vLLM deployment is silently rerouted and rollback is a one-token delete |
| **D34** | **Residency is vLLM's shape, adopted wholesale**: one lazily-constructed refcounted `_ModelRuntime` per Backend instance, single-flight construction under the lock with no `await` between factory-return and slot assignment, teardown at refcount zero while still holding the lock. VL2/VL3/VL5/VL6/VL13/VL14 inherited unchanged | llama.cpp's pool of N pre-warmed instances (LC-shape); a public injectable runtime; a process-global registry | TensorRT-LLM's `LLM` owns an in-process executor, a CUDA context, and the engine's entire VRAM footprint — N instances cost N× VRAM and N× load time, and the executor already performs in-flight batching internally, so a pool buys concurrency the engine provides for free while multiplying the resource that is actually scarce. The proposal explicitly refused to *assume* this inheritance; it is confirmed here on the resource argument, not by analogy. The known consequences carry over verbatim and are re-stated in Limitations, not silently absorbed |
| **D35** | **Construction is blocking: the factory keeps VL7's `async` signature but its default body is `await asyncio.to_thread(...)`** — LC3's body inside VL7's shape | VL7's on-loop construction copied literally; a sync `Callable` factory (LC3's signature); constructing eagerly in `__init__` | VL7 chose an async signature so the "on the loop / in a thread / in a subprocess" decision lives **in the factory** — that rationale survives intact and is why the signature does not change. What inverts is the *default body*: vLLM's `AsyncLLM` attaches asyncio machinery to the constructing loop, whereas TensorRT-LLM's `LLM(...)` is a plain synchronous constructor that loads an engine into VRAM and starts worker processes. Under D27 (eager construction at boot = startup viability), an on-loop construction of that shape stalls the event loop — and therefore the gRPC transport serving every *other* capability — for the whole load. `to_thread` confines the stall to a worker thread. If verification shows loop affinity after all, the fallback is on-loop construction with a documented stall; **both live behind the same unchanged seam**, which is the point of keeping VL7's signature. Teardown is already symmetric: `shutdown()` is blocking, and `await asyncio.to_thread(runtime.engine.shutdown)` is what `vllm.py` does today |
| **D36** | **Cancellation is handle-scoped.** `generate_async(..., streaming=True)` returns the result handle, which *is* the async iterator and owns `abort()`. `_finalize` awaits `handle.abort()` under `suppress(Exception)`; there is **no** `aclose()` counterpart. The `live` side table is keyed by a locally-minted `stream_key = f"{session_id}:{uuid4().hex}"`, never by an SDK request id | Engine-level `abort(request_id)` (VL12's shape, transplanted); using the SDK's own `request_id` as the key; tracking nothing and trusting `generate()`'s `finally` | The LLM API exposes no engine-level `abort(request_id)`, so VL12's "always issue both calls" halves: the handle is not an async generator, so it has no `aclose()`. VL12's *principle* — never rely on engine-side propagation, always issue the explicit call, always suppress — is preserved; only the target moves. The key is minted locally on purpose: an SDK-assigned `request_id` is known only after the call returns and its timing is a version detail, whereas VL14's stranded-suspended-generator problem is **ours** and needs a key we own from the first line. Naming it `stream_key` rather than `request_id` stops the code implying an SDK identity it does not hold. VL11's await-free `finally`, `runtime.pending`, and `release()`-as-join-point are inherited verbatim |
| **D37** | **Read `output.outputs[0].text_diff` — never `.text`.** `.text` is cumulative; `text_diff` is the increment. This MUST land as a permanent `# text_diff, not text — see D37` comment at the read site. **VL9 has no counterpart here**: no `output_kind` flag is set, because TensorRT-LLM solves cumulative-vs-delta with a *field*, not a *sampling parameter* | Emitting `.text` (the SDK's headline field); prefix-diffing against a running local `_last_len`; asking the Provider to deduplicate | Same correctness requirement as VL9 with a different mechanism. Emitting cumulative text as a `TextChunk` makes the consumer concatenate the whole completion O(n) times — quadratic work and visibly duplicated output — and, exactly as VL9 warned, the bug is **invisible in a diff** because `.text` is the field a reader expects, which is why the comment is mandated rather than suggested. Prefix-diffing reimplements in the wrong layer something the engine already computes for free. Notable simplification this buys: VL8's *second* seam is not eliminated (`SamplingParams` is still an SDK type, so the `sampling_params_factory` quarantine stands) but it is no longer load-bearing for correctness — it now carries only `max_tokens`/`temperature`/`stop`/`n=1` |
| **D38** | **`TensorrtLlmConfig(engine_path: str)` — one field, from `TIBIOS_RAY_TENSORRT_ENGINE_PATH`**, and the Backend's constructor keyword is `engine_path`, not `model` | A second `tokenizer_path` field (ONNX's shape); a `ModelArtifact`/catalog indirection; naming the field `model` to mirror `VllmConfig` | Mirrors `VllmConfig`'s single-field shape per `config.py`'s stated convention (field names mirror constructor keywords). The name is load-bearing, not cosmetic: `model=` would read as an HF model id, and passing an HF checkpoint is exactly the JIT-build escape hatch the Core Principle forbids — `engine_path=` makes that misuse read as a misuse at the call site. Accepted limitation, stated not hidden: the tokenizer must be **colocated in the engine directory**, since the LLM API resolves it from the model path. That is OR10's two-artifacts debt in a new costume, and it is deliberately **not** re-opened here — the proposal defers the Model Catalog explicitly |
| **D39** | **The default factory performs a pre-flight artifact check and refuses a non-engine path before the SDK is ever asked to load it**: the path must exist, be a directory, and contain at least one `*.engine` file — otherwise a `ConfigError`-shaped failure naming `TIBIOS_RAY_TENSORRT_ENGINE_PATH` and the Operational Model. The adapter never catches, converts, retries, or falls back; a genuine SDK load failure propagates unchanged out of `acquire()` and the residency slot stays `None` | Letting the SDK decide (existence-only, or no check at all); catching load failures and reporting them as a capability-level error; validating eagerly in `__init__` | This is what makes Invariant 3 **structural** rather than aspirational. Without it, `LLM(model=<HF checkpoint>)` *succeeds* — by silently starting a 10-to-90-minute build inside `acquire()`, which is the single failure the Core Principle exists to prevent, and no amount of documentation prevents an operator pointing the env var at a checkpoint directory. A cheap, local, pre-SDK predicate turns that into an immediate, attributable configuration error. Not in `__init__`, because residency is lazy (VL2) and eager validation would re-introduce a boot-time filesystem dependency the other two engines do not have. Layout knowledge is the accepted cost and is deliberately shallow: if `*.engine` ever stops being the output layout, the integration smoke test fails loudly rather than the check passing silently |

### Accepted, explicit limitations

- **Everything VL2/VL4/VL13's limitations already say** — per-Backend-instance residency (two instances load twice), out-of-band model resolution (`supports()` cannot verify it serves `plan.model`), coupled sessions (head-of-line blocking, shared OOM blast radius), and a refcount-zero `acquire()` paying a full reload — carries over unchanged. TensorRT-LLM makes the last one *worse* in wall-clock terms (engine load is heavier than vLLM's), and cheaper in probability terms (an engine artifact is rarely torn down mid-service).
- **Tokenizer colocation** (D38). No second field, no catalog.
- **The stub cannot prove the real SDK signature** (VL's inherited debt). `tests/integration/test_tensorrt_smoke.py` is the only proof, and here it carries an unusually heavy load — it is the sole check on D35, D36, D37 and D39's layout predicate.
- **A single-GPU assumption is implicit**, not enforced: nothing rejects an engine artifact built with tensor parallelism > 1. Out of scope per the proposal; named so it is not mistaken for a guarantee.

## Key Contracts

```python
TENSORRT_LLM_BACKEND_ID = BackendId("tensorrt_llm")   # must equal the catalog's id

class CompletionOutputLike(Protocol):
    @property
    def text_diff(self) -> str: ...      # the DELTA (D37) — `.text` is CUMULATIVE, never read it

class RequestOutputLike(Protocol):
    @property
    def outputs(self) -> Sequence[CompletionOutputLike]: ...
    @property
    def finished(self) -> bool: ...      # authoritative terminator (VL10 inherited)
    def __aiter__(self) -> AsyncIterator["RequestOutputLike"]: ...   # the handle IS the iterator
    async def abort(self) -> None: ...   # D36: handle-scoped, no engine-level abort(request_id)

class LLMLike(Protocol):
    """Structural shape of `tensorrt_llm.LLM` — the only SDK surface this module uses."""
    def generate_async(
        self, prompt: str, sampling_params: Any, streaming: bool
    ) -> RequestOutputLike: ...
    def shutdown(self) -> None: ...      # blocking → to_thread (D35)

type LLMFactory = Callable[[str], Awaitable[LLMLike]]        # VL7's signature, D35's body
type SamplingParamsFactory = Callable[[TextRequest], Any]    # VL8's quarantine, minus VL9's flag
```

Gotcha to encode in the stub, not just here: the handle yielded by `async for` is expected to be **the same object each iteration**, mutated in place. Harmless for this adapter — fields are read per-iteration and the object is never retained — but a stub that yields fresh objects would test a shape the SDK does not have.

## File Changes

| File | Action | Description |
|---|---|---|
| `src/tibios_ray/engines/tensorrt.py` | Create | `LLMLike`, `RequestOutputLike`, `CompletionOutputLike`, `default_engine_factory` (D35 + D39), `default_sampling_params_factory`, `UnknownSessionError` (module-local, VL's precedent — the rule of three is only now reached; extraction is the *next* engine's job), `TensorrtLlmTextBackend`, `TENSORRT_LLM_BACKEND_ID`, private `_ModelRuntime`/`_SessionEntry`/`_finalize`/`_schedule_finalize` |
| `src/tibios_ray/engines/__init__.py` | Modify | Re-export `TENSORRT_LLM_BACKEND_ID`, `TensorrtLlmTextBackend`, `LLMLike`; extend `__all__` (aliasing, D29) |
| `src/tibios_ray/config.py` | Modify | `TensorrtLlmConfig`, `_TENSORRT_ENGINE_PATH` constant, `_tensorrt_config()`, one `WorkerConfig` field, one `from_env()` line |
| `src/tibios_ray/worker.py` | Modify | One `if config.tensorrt_llm is not None:` branch; **insert** `TENSORRT_LLM_BACKEND_ID` into `_BACKEND_PREFERENCE` at index 1 (D33) with a comment citing D33's rationale |
| `pyproject.toml` | Modify | `tensorrt = ["tensorrt-llm>=X,<Y; python_version < '3.14'"]` (D30) + comment carrying D31/D32's install channel; exact pin from Gate 1 |
| `tests/unit/engines/stub_trtllm.py` | Create | `StubLLM` + `StubRequestOutput` (self-yielding, `text_diff`-bearing, recording `generate_async`/`abort`/`shutdown` + construction count), mirroring `stub_async_llm.py` |
| `tests/unit/engines/test_tensorrt_*.py` | Create | See Testing Strategy |
| `tests/unit/engines/test_engines_exports.py` | Modify | Add the three new names |
| `tests/unit/engines/test_engines_layering.py` | Modify | Bump the vacuity guard `>= 3` → `>= 4` (the scanner globs the package already) |
| `tests/unit/backends/test_no_engine_imports.py` | Modify | Add `"tensorrt_llm"` to `FORBIDDEN_ENGINE_MODULES` |
| `tests/unit/{config,test_worker}.py` | Modify | New config slot; preference-order assertion; construction-scan guard |
| `tests/integration/test_tensorrt_smoke.py` | Create | Opt-in, gated on `TIBIOS_RAY_TENSORRT_ENGINE_PATH`; carries Gates 2–5 |
| `openspec/specs/tensorrt-llm-text-backend/spec.md` | Create | Living spec (owned by `sdd-spec`) |
| `src/tibios_ray/{capabilities,backends,selection,runtime,transport}/**`, `engines/{llamacpp,vllm,onnxrt}.py` | Untouched | The point of the change |

## Testing Strategy

Strict TDD, `uv run pytest`. No `pytest-asyncio` — `asyncio.run(...)` inside sync tests, matching the suite. **The stub is the entire SDK**: the unit tier imports no `tensorrt_llm`, touches no CUDA, no weights, no GPU, no network, and no filesystem beyond `tmp_path`. No `sleep`; every wait is an `Event`/`Barrier` under a bounded `wait_for`.

| Layer | What to test | Approach |
|---|---|---|
| Unit — conformance | Structural satisfaction of `TextGenerationBackend`; `supports()` is a family check (LC12/VL4), never selection | Assignment to the Protocol + id-mismatch cases |
| Unit — residency (D34) | Single-flight construction under concurrent `acquire()`; refcount reuse; teardown exactly at zero; `UnknownSessionError` on double/foreign release | `StubLLM` construction counter; barriers |
| Unit — streaming (D37) | **A cumulative-`.text` stub must not change output**: chunks come from `text_diff`; `finished` terminates; empty non-terminal deltas dropped; defensive synthetic terminator | Stub sets `.text` to a growing prefix and `text_diff` to the increment; assert emitted chunks concatenate to `.text` exactly once |
| Unit — cancellation (D36) | `abort()` issued on exhaustion-free exit, `aclose()`, `break`, `CancelledError`; `release()` strands nothing; single-owner claim never double-finalizes; `finally` performs no `await` | Recording stub + `runtime.pending` drain assertions |
| Unit — blocking construction (D35) | The default factory does not run the constructor on the loop | Monkeypatched `to_thread` / thread-identity assertion in an injected factory |
| Unit — Invariant 2 (**no compilation entry point**) | Source of `engines/tensorrt.py` contains no reference to `trtllm-build`, `build_config`, `BuildConfig`, `quantize`, or `subprocess` | AST/source scan, mirroring the existing guard style |
| Unit — Invariant 3 (D39) | A missing path, a file, and a directory with no `*.engine` each raise an actionable configuration failure **without** invoking the SDK | `tmp_path` fixtures + an SDK import that would fail if reached |
| Unit — composition | `TIBIOS_RAY_TENSORRT_*` absent → Worker starts, `tensorrt_llm` absent from the mapping; present → wired; `_BACKEND_PREFERENCE == (vllm, tensorrt_llm, llama_cpp, onnxruntime)` (D33); `worker.py` remains the sole constructor | `WorkerConfig(env=dict(...))` + existing scan guards |
| Unit — SDK-free | Importing `engines.tensorrt` with `tensorrt_llm` absent succeeds; the factory raises the actionable `ModuleNotFoundError` naming the extra **and** the index/container (D32) | `sys.modules` sabotage, `test_vllm_sdk_free` precedent |
| Integration (opt-in) | Real `LLM` against a real engine artifact — **the only check on Gates 2–5** | Skipped unless the env var is set |

## Migration / Rollout

No migration. Purely additive except one `_BACKEND_PREFERENCE` **insertion** (D33), which by construction preserves the existing relative order of `vllm`/`llama_cpp`/`onnxruntime` — no configured deployment changes behaviour unless it newly sets `TIBIOS_RAY_TENSORRT_ENGINE_PATH`.

**Slice plan** (matching the proposal; `sdd-tasks` owns the final split and the Review Workload Forecast):
- **PR 1** — `TensorrtLlmConfig` + parser; `_ModelRuntime` and the residency seam (`backend_id`, `supports`, `acquire`, `release`); D35's factory + D39's pre-flight check; `stub_trtllm.py`.
- **PR 2** — `generate()` (D37), cancellation/finalize (D36), Composition Root wiring, `_BACKEND_PREFERENCE` (D33), the extra (D30/D32), exports/layering/forbidden-import guards, integration smoke.

## Verification Gates

These are **`sdd-tasks` obligations**, each blocking a specific line — not open design questions. The design does not change if a gate flips; the listed consequence does.

**Post-design update (orchestrator, WebSearch/WebFetch — the executing `sdd-design` agent had neither tool):** Gates 2, 3, and 4 are now **verified against NVIDIA's own docs, reference API, and source**, not just trained-knowledge recall. Gate 1 has real but inconclusive evidence, reinforcing D30's marker rather than flipping it. Gates 5 and 6 still require a real engine artifact / real GPU and are left for the integration smoke test, as no amount of doc-reading substitutes for them.

| # | Fact to verify | How | Result |
|---|---|---|---|
| 1 | Distribution channel + resolvable version range + interpreter tags of `tensorrt-llm` | NVIDIA install docs / PyPI listing | **Inconclusive, leans negative.** PyPI's `tensorrt-llm` metadata (as of Aug 2026) declares `>=3.10,<4` but its classifiers tag only 3.10/3.12 — no confirmed cp314 wheel, even though the sibling `tensorrt` SDK package has added 3.14 wheels separately. **D30's marker stays as designed**; `sdd-tasks` still owns the exact `X`/`Y` pin via a dry-run check at implementation time, since PyPI listings shift |
| 2 | `generate_async` returns the handle **synchronously** and the handle is async-iterable | NVIDIA LLM-API reference (`reference.html`) + official example `llm_inference_async_streaming.py` | **Verified.** Reference declares `generate_async(...) → RequestOutput` (not `Coroutine`); the official example iterates it directly as `async for output in llm.generate_async(prompt, sampling_params, streaming=True):` — no `await` before the `async for`. D35/Key Contracts' `LLMFactory`/`RequestOutputLike` shape holds as designed |
| 3 | `CompletionOutput.text_diff` exists and is the increment | NVIDIA LLM-API reference: `CompletionOutput.text_diff` is documented as "Newly generated tokens" (property), alongside `.text` (cumulative). The official streaming example's own sample output empirically shows `.text` growing across iterations (`'\n'` → `'\n\n'` → `'\n\nJ'` → `'\n\nJane'`...), confirming `.text` is cumulative exactly as D37 assumed | **Verified.** D37 stands unchanged; no fallback to `_last_len` prefix-diffing needed |
| 4 | The handle exposes `abort()` | GitHub `NVIDIA/TensorRT-LLM` issue #10810 shows real usage: `async for output in llm.generate_async(...): ... output.abort(); break` — `abort()` called directly on the yielded `RequestOutput`/handle object | **Verified.** D36's handle-scoped `abort()` (not an engine-level `abort(request_id)`) is exactly this shape |
| 5 | `trtllm-build` output layout contains `*.engine` | Inspect a real artifact | Still open — needs a real build, not a doc. If not, D39's predicate weakens to directory-existence; the decision (pre-flight refusal) stands |
| 6 | `LLM(...)` has no loop affinity | Integration smoke under `to_thread` | Still open — needs a real GPU. If it does, the default factory constructs on-loop with a documented stall — same seam, different body (D35 anticipated this) |

## Open Questions

- [ ] **None blocking.** The proposal's three open questions are closed: Q1 → **D33**, Q2 → **D37**, Q3 → **D30/D31/D32** (name and form decided; the numeric pin is Gate 1, deliberately not guessed).
- [ ] Deferred by prior decision, restated so it is not lost: operator-configurable preference order (rejected in D33 — belongs to its own change), a Model Catalog / `ModelArtifact` domain (deferred by the proposal; D38's tokenizer-colocation limitation is one more datum for it), and extracting the thrice-duplicated `UnknownSessionError` into `engines/errors.py` (the rule of three is reached *by this change*, making it the natural next cleanup — not folded in here, to keep two archived green capabilities untouched).
