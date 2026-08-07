# Design: The vLLM Text Generation Backend

Change: `vllm-backend` · Artifact store: hybrid (file + Engram `sdd/vllm-backend/design`).
Extends — never renumbers — the frozen decisions **D1-D7** (`ray-worker-runtime`), **CP1-CP8** (`capability-providers`), **MC1-MC14** (`model-catalog`), **LC1-LC12** (`llamacpp-backend`). New decisions here are **VL1-VL14**.

## Technical Approach

`backends/` is the contract; `engines/` is the SDK-bound package. One class — `VllmTextBackend` — satisfies `TextGenerationBackend` structurally (no base class, D1). What it does **not** do is as load-bearing as what it does: it reuses LC1 (canonical boundary), LC11 (lazy `importlib` seam) and LC12 (`supports()` is a family check) verbatim, and it **discards LC2-LC9 entirely** — no pump thread, no bounded queue, no `stop_event`, no per-session lock, no one-token lookahead. vLLM is natively async; every one of those mechanisms exists only to make a *blocking* SDK safe.

Three properties carry the whole design:

1. **Residency is shared, not per-session.** One lazily-constructed `AsyncLLM` serves every session, refcounted. Mirroring LC3 (one engine per `acquire()`) would duplicate weights in VRAM per session and defeat continuous batching — it would turn vLLM into something that stops being vLLM.
2. **The lock protects residency transitions, never token generation.** This is the exact inversion of LC4. llama.cpp needed a lock *around generation* because `Llama` is not reentrant; vLLM needs a lock *around `acquire`/`release`* because refcounts and single-flight construction are shared mutable state — and needs **no** lock around `generate()`, because concurrent multiplexed requests are the entire product.
3. **The `finally` block still performs no `await`.** LC5's discipline survives; its mechanism does not. Abort is a coroutine, so it is *scheduled* as a background task and *joined* deterministically in `release()` — structurally the same shape as LC5 (await-free finally) + LC7 (deterministic off-path join), implemented with tasks instead of threads.

```
src/tibios_ray/engines/
  __init__.py   MOD   also re-exports VllmTextBackend, AsyncLLMLike, VLLM_BACKEND_ID
  vllm.py       NEW   AsyncLLMLike, RequestOutputLike, default factories, _ModelRuntime, VllmTextBackend
```

Layer direction unchanged: `runtime -> capabilities -> selection -> backends`, plus the existing `engines -> backends` edge. Nothing imports `engines/` in production yet — no composition root exists (`worker.py` still blocked on `proto-worker-contract`).

## The Canonical Boundary / Data Flow (VL1)

LC1 is **inherited unchanged** — it is the reusable pattern, and the point of this change is to prove it survives a second, structurally opposite SDK:

```
Chat Provider ──①──▶ Model Selection Policy ──②──▶ ResolvedModelRef ──③──▶ vLLM Engine ──④──▶ Token Iterator ──⑤──▶ Worker Runtime ──⑥──▶ gRPC Stream
```

Boundaries ①②⑤⑥ are exactly as specified in the archived `llamacpp-backend` design and are **not restated or reinterpreted here**. Only ③ and ④ change shape:

| # | Boundary | What crosses | What MUST NOT cross | Built here? |
|---|---|---|---|---|
| ③ | ResolvedModelRef → vLLM Engine | `ServingPlanLike` (structurally: `.backend -> BackendId`) into `supports()` / `acquire()`; plus the model id/path supplied **out of band** at adapter construction | Model-selection logic. The engine still cannot see `plan.model` — `ServingPlanLike` does not expose it (VL3). No `ExecutionContext`, no `ExecutionChannel`, no gRPC type | **Yes** — entry half |
| ④ | vLLM Engine → Token Iterator | `AsyncIterator[TextChunk]`, `TextChunk(text: str, finished: bool)` | `vllm` objects, `AsyncLLM`, `RequestOutput`, `SamplingParams`, `request_id` strings, the refcount, `_ModelRuntime`, `BackendSession` internals | **Yes — the entirety of this change** |

What is new is that ④ is no longer a flat box. The Model Runtime layer lives **inside** it, invisible from either side:

```
 ┌─ VllmTextBackend ─────────────────────────────────────────────────────────┐
 │  supports(plan)          → plan.backend == VLLM_BACKEND_ID    (LC12)      │
 │                                                                           │
 │  acquire(plan)  ─┐                                                        │
 │  release(sess)  ─┴─▶ async with self._lock ──▶ ┌─ _ModelRuntime ────────┐ │
 │                      construct-or-reuse       │  engine: AsyncLLMLike   │ │
 │                      refcount ±1              │  refcount: int          │ │
 │                      teardown at 0            │  pending: set[Task]     │ │
 │                                               └────────────────────────┘ │
 │                                                          ▲                │
 │  _sessions: dict[session_id, _SessionEntry] ─────────────┘  (borrows)     │
 │                                                                           │
 │  generate(sess, req)  ── NO LOCK ──▶ engine.generate(request_id=…)         │
 │      async for output in stream:                                          │
 │          yield TextChunk(output.outputs[0].text, output.finished)          │
 │      finally: schedule_finalize(abort=not completed)   ← await-free (VL10) │
 └───────────────────────────────────────────────────────────────────────────┘
              │                                              │
              ▼                                              ▼
   BackendSession(backend_id, session_id)          TextChunk(...) ... finished=True
   ── an execution context, never residency ──
```

The invariant the `backend-adapter` delta formalizes (written in parallel by `sdd-spec`) reads directly off that picture — call it the **Backend Independence Principle**: **a Backend defines what operations are available, never how model residency is implemented.** llama.cpp keeps residency in a per-session side table; vLLM keeps it in a shared refcounted one. Both are legal; neither shape is visible to the caller. `llamacpp-text-backend` and `vllm-text-backend` are its first two proofs, not its only two permitted shapes — a future TensorRT-LLM/SGLang adapter is free to choose a third.

## Architecture Decisions

| # | Decision | Alternatives rejected | Rationale |
|---|---|---|---|
| VL2 | **The Model Runtime is a private `_ModelRuntime` dataclass owned by the `VllmTextBackend` instance**, held in a single-slot field `self._runtime: _ModelRuntime \| None`. Fields: `engine: AsyncLLMLike`, `refcount: int`, `pending: set[asyncio.Task[None]]`. It is not a public type, not injectable, not exported | A public `VllmModelRuntime` collaborator injected into the Backend; a module-global singleton registry; extra fields on `BackendSession` | A public collaborator would let a composition root share one runtime across Backends — attractive, but it exports *lifetime ownership* to a caller that does not exist yet, and makes "who calls `shutdown()`" ambiguous exactly when refcounting is the thing being got right. A module-global is LC2's already-rejected registry: unowned lifetime, cross-test leakage, and residency that outlives the object that created it. Extra fields on `BackendSession` violate the invariant this change is formalizing. Consequence, stated honestly: **residency is per-Backend-instance, not per-process** — two `VllmTextBackend` instances in one process load the model twice. Keeping one instance per backend family is a composition-root obligation (see limitations) |
| VL3 | **Refcount keying is degenerate today, on purpose.** The model id/path arrives out of band at construction (`VllmTextBackend(model=...)`, LC3's `model_path` precedent), so one adapter instance serves exactly one model and the residency table has exactly one slot — no key. The *future* key, once `ResolvedModelRef` resolution exists, is **`(content_hash, quantization)`**, not `object_id` | A `dict[ModelKey, _ModelRuntime]` keyed today by something invented; widening `ServingPlanLike` with `.model` now; keying by `object_id`+`version` | There is nothing to key *by*: `ServingPlanLike` exposes only `.backend`, and the proposal scopes this change to "one Model Runtime correctly shared across sessions of the same model". Building a keyed table now means inventing the key, which is speculative generality on a decision (`content_hash` vs `object_id`) that deserves its own change. The key must be `content_hash` because identical bytes are identical weights — two catalog versions pointing at the same content are the same residency — and must include `quantization` because the same weights served int4 and fp16 are two different engines. Widening `ServingPlanLike` is a `backends/` contract change the proposal explicitly puts out of scope |
| VL4 | **`acquire()` and `release()` need model identity; `supports()` does not — and this does not contradict LC12** | Teaching `supports()` to check the model so keying and support agree | LC12 forbids **selection**, not **identity**. `supports()` answers "am I the right *kind* of engine?" — a predicate over a closed set of `BackendId`s, decidable with zero model knowledge, and the only question asked *before* a model is fixed. `acquire()` answers "give me residency for the model this plan already names" — it *consumes* an identity chosen upstream at boundary ②. Choosing among candidate models is selection; looking up a residency slot by an identity handed to you is a dict lookup. The distinction is directional: selection flows left-to-right through ②; keying never flows backwards. Structurally enforced today by `ServingPlanLike` exposing neither — so `acquire()` cannot select even if someone tried |
| VL5 | **One `asyncio.Lock` per Backend instance guards the *entire* residency state machine** — construct-or-reuse, refcount increment, refcount decrement, teardown — and is **never** held during `generate()` | A lock scoped narrowly to construction only; a per-session lock (LC4 literally); no lock plus a docstring | Residency transitions happen once per execution, not once per token, so serializing them costs nothing and buys atomicity for three separate races at once (single-flight VL6, double-release VL12, teardown-vs-acquire VL12). A construction-only lock leaves increment/decrement/teardown racing — the refcount would be correct only by accident. LC4's per-session lock is **actively harmful** here (exploration finding 4): serializing generation defeats continuous batching, which is the entire reason to run vLLM. `generate()`'s own mutations (adding/removing a live request id) are plain dict/set operations with no `await` between read and write, so they are atomic on the single-threaded loop without a lock |
| VL6 | **Single-flight construction: lock + double-check, with no `await` between the factory returning and the slot assignment.** `async with self._lock: if self._runtime is None: engine = await factory(model); self._runtime = _ModelRuntime(engine=engine)` | A shared `asyncio.Future`/`Task` that concurrent callers await ("in-flight future" pattern); `asyncio.Event` + retry loop; optimistic construct-then-discard-the-loser | Safety proof, in two parts. (1) *Mutual exclusion*: only one coroutine is inside the critical section, so only one can observe `self._runtime is None` and reach the factory. (2) *No lost engine*: asyncio delivers cancellation only at suspension points, and there is no suspension point between `factory(...)` returning and `self._runtime = …`, so the assignment is atomic with respect to cancellation — the constructed engine can never be built and then dropped on the floor holding VRAM. The in-flight-future pattern is strictly more complex here and buys only concurrency during construction, which is worthless: waiters have nothing else to do, and the engine does not exist to serve them. It also makes cancellation semantics subtler (whose cancellation kills the shared task?) for zero gain. Optimistic construct-then-discard is the exact double-VRAM bug the proposal rates highest-severity |
| VL7 | **The engine factory is `async`: `Callable[[str], Awaitable[AsyncLLMLike]]`** | LC3's shape: a sync factory called via `await asyncio.to_thread(factory, model)` | Inverts LC3 deliberately. llama.cpp's `Llama(...)` is pure blocking CPU work with no loop affinity, so `to_thread` was free. vLLM's `AsyncLLM` attaches background asyncio machinery to the loop it runs under; constructing it in a worker thread that has no running loop is at best version-dependent, at worst binds the engine to a loop that never runs. Making the factory `async` moves the decision "on the loop, in a thread, or in a subprocess" **into the factory**, where it belongs — the Backend simply awaits and legislates nothing. The default factory constructs on the loop and accepts the stall, which is tolerable precisely because construction is per-process, not per-session (exploration finding 2). Flagged: the real construction call is SDK truth only the integration test can verify |
| VL8 | **Two injected seams, not one**: `engine_factory` (→ `AsyncLLMLike`) *and* `sampling_params_factory` (`TextRequest -> Any`). Both default to lazy `importlib.import_module` implementations (LC11 inherited unchanged) | One seam plus a `_RealAsyncLLM` wrapper class that takes our vocabulary (`max_tokens`, `temperature`, `stop`) and builds `SamplingParams` internally; constructing `SamplingParams` inline in `generate()` | llama.cpp took plain kwargs, so one seam sufficed. vLLM's request parameters are an **SDK type**, so building them inline would drag `vllm` into `generate()` and destroy the SDK-free unit tier — the single hardest requirement here, given a GB-scale CUDA-pinned wheel (exploration finding 6). The wrapper alternative is tempting and rejected for a specific reason: it reshapes `AsyncLLMLike` into *our* vocabulary, so the Protocol stops resembling the real `AsyncLLM` signature and the stub-divergence risk gets **worse**, not better — the integration test would no longer be checking the same shape the stub imitates. Two seams keep `AsyncLLMLike` a faithful mirror of the SDK and quarantine the only SDK *type* construction into ~6 lines. LC11's `importlib` pincer (`reportMissingImports` when absent vs. `reportUnnecessaryTypeIgnoreComment` when present) applies identically — vLLM's typing situation is no better than llama.cpp's, and the wheel is far heavier, so the pattern is *more* load-bearing, not less |
| VL9 | **The default sampling-params factory MUST set `output_kind=RequestOutputKind.DELTA` and `n=1`** (both from `vllm.sampling_params`) | Accepting vLLM's default `CUMULATIVE` and diffing against a running prefix; accepting cumulative and letting the Provider deduplicate | Not a tuning knob — a correctness requirement. Under `CUMULATIVE`, every `RequestOutput.outputs[0].text` is the *full* text so far, so emitting it as a `TextChunk` would make the Provider concatenate the whole completion O(n) times: quadratic work and visibly duplicated output. Prefix-diffing on our side reimplements, in the wrong layer, something the engine does correctly and for free, and pays O(n²) string comparison. `n=1` because `TextRequest` has no `n` field and we read `outputs[0]` — any `n>1` result would silently discard samples. **For `tasks`/`apply`: this MUST land as a permanent `# DELTA, not CUMULATIVE — see VL9` comment at the `output_kind=RequestOutputKind.DELTA` line in `engines/vllm.py`, not only here — the ceiling this documents (silent O(n²) duplication if vLLM's default ever gets copy-pasted back in) is invisible from the diff alone** |
| VL10 | **The terminal chunk comes straight from `output.finished`. No lookahead.** Plus one defensive rule: if the SDK generator is exhausted without ever producing `finished=True`, synthesize exactly one `TextChunk(text="", finished=True)`. Non-terminal chunks with empty delta text are dropped; a terminal chunk is never dropped | Inheriting LC8's one-token lookahead so the last *non-empty* chunk carries `finished=True`; trusting the SDK to always emit a finished output | LC8 existed because llama-cpp-python places `finish_reason` inconsistently, making exhaustion the only unambiguous terminator. vLLM has no such problem: `.finished` is a structural field on every `RequestOutput` and is authoritative. Inheriting the lookahead would delay **every** chunk by one, buying only the cosmetic property that the terminal chunk is non-empty — the precise opposite of why anyone runs vLLM. The defensive synthetic chunk keeps the cross-engine invariant "exactly one `finished=True`, always at least one chunk" true even for a zero-token completion, without buffering. Observable difference worth naming: vLLM's terminal chunk *may* be empty where llama.cpp's never is (see Open Questions) |
| VL11 | **Cancellation: the `finally` schedules a background finalize task and awaits nothing.** `finalize = abort(request_id)` then `stream.aclose()`, both exception-suppressed, registered in `runtime.pending` and joined in `release()` | `finally: await engine.abort(request_id)`; relying on generator GC / asyncgen hooks; `asyncio.shield`-ing the abort inside the `finally` | The direct `await` is the trap. Under `agen.aclose()` awaiting in a `finally` is legal — but the *same* `finally` also runs under task cancellation, where a fresh `await` can be re-cancelled immediately (`asyncio.timeout`/`wait_for` re-cancel), skipping the abort and leaking a live engine request holding KV-cache blocks. That is LC5's documented failure mode with a worse payload. Scheduling a task is synchronous and infallible, so the abort is *issued* on every exit path — exhaustion, `aclose()`, `break`, `CancelledError`, GC finalization — exactly as LC5 required, and the discipline "no `await` in the `finally`" is preserved verbatim even though the mechanism is completely different. Answering the obvious objection: a scheduled task might not run if the loop dies immediately, which is why `release()` is the **deterministic join point** — precisely LC7's off-path-join shape, tasks in place of threads. `shield` was rejected because it still requires an `await` at the cancellation-sensitive site |
| VL12 | **v0/v1 uniformity: always issue *both* the explicit `abort(request_id)` and the explicit `stream.aclose()`, and never rely on engine-side propagation** | Abort only, and let the engine terminate the generator (v0 behavior); `aclose()` only, and let vLLM's own `finally` abort (newer v1 behavior); branch on a detected engine version | The upstream inconsistency (vllm#20362, #24584) is that v0 turns `abort()` into a `CancelledError` inside the generator automatically while v1 does not, so a caller that only aborts can hang on v1 and a caller that only closes can leak on v0. Doing both makes the Backend correct under either, with no version detection — version sniffing would be a second thing to keep true as vLLM moves. The structural reason this is safe rather than merely belt-and-braces: **we are the driving code**, and we stop iterating at the same moment we abort, so the "generator hangs after abort" scenario cannot arise by construction. Aborting an already-finished request is skipped (`completed` flag) and any abort failure is suppressed — a failed cleanup must never surface as a Worker-visible error. This is what "Known Engine Behavior absorbed by the Backend" means concretely: the Worker's cancellation semantics do not vary by engine version |
| VL13 | **Refcount lifecycle.** `release()` pops the session entry under the lock and raises `UnknownSessionError` if absent (double release, foreign session, or never-acquired) — LC2's idempotent-by-rejection, inherited. Then it finalizes that session's still-live requests, decrements, and at zero **tears down while still holding the lock**: drain `runtime.pending`, `await asyncio.to_thread(engine.shutdown)`, clear the slot | Silently-idempotent `release()`; decrementing without popping; releasing the lock before teardown; a grace-period linger that keeps the engine warm for N seconds after zero | Popping under the lock makes double release structurally impossible to mistake for a legitimate second decrement — the refcount can never go negative, because the second call never reaches the decrement. The teardown-vs-acquire race resolves for free: because both paths take the **same** lock and teardown does not release it before clearing the slot, a concurrent `acquire()` either runs entirely before the decrement (refcount never reaches zero — no teardown) or entirely after the slot is cleared (it constructs a fresh engine). There is no interleaving in which a session borrows an engine that is being shut down. The cost is explicit and accepted: an `acquire()` that lands at exactly refcount 0 waits for a full shutdown and then pays a full model reload. A linger timer would fix that — and it is **residency policy**, which the proposal puts out of scope and which belongs to the future multi-model residency manager, not to the first refcount implementation |
| VL14 | **`request_id = f"{session_id}:{uuid4().hex}"`, and each session entry keeps `live: dict[str, AsyncIterator[RequestOutputLike]]`** (request id → its SDK stream), so `release()` can finalize streams a consumer suspended and abandoned without closing | A process-global counter; reusing `session_id` as the request id; tracking nothing and trusting `generate()`'s `finally` | Per-call uniqueness is mandatory — a session may run several generations, and vLLM multiplexes strictly by `request_id`, so reuse would cross-talk two live requests. Embedding the `session_id` keeps aborts traceable to a session at no cost. The `live` table exists for one real case: an async generator suspended at a `yield` has **not** run its `finally`, so a consumer that holds the generator and calls `release()` would otherwise strand a live engine request. Keeping the stream (not just the id) lets release perform the same abort+close pair as VL11, so there is exactly one cleanup path in the design |

### Accepted, explicit limitations

- **Model resolution is out of band (inherited debt, unchanged).** `ResolvedModelRef` carries `ObjectId`/`ObjectVersion`/`ContentHash`, never a model id or path, and nothing in tibios-ray resolves one yet. `VllmTextBackend(model=...)` is therefore construction-time configuration, and `supports()` **cannot verify that this adapter actually serves `plan.model`**. Identical to LC12's stated debt; closing it must not be done by teaching `supports()` to select (VL4).
- **Residency is per-Backend-instance, not per-process (VL2).** Two `VllmTextBackend` instances for the same model load it twice. The composition root — which does not exist yet — owns "one instance per backend family". Stated in the module docstring, not silently absorbed.
- **Sessions are coupled.** One shared engine means head-of-line blocking and a shared OOM blast radius across sessions. That is inherent to continuous batching and is the trade being bought deliberately; per-session isolation is what llama.cpp offers instead.
- **A `generate()` whose `finally` runs after its session was released** schedules a finalize task against an engine that may already be shut down. `_finalize` suppresses exceptions, so this is inert; it is an edge, not a leak.
- **Quantization never reaches the engine.** `ServingPlanLike` does not expose it, and vLLM takes it as a construction argument, not a per-request one — so it travels with the out-of-band configuration, exactly as the GGUF path did for llama.cpp.
- **The stubbed seam cannot prove the real SDK signature.** Only the opt-in GPU integration test can — and here it also carries the burden of pinning the real construction call (`from_engine_args` vs `from_vllm_config`) and `shutdown()`'s real shape, both of which have moved upstream. Keep it runnable.

## Key Contracts

```python
class CompletionOutputLike(Protocol):
    @property
    def text(self) -> str: ...          # the DELTA under VL9, not cumulative

class RequestOutputLike(Protocol):
    @property
    def outputs(self) -> Sequence[CompletionOutputLike]: ...
    @property
    def finished(self) -> bool: ...     # authoritative terminator (VL10)

class AsyncLLMLike(Protocol):
    """Structural shape of vLLM's `AsyncLLM` — the only SDK surface used."""
    def generate(
        self, prompt: str, sampling_params: Any, request_id: str
    ) -> AsyncIterator[RequestOutputLike]: ...
    async def abort(self, request_id: str) -> None: ...
    def shutdown(self) -> None: ...

type AsyncLLMFactory = Callable[[str], Awaitable[AsyncLLMLike]]      # VL7: async
type SamplingParamsFactory = Callable[[TextRequest], Any]            # VL8: second seam
```

`sampling_params` is `Any`, not a Protocol: it is an opaque SDK value we construct and hand back untouched, and parameter types are contravariant — a Protocol demanding `object` would not be satisfied by a method accepting `SamplingParams`. (Moot in practice: LC11's `importlib` seam means pyright checks the real SDK against nothing. The integration test is the only proof.)

Single-flight construction plus refcount, the whole critical section (VL5/VL6):

```python
async def acquire(self, plan: ServingPlanLike) -> BackendSession:
    async with self._lock:                                  # ← VL5: residency transitions only
        runtime = self._runtime
        if runtime is None:
            engine = await self._engine_factory(self._model)  # ← the only await in here
            runtime = _ModelRuntime(engine=engine)            # ← no await between: atomic
            self._runtime = runtime                           #    w.r.t. cancellation (VL6)
        runtime.refcount += 1
        ...
```

Cleanup, the non-obvious half — await-free `finally`, deterministic join elsewhere (VL11/VL13):

```python
async def generate(self, session, request):                 # async generator
    entry = self._session_for(session)                      # raises UnknownSessionError
    request_id = f"{session.session_id}:{uuid4().hex}"
    stream = entry.runtime.engine.generate(
        prompt=request.prompt,
        sampling_params=self._params_factory(request),
        request_id=request_id,
    )
    entry.live[request_id] = stream
    completed = False
    try:
        async for output in stream:                          # ← no lock (VL5)
            text = output.outputs[0].text if output.outputs else ""
            if output.finished:
                completed = True
                yield TextChunk(text=text, finished=True)
                return
            if text:                                         # drop empty non-terminal deltas
                yield TextChunk(text=text, finished=False)
        completed = True
        yield TextChunk(text="", finished=True)              # ← VL10 defensive terminator
    finally:
        entry.live.pop(request_id, None)
        _schedule_finalize(entry.runtime, stream, request_id, abort=not completed)


async def _finalize(engine, stream, request_id, *, abort: bool) -> None:
    if abort:
        with suppress(Exception):
            await engine.abort(request_id)                   # ← VL12: both, always
    with suppress(Exception):
        await stream.aclose()
```

`_schedule_finalize` does `loop.create_task(...)`, adds the task to `runtime.pending`, and registers `pending.discard` as the done-callback; a missing/closed loop is swallowed (the engine is being torn down anyway). It performs no `await` — that is the whole point.

## File Changes

| File | Action | Description |
|---|---|---|
| `src/tibios_ray/engines/vllm.py` | Create | `AsyncLLMLike`, `RequestOutputLike`, `CompletionOutputLike`, `default_engine_factory`, `default_sampling_params_factory`, `UnknownSessionError`, `VllmTextBackend`, `VLLM_BACKEND_ID`, private `_ModelRuntime`/`_SessionEntry`/`_finalize`/`_schedule_finalize` |
| `src/tibios_ray/engines/__init__.py` | Modify | Re-export `VLLM_BACKEND_ID`, `VllmTextBackend`, `AsyncLLMLike`; extend `__all__` |
| `pyproject.toml` | Modify | `[project.optional-dependencies] vllm = ["vllm>=…"]` (version pinned at apply; note the torch/CUDA coupling in a comment) |
| `tests/unit/engines/stub_async_llm.py` | Create | `StubAsyncLLM` + `StubRequestOutput` + recording params factory (`stub_llama.py` precedent) |
| `tests/unit/engines/test_vllm_{conformance,supports,sdk_free,residency,streaming,cancellation}.py` | Create | See Testing Strategy |
| `tests/unit/engines/test_engines_exports.py` | Modify | Add the three new names |
| `tests/unit/engines/test_llamacpp_layering.py` | Rename + modify | → `test_engines_layering.py`; bump the vacuity guard `>= 2` → `>= 3`. The scanner already covers `vllm.py` (it globs the package); only the file name currently lies about scope |
| `tests/integration/test_vllm_smoke.py` | Create | Opt-in GPU smoke, env-var gated |
| `src/tibios_ray/backends/adapter.py` | Untouched | The `backend-adapter` delta is spec-level; fields already comply |
| `tests/unit/backends/test_no_engine_imports.py` | Untouched | `"vllm"` already in `FORBIDDEN_ENGINE_MODULES`; guard already recursive |
| `src/tibios_ray/engines/llamacpp.py` | Untouched | Including its `UnknownSessionError` — see below |

**`UnknownSessionError` is redefined module-locally in `vllm.py`** rather than imported from `engines/llamacpp.py`, extracted to `engines/errors.py`, or promoted to `backends/adapter.py`. Importing it would pass the layering guard (which allows intra-`engines` edges) but couple two engines through a module named after an unrelated SDK. Extracting a shared module is the correct end state but edits an archived, green capability for a 12-line win before the rule of three. Promoting it to the contract is a `backends/` change the proposal puts out of scope. **Promotion trigger, stated so it is not forgotten:** the first caller that needs to catch this polymorphically across engines.

## Testing Strategy

Strict TDD. No `pytest-asyncio` — async assertions use `asyncio.run(...)` inside sync tests, matching the whole existing suite. **The stub is the entire SDK**: unit tests never import `vllm`, never touch torch, CUDA, weights, a GPU, or the network. Nothing here sleeps; every wait is an `asyncio.Event`/`Barrier` under a bounded `wait_for`.

| Piece | Unit tests | Integration test |
|---|---|---|
| `AsyncLLMLike` | `StubAsyncLLM` — an async generator yielding `StubRequestOutput`, recording `generate`/`abort`/`shutdown` calls and construction count | Real `AsyncLLM` |
| Engine factory | injected `async def _factory(model): return stub` | `default_engine_factory` |
| Sampling params factory | injected recorder returning a plain dataclass | `default_sampling_params_factory` |
| Lock, refcount, tasks, loop | **real** — the state machine is the thing under test | real |

| Decision | What a test can actually assert | Approach |
|---|---|---|
| — | Protocol conformance | Typed binding `_b: TextGenerationBackend = VllmTextBackend(model="m", ...)` — pyright verifies structurally in one expression (CP7/LC precedent); no runtime `isinstance` is possible |
| VL8 | Module import is SDK-free | After `import tibios_ray.engines.vllm`, assert `"vllm" not in sys.modules` **and** `"torch" not in sys.modules` (stricter than llamacpp's, because vLLM drags torch) |
| VL4 | `supports()` | `True` for `BackendId("vllm")`; `False` for `llama_cpp`, `tensorrt_llm`, `onnxruntime`. Plus: a `plan` object exposing only `.backend` still works — the model is structurally invisible |
| VL2/VL3 | One engine shared across N sessions | Three sequential `acquire()`s → three distinct `session_id`s, but the factory's invocation counter is **exactly 1**, and all three sessions stream from the same stub instance |
| **VL6** | **Single-flight under concurrency** | `asyncio.gather(backend.acquire(p), backend.acquire(p))` where the injected factory awaits an `asyncio.Event` set by a third task before returning — so both coroutines are *provably* in flight simultaneously — then assert the factory's invocation counter is **exactly 1** and both sessions are distinct. Without the lock this counter reads 2. This is the highest-severity risk in the proposal and it gets the sharpest test |
| VL13 | Refcount teardown at zero, not before | Two `acquire()`s; release the first → `stub.shutdown_calls == 0`; release the second → `shutdown_calls == 1`. Then `acquire()` again → factory counter is now 2 (fresh engine, slot was cleared) |
| VL13 | Double release rejected | `release(session)` twice → second raises `UnknownSessionError`; and `stub.shutdown_calls` stays 1 (proving the refcount did not go negative). Releasing a `BackendSession` never minted by this adapter raises the same |
| VL13 | Teardown-vs-acquire race | Stub's `shutdown` blocks on a `threading.Event` released by a concurrent task; `gather(release(last), acquire(plan))`. Assert the ordering invariant: the second engine's construction **starts after** the first `shutdown` returns, and the new session's stub is not the shut-down one |
| VL5 | `generate()` takes no lock | Two sessions, two `generate()` streams via `asyncio.gather`; each stub stream waits on a shared `asyncio.Barrier(2)` before its first output. Both must enter before either exits. A residency-scoped-too-widely lock makes the barrier time out → test fails. This is the test that proves the LC4 inversion is real |
| VL10 | Terminal semantics | Multi-output stub → exactly one `finished=True`, and it is the last chunk. Stub whose only output has `finished=True` → exactly one chunk. Stub that exhausts with **no** finished output → exactly one `TextChunk(text="", finished=True)` (the defensive rule). Stub emitting an empty non-terminal delta → that chunk is dropped, terminal count unchanged |
| VL9 | Delta, not cumulative | Consumer-side: concatenating all `TextChunk.text` equals the concatenation of the stub's deltas (a cumulative bug makes this quadratic and unequal). Default-factory side: inject a fake `sys.modules["vllm.sampling_params"]` module exposing a recording `SamplingParams` and a `RequestOutputKind` enum, call `default_sampling_params_factory(request)`, assert `output_kind is RequestOutputKind.DELTA` and `n == 1`. `importlib.import_module` consults `sys.modules`, so this tests the real default with zero SDK installed |
| VL8 | Parameter mapping | Injected params factory records the `TextRequest`; assert `max_tokens`, `temperature`, `stop` reach it verbatim, and that the prompt reaches `engine.generate(prompt=...)` unmodified alongside the returned params object |
| — | Streaming, not buffering | Stub parks on an `asyncio.Event` after its **first** output; assert the consumer already received chunk 1 while the producer is still parked, and that a concurrent task can run (loop liveness). Zero timing dependence |
| **VL11** | **Abandonment issues a real abort** | Consume one chunk, `await agen.aclose()`. Then `await asyncio.wait_for(stub.abort_called.wait(), 1.0)` — an `asyncio.Event` the stub sets inside `abort()`. Assert the aborted id is the one passed to `generate()`, and that `stream.aclose()` also ran (stub's generator `finally` fired). Also: the `finally` must not have awaited — asserted indirectly by the task-cancellation case below |
| VL11 | Abort survives task cancellation | Run the `async for` in a task, `task.cancel()` mid-stream, await the task's `CancelledError`, then `release()` and assert the abort still happened. A direct `await` in the `finally` fails this test on re-cancellation; the scheduled task passes |
| VL11/VL12 | No abort on clean completion | Drain the stream to its `finished=True` chunk; assert `stub.abort_calls == []` and that `stream.aclose()` still ran |
| VL13/VL14 | `release()` is the deterministic join | Start a stream, consume one chunk, do **not** close it, call `release(session)`; assert the abort for that request id was issued **and completed** before `shutdown()` was called (stub records a single ordered call log) |
| VL14 | Request ids are per-call | Two `generate()` calls on one session → two distinct `request_id`s, both prefixed with the `session_id` |
| — | Unknown session | `generate()` on a released or foreign session raises `UnknownSessionError` before touching the engine (stub's `generate` counter unchanged) |
| VL1/LC12 | Layering | Existing `engines/` AST guard (renamed `test_engines_layering.py`) — `vllm.py`'s `tibios_ray.*` imports limited to `tibios_ray.backends`; no `catalog`, `selection`, `capabilities`, `runtime` |
| — | Package exports | `test_engines_exports.py` covers the three new names |
| Integration | The stub is not lying | `tests/integration/test_vllm_smoke.py`, module-level `pytestmark = pytest.mark.skipif(os.environ.get("TIBIOS_RAY_VLLM_MODEL") is None, ...)`. Public API only (so it type-checks with the SDK absent): real factories, ≥2 chunks, exactly one terminal chunk, `max_tokens` honored, two concurrent sessions share one engine, mid-stream abandonment does not wedge the engine, `release()` clean |

## Slice Plan

Two chained PRs (`auto-chain`, ~450-550 lines total), each green under `uv run pytest && uv run ruff check && uv run pyright`:

| # | Slice | Adds |
|---|---|---|
| 1 | Model Runtime + residency | `engines/vllm.py` with `AsyncLLMLike`/`RequestOutputLike`, both default factories, `_ModelRuntime`, `backend_id`/`supports`/`acquire`/`release`, VL5/VL6/VL7/VL13; conformance, supports, SDK-free-import, sharing, single-flight, teardown, double-release, race tests; layering-guard rename; `__init__` re-exports + exports test; `pyproject.toml` extra. (The `backend-adapter` spec delta lands with this slice.) |
| 2 | Streaming + cancellation | `generate()`, `_finalize`/`_schedule_finalize`, VL9/VL10/VL11/VL12/VL14; streaming, non-buffering, delta-mapping, terminal-semantics, parameter-mapping, abandonment, task-cancellation, clean-completion, release-join, request-id tests; opt-in GPU integration smoke |

## Migration / Rollout

No migration. Purely additive except three edits (`pyproject.toml` extra, `engines/__init__.py` re-exports, layering-test rename) and one spec formalization. No contract fields, Provider, or runtime behavior change: `ChatProvider`/`VisionProvider` raise `NoBackendAvailableError` before and after, `llamacpp-text-backend` is untouched and still passes, and nothing constructs `VllmTextBackend` in production code until a composition root exists. `git revert` of the slice commits restores the archived `llamacpp-backend` state exactly.

## Open Questions

- [ ] **Cross-engine terminal-chunk shape (VL10).** llama.cpp's terminal chunk always carries text; vLLM's may be empty. If the Provider layer ever needs "the terminal chunk carries the final text", that becomes a *contract* requirement in `backends/text.py` and vLLM must buy a lookahead to satisfy it. Surfaced for `sdd-spec`: today it is a per-engine liberty, not a guarantee.
- [ ] **Who owns "one Backend instance per family per process" (VL2)?** The composition root, which does not exist. Until then the invariant is documented, not enforced.
- [ ] **The multi-model residency manager.** VL3's degenerate key becomes `(content_hash, quantization)` only when something resolves `ResolvedModelRef` to a servable model — and that same change must decide GPU-budget eviction across different models. Both are out of scope; neither should be solved inside `supports()` (VL4).
- [ ] **On-loop construction stall (VL7).** The default factory blocks the loop for the duration of a model load. Acceptable at once-per-process, unacceptable if residency ever becomes dynamic. Revisit with the residency manager.
- [ ] **`shutdown()`'s real shape and the real construction call.** `AsyncLLM.from_engine_args` vs `from_vllm_config`, and whether `shutdown()` is sync, have both moved upstream. Pinned at apply against the version in the extra; only the integration test can confirm.
- [ ] **`tensor_parallel_size` / `gpu_memory_utilization` tuning policy.** Construction-time arguments with no home in `ServingPlan`. Out of scope; the residency manager inherits it.
