# Design: The ONNX Runtime Embedding and Rerank Backend

Change: `onnx-runtime-backend` · Artifact store: hybrid (file + Engram `sdd/onnx-runtime-backend/design`).
Extends — never renumbers — the frozen decisions **D1-D7** (`ray-worker-runtime`), **CP1-CP8** (`capability-providers`), **MC1-MC14** (`model-catalog`), **LC1-LC12** (`llamacpp-backend`), **VL1-VL14** (`vllm-backend`). New decisions here are **OR1-OR11**.

## Technical Approach

`backends/` is the contract; `engines/` is the SDK-bound package. Two classes — `OnnxEmbeddingBackend` and `OnnxRerankBackend` — each satisfy exactly one modality protocol structurally (no base-Protocol edge, D1), over one private, shared residency implementation.

The single insight this change buys, and the reason "N=2 says pick the other one" is the wrong way to decide OQ1:

> **Residency shape and async-bridge shape are independent axes.** Residency shape is decided by whether the engine holds *per-request mutable state*. Bridge shape is decided by whether the engine's API is *blocking*. llama.cpp was (stateful, blocking); vLLM was (shared-batched, async). Those are the two diagonal cells, so N=2 could not tell the axes apart. ONNX Runtime is the off-diagonal cell — **stateless and blocking** — and picks one answer from each predecessor: vLLM's shared refcounted residency (OR2) with llama.cpp's off-loop thread bridge (OR7), and neither one's complexity (no pump thread, no bounded queue, no `stop_event`, no per-session lock, no lookahead, no abort task).

```
src/tibios_ray/engines/
  __init__.py   MOD   also re-exports the two Backends, InferenceSessionLike, TokenizerLike, ONNXRUNTIME_BACKEND_ID
  onnxrt.py     NEW   both Protocols, both default factories, _OnnxResidency, _OnnxBackendBase, the two Backends
```

Layer direction unchanged: `runtime -> capabilities -> selection -> backends`, plus the existing `engines -> backends` edge. Nothing imports `engines/` in production yet — no composition root exists.

## The Canonical Boundary / Data Flow (OR1)

LC1 is inherited unchanged; only ③ and ④ change shape, and ④ changes *modality* for the first time:

```
Embedding / Rerank Provider ──①──▶ Model Selection Policy ──②──▶ ResolvedModelRef ──③──▶ ONNX Runtime Engine ──④──▶ Sequence[Vector] | Sequence[RerankResult] ──⑤──▶ Worker Runtime ──⑥──▶ gRPC unary
```

| # | Boundary | What crosses | What MUST NOT cross | Built here? |
|---|---|---|---|---|
| ③ | ResolvedModelRef → ONNX Engine | `ServingPlanLike` (structurally: `.backend -> BackendId`) into `supports()`/`acquire()`; plus the **Artifact Bundle** supplied out of band at construction (OR10) | Model-selection logic; execution-provider choice made *by* the adapter; any `ExecutionContext`/gRPC type | **Yes** — entry half |
| ④ | ONNX Engine → results | `Sequence[Vector]`, `Sequence[RerankResult]` — plain floats and ints | `onnxruntime` objects, `InferenceSession`, `NodeArg`, numpy arrays, tokenizer objects, token ids, `BackendSession` internals, the refcount | **Yes — the entirety of this change** |

⑤⑥ do not execute yet: `EmbeddingProvider`/`RerankProvider` still raise `NoBackendAvailableError` (out of scope, both predecessors' deferral).

```
 ┌─ OnnxEmbeddingBackend ──┐   ┌─ OnnxRerankBackend ──┐
 │  embed(sess, inputs)    │   │  rerank(sess, q, ds) │      ← the ONLY public difference (OR5)
 └──────────┬──────────────┘   └──────────┬───────────┘
            └───────── _OnnxBackendBase ──┘   (private, never exported, never a Protocol edge)
                              │
        backend_id / supports(plan)  → plan.backend == ONNXRUNTIME_BACKEND_ID       (LC12/VL4)
        acquire / release  ─▶ async with self._lock ─▶ ┌─ _OnnxResidency ─────────┐
                              construct-or-reuse       │  session: …SessionLike   │
                              refcount ±1              │  tokenizer: TokenizerLike│
                              teardown at 0            │  input_names: frozenset  │
                                                       │  refcount: int           │
                                                       └──────────────────────────┘
        _infer(sess, texts, pairs)  ── NO LOCK (OR3) ──▶ await asyncio.to_thread(       ← ONE hop (OR7)
                                                            tokenize → session.run → extract rows)
```

## Architecture Decisions

| # | Decision | Alternatives rejected | Rationale |
|---|---|---|---|
| **OR2** | **Residency is shared and refcounted** — one `_OnnxResidency` (session + tokenizer + declared input names) per Backend instance, `refcount`/single-flight/teardown-at-zero reusing **VL2, VL6, VL13 verbatim**. `_sessions: dict[session_id, _OnnxResidency]` records borrows | LC2/LC3's one-engine-per-`acquire()`; a module-global session registry; extra fields on `BackendSession` | Decided by an engine property, not by precedent. LC3 existed because `llama_cpp.Llama` owns a **KV cache and context** — per-conversation mutable state that must not interleave, so isolation was worth a full reload per session. `InferenceSession` owns **no per-request state at all**: weights are read-only, `run()` is a pure function of its `input_feed`, there is nothing to isolate. Per-acquire would therefore pay three costs for zero benefit — duplicated weights in RAM/VRAM, a duplicated intra-op **thread pool per session** (ORT sizes one per session; N sessions oversubscribe the CPU), and seconds of graph-optimization + EP-init latency on every `acquire()`. The shape matches vLLM's, but the *reason* does not: vLLM shares because batching requires it; ORT shares because statelessness makes sharing free. Same consequence as VL2, stated honestly: residency is **per-Backend-instance, not per-process** |
| **OR3** | **The lock guards residency transitions only. `run()` is called with no lock held, from an arbitrary thread, concurrently across sessions** | LC4's per-session lock around execution; a process-wide `threading.Lock` around `run()`; a semaphore bounding in-flight runs | This is the inversion of LC4 for a *different* reason than VL5. vLLM refused the lock for throughput (serializing defeats continuous batching). ORT refuses it for **correctness economics**: ORT documents `Run()` as thread-safe on a shared session — concurrent `Run()` calls on one session are the officially recommended usage — and the Python binding releases the GIL for the duration of the native call, so off-loop concurrency is real parallelism, not merely loop-liveness. A lock would convert a documented-parallel engine into a serial one and make every `embed()` queue behind every other, for a safety property ORT already provides. What is *not* shared and *not* thread-safe is session **construction/mutation** (`SetProviders`, session-option mutation) — which is exactly what `self._lock` already covers under OR2 |
| **OR4** | **OR3's thread-safety claim is load-bearing, so it is discharged by evidence, not by docstring: (a) the opt-in integration smoke issues two genuinely concurrent `run()` calls against a real session and asserts both complete with correct results; (b) if some execution provider ever proves unsafe, the fix is a caller-supplied locking decorator satisfying `InferenceSessionLike`, never a branch inside the Backend** | Pre-emptively locking "to be safe"; branching on `providers` inside `_infer`; asserting per-EP safety in the design and moving on | The proposal's highest-severity risk is "assumed concurrent-`run()` safety is wrong for *some* EP", and it is right to distrust it: CPU EP is genuinely parallel; **CUDA EP is safe but serializes on the session's single compute stream**, so concurrency there buys latency-hiding, not device throughput; CUDA-graph capture and some non-target EPs (DirectML historically) impose stricter single-run rules. The design is built so being wrong is *cheap and local*: the session arrives through a factory seam, so a serializing wrapper (`threading.Lock` around `run()`, held on the worker thread, never on the loop) restores safety in ~8 lines **outside** this module and outside `backends/`. The Backend stays EP-ignorant — the same boundary LC12 draws for model selection, applied to hardware selection. **Verified post-design** (this phase had no network tool): an ONNX Runtime maintainer confirms in [microsoft/onnxruntime#10107](https://github.com/microsoft/onnxruntime/discussions/10107) that `Run()` is thread-safe on a shared session, and maintainers explicitly recommend *one session shared across threads* over one session per thread ("creating multiple sessions for each thread is a huge waste of resources and this is strongly discouraged" — separate arena allocators per session waste memory). C++ confirmation in [#14073](https://github.com/microsoft/onnxruntime/discussions/14073): concurrent `Run()` calls from different threads are safe, weights are shared. The only adjacent hazard found ([#26610](https://github.com/microsoft/onnxruntime/issues/26610)) is a *different* shape entirely — multiple independent sessions, each on its own thread, sharing one CUDA `device_id`, crashing at construction/init — not this design's shared-single-session pattern; it reinforces OR2 (share the session) rather than undermining OR3. **For `apply`: cite these two discussion links in the module docstring** |
| **OR5** | **Two classes, one private base.** `OnnxEmbeddingBackend` implements only `embed`; `OnnxRerankBackend` implements only `rerank`; both inherit residency from a private `_OnnxBackendBase` in the same module | One class implementing both protocols; two classes with a duplicated residency implementation; composition with four forwarding methods | OQ2's own stated criterion decides it, in the negative: **`supports()` cannot distinguish the modalities.** `ServingPlanLike` exposes only `.backend`, and `onnxruntime` is advertised by *four* capability descriptors — embedding, rerank, speech, OCR. So `supports()` returns `True` identically for all of them, and the **static protocol type is the only remaining discriminator**: `EmbeddingProvider` looks up an `EmbeddingBackend`, `RerankProvider` a `RerankBackend`. A single class implementing both would destroy that last discriminator (it matches both lookups) *and* the type would lie about the artifact — one instance holds one session, and an embedding encoder's graph is not a cross-encoder's graph, so `rerank()` on an embedding session yields a shape error or silent garbage. Sharing via a private base is not D1's prohibition (that bans inheriting the **Protocol**), and VL's "rule of three" caution was about coupling **across modules** through a foreign SDK's namespace — this is one module, one SDK, one mechanism, never exported. Composition was rejected as four forwarding methods creating an indirection that is not a seam, since the host is private either way |
| **OR6** | **The tokenizer is a second injected seam and part of residency**: `tokenizer_factory: Callable[[str], TokenizerLike]`, constructed inside the same `acquire()` critical section as the session, dropped with it at refcount zero. `TokenizerLike` mirrors the real `PreTrainedTokenizerBase.__call__` signature | Lazily loading the tokenizer at first `embed()`; hiding it behind an `Encoder = Callable[[Sequence[str]], Mapping[str, Any]]` seam in *our* vocabulary; the lighter `tokenizers` (Rust) package in the default factory; tokenizing in `backends/` | VL8's two-seam precedent transfers exactly, including its rejection of the wrapper: reshaping the seam into our vocabulary makes the Protocol stop resembling the SDK, which makes stub divergence **worse**, since the integration test would no longer validate the shape the stub imitates. Binding the tokenizer to residency is what makes the artifact-pair invariant enforceable at all — model and tokenizer must match, so they must share one lifetime; a lazily-loaded tokenizer would be a second lifecycle to reason about for no gain. The decisive secondary effect: with `return_tensors="np"`, **the tokenizer is the only numpy producer in the module**, so `onnxrt.py` never imports numpy and never constructs an array — outputs are read back through plain indexing and `float()`. That is precisely why `tokenizers` (which returns `Encoding` objects) was rejected for the default factory: it would force array assembly, and numpy, into `onnxrt.py` |
| **OR7** | **One `asyncio.to_thread` per call, spanning tokenize → `run()` → row extraction.** No pump thread, no queue, no `stop_event` | Calling `session.run` inline (proposal's stated High risk); LC6-LC10's pump-thread machinery; two `to_thread` hops (one for tokenization, one for `run`) | LC6-LC10 exist to move *a stream* across a thread boundary with backpressure — items arriving incrementally, a consumer that may abandon mid-flight. `embed`/`rerank` are single-shot request/response: one call in, one fully-formed result out, explicitly non-streaming in both protocols. `to_thread` is the whole bridge. Both tokenization (fast tokenizers are native and release the GIL) and `run()` are blocking native work, so putting them in **one** hop means a single context-switch pair and one unambiguous statement — "the synchronous span is entirely off-loop" — instead of a half-off-loop story with a gap in the middle. Accepted and documented: `to_thread` uses the loop's default executor (`min(32, cpu+4)` threads), so unbounded concurrent calls can saturate it; a request scheduler is out of scope |
| **OR8** | **The input feed is filtered against `session.get_inputs()`**: only tokenizer keys the graph actually declares are passed | Passing the tokenizer output verbatim; hardcoding `("input_ids", "attention_mask", "token_type_ids")`; making the key set a construction argument | Not defensive programming — a real, common failure. HF tokenizers emit `token_type_ids` for BERT-family configs; many exported ONNX graphs (distil/roberta-family, or exports that pruned it) declare only two inputs, and ORT **raises on an unexpected input name**. Hardcoding the triple gets it wrong in the other direction (models with `position_ids`). The graph itself is the authority, it is queryable for free at `acquire()` time, and caching the frozen name set in `_OnnxResidency` keeps `run()`'s hot path a set intersection. It also gives `InferenceSessionLike` a second method, which keeps the stub honest about more of the real surface |
| **OR9** | **Output contract: read `outputs[0]` (or the `output_name` selected in the Artifact Bundle) and require it to be 2-D `[batch, N]`.** `embed()` → row *i* becomes `Vector(values=tuple(float(x) for x in row))`; `rerank()` → `RerankResult(index=i, score=float(row[0]))`. A non-2-D result raises `OnnxOutputShapeError` naming the fix. **The adapter never pools and never normalizes** | Mean-pooling `last_hidden_state` over the attention mask inside the adapter; auto-detecting the first rank-2 output; a `pooling` strategy enum; returning raw hidden states | Pooling strategy (mean vs CLS vs max, L2-normalize or not) is **model metadata**, not engine behavior — it lives in the artifact's `sentence-transformers` config, which nothing here resolves. Implementing it would force one strategy on every model (silently wrong, and silently *plausible*, for CLS-pooled ones) and would drag numpy into the module, undoing OR6. One rule serves both modalities: a rectangular 2-D result makes "one `Vector` per input, all of equal length" and "one `RerankResult` per document" structural facts rather than assertions, and `index=i` by position makes order-preservation true by construction. The refusal is the honest failure mode: a 3-D `last_hidden_state` means the operator must point `output_name` at a pooled output or re-export — a message the error text must say outright. Auto-detection was rejected as magic that guesses at the operator's intent |
| **OR10** | **The Artifact Bundle: every artifact and hardware fact is a construction argument** — `model_path`, `tokenizer_path`, `providers: Sequence[str] = ("CPUExecutionProvider",)`, `output_name: str \| None = None`, plus the two factories. **`ServingPlanLike` gains no field, and `supports()` consults none of them** | A `ServingPlanLike.execution_provider` / `.providers` field; a global EP-selection policy module; letting the default factory inherit ORT's implicit provider list; deriving the tokenizer path from `model_path` by convention | LC12/VL4's boundary rule applied to a second kind of choice: an Engine never performs **selection** — not of models (LC12), and not of hardware. An EP is a deployment fact about the process, exactly like llama.cpp's `model_path` and vLLM's `model`, so it arrives the same way, and widening `ServingPlanLike` is a `backends/` contract change the proposal puts out of scope besides. The explicit CPU default matters: ORT's implicit list depends on which wheel is installed (`onnxruntime` vs `onnxruntime-gpu`), so inheriting it makes behavior change silently with the environment — the default must be deterministic and CUDA must be opted into. Naming these four together is the point: they are **one debt, not four**, all discharged by the same future change that resolves `ResolvedModelRef` into a servable artifact set — which now has a concrete shape to produce. Path-by-convention was rejected because the two artifacts genuinely ship separately |
| **OR11** | **No cancellation support. A cancelled `embed()`/`rerank()` leaves its worker thread running to completion; the result is discarded** | Threading `RunOptions.terminate` through the seam; wrapping in `asyncio.shield`; a VL11-style scheduled finalize task | `asyncio.to_thread` cannot cancel a running thread — that is a fact of the bridge, not a choice. What differs from VL11 is the *payload* of doing nothing: an orphaned vLLM request holds KV-cache blocks until aborted (a real leak, which is why VL11 exists), whereas an orphaned ORT `run()` holds only its own arena for a bounded, non-streaming call and mutates nothing shared — it is inert, not leaked. LC5's discipline still holds trivially: there is no `finally` doing async work, because there is nothing to clean up. The future path is named so it is not rediscovered: ORT's `RunOptions.terminate` flag can abort an in-flight `Run`, and adding it means widening `InferenceSessionLike` with a third method — worth doing when a caller can actually cancel, which requires the Worker Runtime wiring that does not exist yet |

### Accepted, explicit limitations

- **Artifact resolution is out of band (inherited debt, OR10).** `supports()` cannot verify this adapter serves `plan.model`, and nothing verifies that `model_path` and `tokenizer_path` are a *matching* pair — a mismatch produces garbage vectors, not an error. Documented in-module (GGUF-path precedent, LC12/VL3).
- **Residency is per-Backend-instance, not per-process (OR2/VL2).** Two `OnnxEmbeddingBackend` instances load the model twice; "one instance per family per modality" is a composition-root obligation that does not exist yet. An embedding Backend and a rerank Backend never share a session — correctly, since they are different graphs.
- **No pooling, no normalization (OR9).** Artifacts exporting only `last_hidden_state` are rejected, not silently mean-pooled.
- **No batching policy.** Every call is one `run()` with the full input sequence; a huge `inputs` list is one huge tensor. Dynamic batching and a request scheduler are out of scope.
- **The stub cannot prove the real SDK signature** (VL8's caveat, unchanged): `run(output_names, input_feed)`'s real shape, numpy I/O, `get_inputs()`'s `NodeArg`, and `AutoTokenizer`'s real return type are proven only by the opt-in integration smoke. Keep it runnable.
- **The CUDA EP is untested here.** OR4's escape hatch is designed, not exercised; the smoke runs CPU.

## Key Contracts

```python
class NodeArgLike(Protocol):
    @property
    def name(self) -> str: ...                               # OR8: the graph is the authority

class InferenceSessionLike(Protocol):
    """Structural shape of `onnxruntime.InferenceSession` — the only SDK surface used."""
    def get_inputs(self) -> Sequence[NodeArgLike]: ...
    def run(
        self, output_names: Sequence[str] | None, input_feed: Mapping[str, Any]
    ) -> Sequence[Any]: ...                                  # OR3: called off-loop, unlocked

class TokenizerLike(Protocol):
    """Structural shape of `PreTrainedTokenizerBase.__call__` (OR6). `text_pair`
    is what makes cross-encoder rerank possible; `return_tensors="np"` is what
    keeps numpy out of this module."""
    def __call__(
        self,
        text: Sequence[str],
        text_pair: Sequence[str] | None = None,
        *,
        padding: bool = True,
        truncation: bool = True,
        return_tensors: str = "np",
    ) -> Mapping[str, Any]: ...

type SessionFactory = Callable[[str, Sequence[str]], InferenceSessionLike]   # (model_path, providers)
type TokenizerFactory = Callable[[str], TokenizerLike]                       # (tokenizer_path)
```

Both defaults are lazy `importlib.import_module` implementations (LC11/VL8 inherited verbatim, same `reportMissingImports`/`reportUnnecessaryTypeIgnoreComment` pincer): `onnxruntime.InferenceSession(model_path, providers=list(providers))` and `transformers.AutoTokenizer.from_pretrained(tokenizer_path)`.

The one execution path, shared by both modalities (OR7/OR8/OR9):

```python
async def _infer(self, session, text, text_pair) -> Sequence[Sequence[float]]:
    residency = self._residency_for(session)                 # UnknownSessionError (LC2 inherited)

    def _blocking() -> Sequence[Sequence[float]]:            # ← the entire synchronous span
        encoded = residency.tokenizer(text, text_pair, padding=True,
                                      truncation=True, return_tensors="np")
        feed = {k: v for k, v in encoded.items() if k in residency.input_names}   # OR8
        outputs = residency.session.run(self._output_names, feed)                 # OR3: no lock
        return _rows(outputs[0])                             # OR9: 2-D or OnnxOutputShapeError

    return await asyncio.to_thread(_blocking)                # OR7: one hop, no pump thread
```

`embed()` calls `_infer(session, list(inputs), None)` and maps rows to `Vector`; `rerank()` calls `_infer(session, [query] * len(documents), list(documents))` and maps `row[0]` to `RerankResult(index=i, ...)`. Empty input returns an empty sequence without touching the session.

## Testing Strategy

Strict TDD. No `pytest-asyncio` — async assertions use `asyncio.run(...)` inside sync tests, matching the existing suite. **The stubs are the entire SDK**: unit tests never import `onnxruntime`, `transformers`, or numpy, and touch no model files, no network, no GPU. The stub tokenizer returns plain `list[list[int]]`; the stub session returns plain nested lists — which also proves OR9's extraction is duck-typed, not numpy-bound. Nothing sleeps; waits are `threading.Barrier`/`Event` under bounded timeouts.

| Decision | What a test asserts | Approach |
|---|---|---|
| — | Protocol conformance | Typed bindings `_e: EmbeddingBackend = OnnxEmbeddingBackend(...)`, `_r: RerankBackend = OnnxRerankBackend(...)` — pyright verifies structurally (CP7/LC/VL precedent). Plus a negative: `OnnxEmbeddingBackend` has **no** `rerank` attribute (OR5's discriminator is real) |
| LC11 | SDK-free import | After `import tibios_ray.engines.onnxrt`, assert `onnxruntime`, `transformers`, **and `numpy`** absent from `sys.modules` (OR6's stricter claim) |
| LC12/OR5 | `supports()` | `True` for `BackendId("onnxruntime")` on **both** classes; `False` for `llama_cpp`/`vllm`. Explicitly asserts both classes answer identically — the documented reason two classes exist |
| OR2 | One session across N sessions | Three `acquire()`s → three distinct `session_id`s, session-factory invocation counter **exactly 1**, tokenizer-factory counter exactly 1 |
| OR2/VL6 | Single-flight under concurrency | `asyncio.gather` of two `acquire()`s with a factory parked on a `threading.Event` set by a third task → factory counter exactly 1 |
| OR2/VL13 | Teardown at zero; double release | Two acquires, release one → session not closed; release the second → closed once. Second `release()` of the same session raises `UnknownSessionError`; next `acquire()` builds a fresh session (counter 2) |
| **OR3** | **Concurrent `run()` on one shared session** | Two sessions from one Backend; stub `run()` blocks on a `threading.Barrier(2)` under a bounded timeout; `asyncio.gather(embed(s1, …), embed(s2, …))`. Both must *enter* `run()` before either exits. A lock anywhere on the path makes the barrier time out. This is the OQ1 proof the proposal demands |
| **OR7** | **Provably off the event loop** | Stub `run()` blocks on a `threading.Event`; a concurrent coroutine increments a counter in a bounded loop; assert it advanced **before** the event is set, then set it and assert the result is still correct. Zero timing dependence, no sleeps |
| OR8 | Input filtering | Stub tokenizer emits `token_type_ids`; stub session declares only `input_ids`/`attention_mask` → the recorded feed has exactly two keys. Reverse case: a session declaring an input the tokenizer never emits is simply absent, not synthesized |
| OR9 | Shape and order | 2-D stub output → one `Vector` per input, in input order, all equal length; values match the stub rows exactly. 3-D output → `OnnxOutputShapeError`. Rerank: one `RerankResult` per document, `index` is `0..n-1` in order, `score` equals column 0. Empty input → empty result, `run` never called |
| OR9/OR10 | `output_name` selection | Constructed with `output_name="sentence_embedding"` → the stub records that name in `output_names`; default `None` → `None` passed through and `outputs[0]` read |
| OR6 | Rerank pairs the query | Stub tokenizer records its arguments: `text == [query] * len(documents)` and `text_pair == documents` |
| OR11 | Cancellation is inert | Cancel the awaiting task mid-`run()`; assert `CancelledError` propagates, the session is untouched afterwards, and a subsequent `embed()` on the same session returns correct results |
| OR10 | Providers reach the factory, not `supports()` | Recording factory asserts `("CPUExecutionProvider",)` by default and a custom tuple when supplied; `supports()` behavior is identical for both |
| OR1/LC12 | Layering | `test_engines_layering.py` already globs the package; bump the vacuity guard `>= 3` → `>= 4` |
| — | Package exports | `test_engines_exports.py` gains the new names |
| Integration | **The stubs are not lying** | `tests/integration/test_onnxrt_smoke.py`, `pytestmark = skipif(TIBIOS_RAY_ONNX_MODEL/…_TOKENIZER unset)`. Real factories, public API only: `embed()` over 3 texts → 3 equal-length vectors; `rerank()` → 3 ordered results; **two `asyncio.gather`-ed `embed()` calls on one shared session both succeed with identical results to their serial runs (OR3/OR4's empirical discharge)**; `release()` clean |

## File Changes

| File | Action | Description |
|---|---|---|
| `src/tibios_ray/engines/onnxrt.py` | Create | `InferenceSessionLike`, `NodeArgLike`, `TokenizerLike`, both default factories, `UnknownSessionError`, `OnnxOutputShapeError`, `ONNXRUNTIME_BACKEND_ID`, private `_OnnxResidency`/`_OnnxBackendBase`/`_rows`, `OnnxEmbeddingBackend`, `OnnxRerankBackend` |
| `src/tibios_ray/engines/__init__.py` | Modify | Re-export the two Backends, both Protocols, `ONNXRUNTIME_BACKEND_ID`; extend `__all__` |
| `pyproject.toml` | Modify | `onnx = ["onnxruntime>=…", "transformers>=…"]`; verify cp314 wheels at apply and add a `python_version` marker **only if** resolution actually fails (vllm marker precedent) |
| `tests/unit/engines/stub_onnx.py` | Create | `StubInferenceSession`, `StubNodeArg`, `StubTokenizer` (`stub_llama.py`/`stub_async_llm.py` precedent) |
| `tests/unit/engines/test_onnxrt_{conformance,supports,sdk_free,residency,concurrency,embed,rerank,artifacts}.py` | Create | See Testing Strategy |
| `tests/unit/engines/test_engines_exports.py` | Modify | New names |
| `tests/unit/engines/test_engines_layering.py` | Modify | Vacuity guard `>= 3` → `>= 4` |
| `tests/integration/test_onnxrt_smoke.py` | Create | Opt-in real-model smoke, env-var gated |
| `openspec/specs/backend-adapter/spec.md` | Modify | Modality-agnostic contract phrasing (delta authored by `sdd-spec`) |
| `src/tibios_ray/backends/{embedding,rerank,adapter}.py` | Untouched | Protocols already final; `ServingPlanLike` gains nothing (OR10) |
| `tests/unit/backends/test_no_engine_imports.py` | Untouched | `"onnxruntime"` already in `FORBIDDEN_ENGINE_MODULES`; guard already recursive |

`UnknownSessionError` is redefined module-locally again (VL's rationale, unchanged). **This is the third occurrence — the rule of three is now met.** Extracting `engines/errors.py` is deliberately deferred to its own change rather than smuggled into this one; the trigger is recorded here so it is not lost.

## Slice Plan

Two chained PRs (`auto-chain`, ~550-650 lines total), each green under `uv run pytest && uv run ruff check && uv run pyright`:

| # | Slice | Adds |
|---|---|---|
| 1 | Seams + residency | `onnxrt.py` with both Protocols, both default factories, `_OnnxResidency`, `_OnnxBackendBase` (`backend_id`/`supports`/`acquire`/`release`), OR2/OR6/OR10; both public classes present with their execution method raising `NotImplementedError`; conformance, supports, SDK-free, residency, single-flight, teardown, double-release, provider-plumbing tests; layering bump; `__init__` re-exports + exports test; `onnx` extra. The `backend-adapter` spec delta lands here |
| 2 | Execution | `_infer`, `embed`, `rerank`, `_rows`, `OnnxOutputShapeError`, OR3/OR7/OR8/OR9/OR11; concurrency, off-loop, filtering, shape/order, `output_name`, rerank-pairing, cancellation tests; opt-in integration smoke |

## Migration / Rollout

No migration. Additive except three edits (`pyproject.toml` extra, `engines/__init__.py` re-exports, layering vacuity bump) and one spec formalization. No contract fields, Provider, or runtime behavior change: `EmbeddingProvider`/`RerankProvider` raise `NoBackendAvailableError` before and after, `llamacpp-text-backend` and `vllm-text-backend` are untouched, and nothing constructs these Backends in production until a composition root exists. `git revert` of the slice commits restores the archived `vllm-backend` state exactly.

## Open Questions

- [x] **OR3's thread-safety claim, verified post-design** via WebSearch against ONNX Runtime maintainer discussions ([#10107](https://github.com/microsoft/onnxruntime/discussions/10107), [#14073](https://github.com/microsoft/onnxruntime/discussions/14073)): `Run()` on a shared session across threads is confirmed thread-safe and is the officially recommended pattern (one session per thread is explicitly discouraged as wasteful). `apply` MUST cite these links in the module docstring; the integration smoke (OR4) remains the empirical proof for this environment. The one adjacent GitHub issue found ([#26610](https://github.com/microsoft/onnxruntime/issues/26610)) describes a different failure mode (multiple independent sessions on one CUDA device) that does not apply to this design's single-shared-session shape.
- [ ] **Per-EP concurrency behavior beyond CPU (OR4).** CUDA is confirmed safe but serializes on one compute stream (concurrency hides latency, not device throughput); TensorRT/DirectML are unexamined. Belongs to whichever change first ships a GPU deployment, not here.
- [ ] **Pooling (OR9).** The moment a required artifact exports only `last_hidden_state`, someone must decide where mean-pooling lives — a fourth seam, an export-time obligation, or a numpy dependency in `engines/`. This design deliberately refuses rather than guesses.
- [ ] **Who owns "one Backend instance per family per modality" (OR2)?** The composition root, which does not exist. Documented, not enforced.
- [ ] **Artifact-pair validation (OR10).** Nothing checks that model and tokenizer match. The future `ResolvedModelRef` resolution must produce the bundle atomically, or this stays a silent-garbage failure mode.
- [ ] **Executor saturation (OR7).** `to_thread`'s default pool bounds real concurrency at `min(32, cpu+4)`. Fine for the current zero-caller state; the request scheduler inherits it.
- [ ] **`engines/errors.py` extraction.** Rule of three met by this change; deferred to its own change on purpose.
