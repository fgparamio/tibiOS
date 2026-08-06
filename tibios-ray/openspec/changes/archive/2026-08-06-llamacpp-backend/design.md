# Design: The llama.cpp Text Generation Backend

Change: `llamacpp-backend` · Artifact store: hybrid (file + Engram `sdd/llamacpp-backend/design`).
Extends — never renumbers — the frozen decisions **D1-D7** (`ray-worker-runtime`), **CP1-CP8** (`capability-providers`), **MC1-MC14** (`model-catalog`). New decisions here are **LC1-LC12**.

## Technical Approach

`backends/` is the **contract** package. `engines/` is the new **SDK-bound** package. One class — `LlamaCppTextBackend` — satisfies `TextGenerationBackend` structurally (no base class, D1) and turns llama.cpp's *blocking sync* token generator into a *non-blocking async* `AsyncIterator[TextChunk]`.

Three properties carry the whole design:

1. **Transport-agnostic output.** The only thing that leaves the engine is `TextChunk` — the plain frozen dataclass already in `backends/text.py`. No gRPC type, no `llama_cpp` type, no `dict`.
2. **The blocking call runs off the event loop**, on a dedicated `Thread`, feeding a **bounded** `asyncio.Queue`. Bounded is load-bearing: it is what makes "streamed, never buffered" true across the thread boundary.
3. **Concurrency is serialized per session, not per process.** One `asyncio.Lock` per `acquire()`, next to that session's one `Llama`.

```
src/tibios_ray/engines/
  __init__.py   NEW   re-exports LlamaCppTextBackend, LlamaLike, LLAMA_CPP_BACKEND_ID
  llamacpp.py   NEW   LlamaLike, default_llama_factory, LlamaCppTextBackend
```

Layer direction is unchanged: `runtime -> capabilities -> selection -> backends`, plus the new edge `engines -> backends` **only**. Nothing imports `engines/` yet — no composition root exists (`worker.py` is still blocked on `proto-worker-contract`).

## The Canonical Boundary / Data Flow (LC1)

This is the reusable pattern every future engine (TensorRT-LLM, vLLM, ONNX Runtime, Faster-Whisper) follows. It is stated once, here, verbatim:

```
Chat Provider ──①──▶ Model Selection Policy ──②──▶ ResolvedModelRef ──③──▶ LlamaCpp Engine ──④──▶ Token Iterator ──⑤──▶ Worker Runtime ──⑥──▶ gRPC Stream
```

| # | Boundary | What crosses (concrete type) | What MUST NOT cross | Built by this change? |
|---|---|---|---|---|
| ① | Chat Provider → Model Selection Policy | `ResolvedModelRef` (only ever from `ExecutionContext.dependencies`) + `ServingConstraints` | A bare family/model-name string — structurally impossible, pinned by `tests/unit/selection/pyright_fixtures/rejects_bare_family_string.py`. Also: no `ExecutionChannel`, no `CancellationToken`, no engine type | **No** — conceptual. `ChatProvider` is a zero-field dataclass (CP1) and holds no policy. Follow-up `chat-provider-wiring` |
| ② | Model Selection Policy → ResolvedModelRef *(wire form: `ServingPlan`)* | `ServingPlan(model=ResolvedModelRef, backend=BackendId, quantization=Quantization)` | Catalog lookups, alternate model matches, discovery of any kind (`18-worker-model.md`) | **No** — the contract exists (`selection/policy.py`); no concrete policy implementation yet |
| ③ | ResolvedModelRef → LlamaCpp Engine | `ServingPlanLike` (structurally: `.backend -> BackendId`) into `supports()` / `acquire()`; plus the GGUF `model_path: str` supplied **out of band** at adapter construction | **Model-selection logic never appears right of ②.** The engine cannot even see `plan.model` — `ServingPlanLike` does not expose it. Also: no `ExecutionContext`, no `ExecutionChannel`, no gRPC type | **Yes** — entry half |
| ④ | LlamaCpp Engine → Token Iterator | `AsyncIterator[TextChunk]`, `TextChunk(text: str, finished: bool)` | `llama_cpp` objects, the `Llama` handle, raw completion `dict`s, `finish_reason` strings, threads, queues, `BackendSession` internals | **Yes — this is the entirety of this change** |
| ⑤ | Token Iterator → Worker Runtime | `TextChunk` values, consumed by a Provider that turns each into an Execution Event on `ExecutionChannel` and one terminal `ExecutionReport` | The `BackendSession`, the `LlamaLike`, any engine-owned lifetime | **No** — conceptual |
| ⑥ | Worker Runtime → gRPC Stream | proto/gRPC messages | **No gRPC or proto type ever appears left of "Worker Runtime".** `backends/text.py` has zero gRPC coupling today; this change adds none | **No** — blocked on `proto-worker-contract` |

**This change builds exactly the ③→④ segment**, consuming an already-`ResolvedModelRef`-derived plan. Everything left of ③ and right of ④ is out of scope and unmodified.

Inside ④, the only place a thread, a queue, or an SDK object exists:

```
 event loop thread                             │  dedicated pump thread
 ─────────────────────────────────────────────-┼──────────────────────────────────────────
 generate(session, request)                    │
   async with residency.lock  ← per session    │
   queue = asyncio.Queue(maxsize=8)            │
   thread.start() ─────────────────────────────┼─▶ llama.create_completion(stream=True)
   item = await queue.get()  ◀── put scheduled ─┤     for raw in stream:  (BLOCKING)
   _Token → buffer (1-token lookahead)         │       _put(_Token(raw["choices"][0]["text"]))
   _Failure → raise                            │     finally: stream.close(); _put(_Done())
   _Done → flush buffer with finished=True     │
   finally: stop_event.set()  (lock released)  │
   ▼                                           │
 TextChunk(...) ... TextChunk(finished=True)   │
```

## Architecture Decisions

| # | Decision | Alternatives rejected | Rationale |
|---|---|---|---|
| LC2 | **Per-session residency held in a side table** on the adapter: `dict[str, _Residency]` keyed by `session_id`, where `_Residency` holds `llama: LlamaLike`, `lock: asyncio.Lock`, `thread: Thread \| None` | Subclass `LlamaCppSession(BackendSession)` carrying the `Llama` + lock as extra frozen fields; a module-global registry | `BackendSession` is documented as an **opaque handle**; the side table keeps the value that crosses back to the Provider a pure two-field identity, so boundary ④ stays clean. It also makes released/foreign sessions *detectable* (`generate()` raises a precise error instead of using a closed `Llama`), makes `release()` authoritative and idempotent, and avoids stuffing mutable state (`Lock`, live thread) into a `frozen=True, slots=True` dataclass. A global registry would make the lock process-wide — the exact thing LC4 forbids |
| LC3 | `acquire(plan)` mints `session_id = f"llamacpp-{uuid4().hex}"` and constructs **one `Llama` per call** via `await asyncio.to_thread(self._factory, self._model_path)`; `release(session)` pops the entry and runs stop→join→`llama.close()` inside **one** `asyncio.to_thread` | Construct the `Llama` inline in `acquire()`; share/pool one `Llama` across sessions | Loading GGUF weights is seconds-to-minutes of blocking I/O — inline construction would stall the loop just as badly as inline generation. One `Llama` per `acquire()` is what makes LC4's independence claim real. Pooling is explicitly out of scope (proposal) |
| LC4 | **One `asyncio.Lock` per session, created in `acquire()`.** `generate()` wraps its whole body in `async with residency.lock` | A single adapter-level `asyncio.Lock`; a `threading.Lock`; no lock plus a "don't do that" docstring | `Llama` is not reentrant, so concurrent `generate()` calls on **one** session must serialize. But two independently acquired Qwen sessions own two distinct `Llama` instances and share nothing — a global lock would serialize them for no reason and silently halve throughput. `asyncio.Lock` (not `threading.Lock`) because the contended waiters are coroutines on the loop. Consequence worth knowing: an async generator runs no body until the first `__anext__`, so `generate()` **returns without taking the lock**; serialization starts at first iteration and ends at exhaustion/close |
| LC5 | **Lock release discipline**: the `async with` sits inside the async generator, so exit runs from the generator's implicit `finally` on *every* path — exhaustion, `aclose()`, `break`, `CancelledError`, or GC finalization via asyncio's asyncgen hooks. That `finally` performs **no `await`** — it only does `stop_event.set()` (non-blocking) and lets `Lock.release()` (sync, infallible) run | `try/finally` with `lock.acquire()`/`lock.release()` by hand; joining the pump thread in the `finally` | Awaiting inside a `finally` during task cancellation re-raises `CancelledError` immediately and would skip the release — the documented "lock leak if a consumer abandons the stream" risk. Keeping the finally await-free makes leak-freedom structural. The thread is *not* joined here (see LC7); it is joined off-loop in `release()` |
| LC6 | **Thread bridge**: dedicated `Thread(daemon=True)` runs the blocking generator; hand-off via `asyncio.Queue(maxsize=8)` written with `asyncio.run_coroutine_threadsafe(queue.put(item), loop)` and awaited by the pump thread | `loop.call_soon_threadsafe(queue.put_nowait, item)`; per-token `asyncio.to_thread(next, stream)`; unbounded queue | `asyncio.Queue` is not thread-safe, so the mutation must happen on the loop thread — both candidates satisfy that. The discriminator is **backpressure**: `put_nowait` on a bounded queue raises `QueueFull` inside a loop callback with no way to retry, forcing either an unbounded queue (a fast engine buffers the whole completion in RAM — "never buffered" becomes a lie) or dropped tokens. `run_coroutine_threadsafe(...).result()` blocks the *pump thread* — the one thread that is allowed to block — until the loop makes room. Per-token `to_thread` was rejected because `create_completion` is a generator whose `next()` must be pulled from a consistent thread, and it would pay a thread-pool hop per token |
| LC7 | **Abandonment protocol**: a `threading.Event` (`stop_event`). The pump's `_put` waits with a **poll timeout**, re-checking `stop_event`, and cancels the pending future when set. Consumer-side cleanup is therefore `stop_event.set()` and nothing else | Consumer drains the queue then joins; consumer joins with a timeout; rely on the daemon flag alone | If the pump blocks forever on a `put` nobody will drain, `stop_event` alone cannot free it — hence the polling `result(timeout=…)` loop. With it, the pump self-terminates within one poll interval **without** the consumer draining or joining, so cleanup stays await-free (LC5) and never blocks the loop. Straggler joining happens off-loop in `release()`, where it is both cheap and deterministic |
| LC8 | **Terminal chunk by one-token lookahead on stream exhaustion**, not by the SDK's `finish_reason`. Empty-text raw chunks are dropped; an empty completion still yields exactly one `TextChunk(text="", finished=True)` | Emit an extra empty `finished=True` chunk after the last token; read `choices[0]["finish_reason"]` | llama-cpp-python places `finish_reason` inconsistently (sometimes on the last text chunk, sometimes on a trailing empty one), and `TextChunk` has no field to carry *why* it stopped anyway. Exhaustion is unambiguous. Lookahead also matches the existing precedent in `tests/unit/backends/test_text.py`, where the last **real** chunk carries `finished=True`, and guarantees "exactly one `finished=True`" on every path including the zero-token one |
| LC9 | **All `LlamaLike` interaction happens off the event loop** — construction and `create_completion` on the pump thread or a `to_thread` worker, `close()` inside `release()`'s single `to_thread`, which joins the pump first | Call `close()` from the loop; close the SDK generator cross-thread | The SDK object is not thread-safe; confining every touch to one off-loop thread at a time makes that trivially true instead of review-enforced, and keeps the loop non-blocking by construction |
| LC10 | **Queue item union** `_Token(text: str) \| _Failure(error: BaseException) \| _Done`, frozen slotted dataclasses, narrowed by `isinstance` | Put `TextChunk` directly on the queue; use `None` as sentinel | The `finished` flag is only knowable at exhaustion (LC8), so a `TextChunk` cannot be built on the producer side. Failure and termination need to travel in-band anyway. `_Failure` re-raises the **original** exception object from the consumer, preserving the worker thread's traceback; `WorkerRuntime._dispatch` already turns any `Exception` into a Failed `ExecutionReport` (CP2 precedent), so no bespoke wrapper type is needed |
| LC11 | **Lazy SDK load via `importlib.import_module("llama_cpp")` inside `default_llama_factory` only**, with `ModuleNotFoundError` re-raised as an actionable "install `tibios-ray[llamacpp]`" message | `import llama_cpp` inside the function with `# pyright: ignore[reportMissingImports]`; a module-level guarded import | `typeCheckingMode = "standard"` makes `reportMissingImports` an error when the optional extra is absent — but `reportUnnecessaryTypeIgnoreComment = true` makes the suppression itself an error once the extra **is** installed. `importlib.import_module` resolves that pincer: typeshed gives `ModuleType.__getattr__ -> Any`, so pyright is green in both worlds with no suppression. It is also genuinely lazy — importing `tibios_ray.engines.llamacpp` never touches the SDK |
| LC12 | `supports(plan)` is **exactly** `plan.backend == LLAMA_CPP_BACKEND_ID` | Also check the model/family; also probe the GGUF file | New spec-level rule: *an Engine never performs model selection; it executes an already selected model.* Anything richer is selection logic living right of boundary ②. `ServingPlanLike` exposes only `.backend`, so this is structurally enforced, not merely intended. See the explicit limitation below |

### Accepted, explicit limitations

- **GGUF resolution is out of band (deferred debt).** `ResolvedModelRef` carries `ObjectId`/`ObjectVersion`/`ContentHash` — never a filesystem path — and nothing in tibios-ray resolves one to a `.gguf` yet. The adapter therefore takes `model_path: str` at construction, and `supports()` **cannot verify that this adapter actually serves `plan.model`**. This is stated in the module docstring, not silently absorbed. Precedent: `ray-worker-runtime` deferred `ExecutionContext` enrichment pending tibios-core. Note the pleasant coincidence: LC12's boundary rule and this debt point the same way, so closing the debt must not be implemented by teaching `supports()` to select.
- **Quantization is not passed to the engine.** `ServingPlanLike` does not expose it, and for llama.cpp the quantization is baked into the GGUF file — it travels with the path, not with the plan.
- **Abandonment is cooperative at token boundaries.** `stop_event` is checked between tokens, so cancelling mid-token costs at most one token of latency. llama.cpp's abort callback is future work.
- **The stubbed seam cannot prove the real SDK signature.** Only the opt-in integration test can. Keep it runnable.

## Key Contracts

```python
type LlamaFactory = Callable[[str], LlamaLike]

class LlamaLike(Protocol):
    """Structural shape of `llama_cpp.Llama` — the only SDK surface used."""
    def create_completion(
        self, prompt: str, *, max_tokens: int, temperature: float,
        stop: list[str], stream: bool,
    ) -> Iterator[Mapping[str, Any]]: ...
    def close(self) -> None: ...
```

Keyword-only params in the Protocol are satisfied by the SDK's positional-or-keyword ones, and extra defaulted SDK params are irrelevant to structural conformance.

The non-obvious half — backpressure plus self-terminating shutdown, on the pump thread:

```python
def _put(loop, queue, item, stop_event) -> bool:
    try:
        future = asyncio.run_coroutine_threadsafe(queue.put(item), loop)
    except RuntimeError:          # loop already closed
        return False
    while True:
        if stop_event.is_set():   # consumer abandoned the stream
            future.cancel()
            return False
        try:
            future.result(timeout=_PUT_POLL_SECONDS)   # 0.05
            return True
        except TimeoutError:
            continue
        except (CancelledError, RuntimeError):
            return False
```

Consumer side, with the two properties that matter marked:

```python
async def generate(self, session, request):          # async generator, satisfies the Protocol
    residency = self._residency_for(session)         # raises on unknown/released session
    async with residency.lock:                       # ← LC4: per session, whole lifetime
        ...
        try:
            ...                                      # lookahead loop, LC8
        finally:
            stop_event.set()                         # ← LC5/LC7: no await, never leaks
```

## File Changes

| File | Action | Description |
|---|---|---|
| `src/tibios_ray/engines/__init__.py` | Create | Re-exports + `__all__` (package-exports test convention) |
| `src/tibios_ray/engines/llamacpp.py` | Create | `LlamaLike`, `default_llama_factory`, `LlamaCppTextBackend`, `LLAMA_CPP_BACKEND_ID`, private `_Residency`/`_Token`/`_Failure`/`_Done`/`_pump`/`_put` |
| `pyproject.toml` | Modify | `[project.optional-dependencies] llamacpp = ["llama-cpp-python>=0.3.34,<0.4"]` (version re-verified at apply) |
| `tests/unit/backends/test_no_engine_imports.py` | Modify | `glob` → `rglob`; extract the scanner so recursion is asserted, not assumed |
| `tests/unit/engines/{__init__,test_llamacpp_*}.py` | Create | Residency, streaming, concurrency, cancellation, layering, exports |
| `tests/integration/{__init__,test_llamacpp_smoke}.py` | Create | Opt-in real-GGUF smoke |
| `src/tibios_ray/capabilities/chat.py` | Untouched | CP1 preserved — still raises `NoBackendAvailableError`, still zero fields |

## Testing Strategy

Strict TDD. No `pytest-asyncio` is installed — async assertions use `asyncio.run(...)` inside sync tests, matching the whole existing suite. **The stub is the entire SDK**: unit tests never import `llama_cpp`, never touch a weight file, never hit the network.

What is stubbed vs. real:

| Piece | Unit tests | Integration test |
|---|---|---|
| `LlamaLike` | `StubLlama` in `tests/unit/engines/` — a hand-written generator, `RecordingBackend`/`FakeTextBackend` precedent | Real `llama_cpp.Llama` |
| Factory | injected `lambda path: stub` | `default_llama_factory` |
| Thread, queue, lock, loop | **real** — the bridge is the thing under test | real |

| Layer | What to test | Approach |
|---|---|---|
| Unit | Protocol conformance | Typed binding `_b: TextGenerationBackend = LlamaCppTextBackend(...)` — pyright verifies structurally in one expression (CP7 precedent); no runtime `isinstance` is possible |
| Unit | Module import is SDK-free | After `import tibios_ray.engines.llamacpp`, assert `"llama_cpp" not in sys.modules` |
| Unit | Residency round trip | `acquire()` twice → two distinct `session_id`s, two distinct stub instances; `release()` calls `close()` exactly once and makes the session unusable; releasing an unknown session raises |
| Unit | `supports()` | `True` for `BackendId("llama_cpp")`, `False` for `vllm`/`tensorrt_llm`/`onnxruntime` |
| Unit | Streaming, not buffering | Stub blocks on a `threading.Event` after its **first** token; assert the consumer already received chunk 1 while the producer is still parked. Zero timing dependence |
| Unit | Loop stays alive | Stub parks until a **concurrent asyncio task** sets its event. If `generate()` blocked the loop, that task could never run and the test deadlocks → fails. Deterministic by construction, not by sleeps |
| Unit | Terminal semantics | Multi-token stub yields >1 chunk, exactly one `finished=True`, and it is the last; empty completion yields exactly one `TextChunk(text="", finished=True)` |
| Unit | Parameter mapping | Stub records its kwargs: `max_tokens`, `temperature`, `stop=list(request.stop)`, `stream=True`, prompt verbatim |
| Unit | Serialization **within** a session | Stub appends `(marker, "enter"/"exit")` under a `threading.Lock` and keeps a reentrancy counter that must never exceed 1. Two `generate()` streams on **one** session via `asyncio.gather` → log is `[enter, exit, enter, exit]`, never nested |
| Unit | Independence **across** sessions (LC4's real claim) | Two `acquire()`s; each stub waits on a shared `threading.Barrier(2, timeout=…)` before its first token. Both must enter before either exits. A global lock makes the barrier time out → test fails. This is the test that proves the lock is not global |
| Unit | Abandonment | Consume one chunk, `await agen.aclose()`; then (a) a fresh `generate()` on the same session completes — proving the lock was released without poking privates, (b) the stub's generator `finally` ran, awaited via `asyncio.to_thread(stub.closed.wait, 1.0)` |
| Unit | Exception propagation | Stub raises mid-stream → the identical exception object surfaces from the `async for`, and the lock is still released afterwards |
| Unit | Layering | AST scan of `src/tibios_ray/engines/*.py`: imports from `tibios_ray.*` are limited to `tibios_ray.backends` — no `catalog`, `selection`, `capabilities`, or `runtime`. This is the mechanical enforcement of LC12 ("an Engine never performs model selection") |
| Unit | Recursive guard | `test_no_engine_imports.py` runs its scanner twice: against the real `backends/` (expect no offenders) **and** against a synthetic nested package built in `tmp_path` containing `sub/pkg/bad.py` with a forbidden import (expect it found). Recursion becomes an assertion, not a hope |
| Integration | The stub is not lying | `tests/integration/test_llamacpp_smoke.py`, module-level `pytestmark = pytest.mark.skipif(os.environ.get("TIBIOS_RAY_LLAMACPP_GGUF") is None, ...)`. Uses only the public API (so it type-checks with the SDK absent): real factory, ≥2 chunks, one terminal chunk, `max_tokens` honored, a `stop` string honored, `release()` clean |

**Recommended guard hardening (design-added, ~10 lines, slice 1).** LC11 introduces `importlib.import_module("llama_cpp")` into this codebase — a string-based import the AST guard cannot see. Since the pattern now exists to be copy-pasted, the guard should also flag `importlib.import_module("<forbidden literal>")` inside `backends/`. Cheap, and it closes the hole this very change opens.

## Slice Plan

Keeps the proposal's three chained PRs (`auto-chain`, ~700 lines total, each slice green under `uv run pytest && uv run ruff check && uv run pyright`):

| # | Slice | Adds |
|---|---|---|
| 1 | Package, seam, residency | `engines/{__init__,llamacpp}.py` with `LlamaLike` + factory + `backend_id`/`supports`/`acquire`/`release`; conformance, residency, SDK-free-import, layering, exports tests; recursive guard fix (+ hardening); `pyproject.toml` extra |
| 2 | Streaming | `generate()`, `_pump`/`_put`, `_Token`/`_Failure`/`_Done`, LC8 lookahead; streaming, non-buffering, loop-liveness, terminal-semantics, parameter-mapping, exception-propagation tests |
| 3 | Concurrency + reality check | Serialization, cross-session independence, abandonment/lock-release tests; opt-in integration test |

## Migration / Rollout

No migration. Purely additive except two edits (`pyproject.toml` extra, guard `glob`→`rglob`). No Provider, contract, or runtime behavior changes: `ChatProvider` raises `NoBackendAvailableError` before and after, and nothing constructs `LlamaCppTextBackend` in production code until `chat-provider-wiring` lands. `git revert` of the slice commits restores the archived `model-catalog` state exactly.

## Open Questions

- [ ] **Where does `finish_reason` go?** llama.cpp distinguishes `stop` from `length`; `TextChunk` has no field for it. Deferred until a consumer needs it (a `TextChunk` field vs. an `ExecutionReport` metric is a boundary-⑤ decision, not an engine one).
- [ ] **Session-map growth.** `_sessions` only shrinks on `release()`. A caller that acquires and never releases leaks both an entry and a `Llama`. That is a contract violation, not a bug — but a future session pool should own eviction.
- [ ] **`n_ctx` / `n_gpu_layers` tuning policy.** Out of scope; the default factory uses SDK defaults plus `verbose=False`. Whoever closes the GGUF-path debt inherits this.
- [ ] **Who resolves `ResolvedModelRef` → GGUF path?** The single largest piece of deferred debt here. It is a *catalog/resolution* concern and must not be solved inside `supports()` (LC12).
- [ ] **Poll interval `_PUT_POLL_SECONDS = 0.05` and `maxsize = 8`** are judgment calls, not measurements. Revisit once a real GPU stream exists.
