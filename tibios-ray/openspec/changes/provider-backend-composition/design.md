# Design: Provider-Backend Composition

Change: `provider-backend-composition` · Artifact store: openspec (file).
Extends — never renumbers — the frozen decisions **D1-D7** (`ray-worker-runtime`), **CP1-CP8** (`capability-providers`), **MC1-MC14** (`model-catalog`), **LC1-LC12** (`llamacpp-backend`), **VL1-VL14** (`vllm-backend`), **OR1-OR11** (`onnx-runtime-backend`), **D8-D17** (`worker-context-wiring`). New decisions here are **D18-D29**.

> **D17 boundary verified, not assumed.** `openspec/changes/archive/2026-08-07-worker-context-wiring/design.md:4` states verbatim: *"New decisions here are **D8-D17**"*, and its `ARCHIVE-REPORT.md:26` heading reads *"Architecture Decisions (D8-D17)"*. No archived design defines a `D18`. The proposal's claim holds.

[ADR-0001](../../../docs/adr/0001-provider-backend-composition.md) (ownership), [ADR-0002](../../../docs/adr/0002-provider-backend-selection-delegation.md) (selection delegation), [ADR-0003](../../../docs/adr/0003-backend-resource-ownership.md) (resource ownership) and [ADR-0004](../../../docs/adr/0004-capability-request-boundary.md) (request boundary) are ground truth. This document picks mechanisms that satisfy them; it never re-justifies them.

## Technical Approach

Three wired Providers gain exactly two injected fields and a real `execute()`. Everything they need that is *not* capability-specific — model-reference selection, backend resolution, report construction — lives in module-level pure functions in a new `capabilities/dispatch.py`, so each Provider body stays roughly twenty lines of its own modality and the "no selection logic" guard has almost nothing to police.

Two seams are net-new and carry the change's weight: `config.py` (the only reader of process configuration) and `selection/preference.py` (the first concrete `ModelSelectionPolicy`). `worker.py` becomes the single module that names a concrete engine class.

```
src/tibios_ray/
  config.py                 NEW   env-var surface; per-engine artifact + sizing values
  capabilities/requests.py  NEW   CapabilityRequest Protocol + Chat/Embedding/RerankRequest (ADR-0004)
  capabilities/dispatch.py  NEW   model-ref selection, backend resolution, report builders
  capabilities/errors.py    MOD   ProviderExecutionError family (D21)
  capabilities/{chat,embedding,rerank}.py  MOD  two fields each, real execute()
  selection/preference.py   NEW   PreferenceOrderPolicy — the first concrete policy
  selection/errors.py       NEW   UnsatisfiablePlanError (selection/ may not import capabilities/)
  engines/llamacpp.py       MOD   pool of N pre-warmed Llama instances (ADR-0003)
  worker.py                 MOD   the real Composition Root
```

Layer direction unchanged: `runtime -> capabilities -> selection -> backends`, with `engines -> backends`, and `worker.py` sitting above all of them as the only importer of `engines/`.

## Data Flow

```
build_runtime(config)                         ← the ONLY reader of config.py, the ONLY namer of engine classes
   │  config absent per engine → engine not built → BackendId absent from the mapping (capability unwired)
   ▼
ChatProvider(backends={llama_cpp: …, vllm: …}, selection_policy=PreferenceOrderPolicy(…))
   │
   ▼  execute(context)
 ① ChatRequest.parse(context.execution_parameters)          RequestParseError            (ADR-0004, D22)
 ② resolve_model_ref(context)                               MissingModelDependencyError  (D20)
 ③ resolve_backend(backends, policy, model)                 NoBackendAvailableError │ UnresolvableBackendError
 ④ acquire(plan) → generate/embed/rerank → release(session) BackendExecutionError        (D21)
 ⑤ OutputChunk(data=…, sequence=n) on context.channel                                    (D24)
 ⑥ return ExecutionReport(COMPLETED | CANCELLED)  ← never FAILED; WorkerRuntime owns that (D21)
   ▼
WorkerRuntime.execute() → emits the one terminal EndOfStream, translates any raise to FAILED (D25)
```

## Architecture Decisions

| # | Decision | Alternatives rejected | Rationale |
|---|---|---|---|
| **D18** | **Wired Provider shape: `@dataclass(frozen=True, slots=True, kw_only=True)` with public fields `backends` and `selection_policy`. `__post_init__` normalizes the mapping via `object.__setattr__(self, "backends", MappingProxyType(dict(backends)))`. The ADR-0002 flow is executed through module-level pure functions in `capabilities/dispatch.py` — never an injected collaborator** | ADR-0002's literal `self._backends` private names; trusting the caller to pass an immutable mapping; a `ProviderBase` class or an injected `Dispatcher` object; inlining the flow three times | The spec's immutability scenario demands that adding/removing an entry *fails*, and a plain `dict` passed by a test would silently succeed — normalizing at construction makes the guarantee the Provider's own rather than the caller's, and `dict(...)` first means the Provider holds a snapshot the Composition Root cannot mutate afterwards. `object.__setattr__` in `__post_init__` is already this codebase's frozen-dataclass idiom (`ResolvedModelRef.__post_init__`). Underscore-prefixed names are dropped deliberately: ADR-0002's `self._backends` is pseudo-code, and on a frozen `slots=True` dataclass the underscore buys no protection while making the Composition Root's call site read `_backends=…`. Helpers are *functions in the same package*, not a third field: the injected-fields invariant (exactly two) and the "no service locator" rule both survive, and the three `execute()` bodies keep only the conditionals the spec allows |
| **D19** | **Configuration source is environment variables (Q7)** — `config.py` exposing frozen `LlamaCppConfig`/`VllmConfig`/`OnnxConfig` and a `WorkerConfig.from_env(env: Mapping[str, str] = os.environ)`. Names reuse the vocabulary already in the repo: `TIBIOS_RAY_LLAMACPP_GGUF`, `TIBIOS_RAY_LLAMACPP_POOL_SIZE`, `TIBIOS_RAY_VLLM_MODEL`, `TIBIOS_RAY_ONNX_{EMBEDDING,RERANK}_{MODEL,TOKENIZER,OUTPUT_NAME}`. Absent → `None` (engine skipped); present-but-incomplete or unparseable → raise at load | A structured TOML/YAML file; both with a defined precedence; `pydantic-settings`; a `.env` loader; deriving the tokenizer path from the model path | Decided against this repo's *actual* deployment shape, not a general preference. There is no `Dockerfile`, no compose file, no unit file, and no config file of any kind in the tree — the entire current deployment surface is `server.py:21`, `os.environ.get("TIBIOS_RAY_ADDRESS", …)`, plus a `python -m` entry point. The env vocabulary is not hypothetical either: `tests/integration/test_llamacpp_smoke.py:24`, `test_vllm_smoke.py:27` and `test_onnxrt_smoke.py:39-40` already read `TIBIOS_RAY_LLAMACPP_GGUF` / `TIBIOS_RAY_VLLM_MODEL` / `TIBIOS_RAY_ONNX_MODEL` + `_TOKENIZER`, and ADR-0003 itself names `TIBIOS_RAY_LLAMACPP_POOL_SIZE`. Adopting a file would invent a second, competing vocabulary for the same four artifacts and add a parser, a schema, a file-location search order, and precedence rules — all to describe **eight scalars**. A file's real advantages (lists, profiles, N instances per engine) buy nothing until an engine can serve more than one model, which is exactly the unresolved `ResolvedModelRef` → artifact-path debt (OR10/LC12) this change explicitly does not repay. The `env: Mapping[str, str]` parameter is the repo's standard factory seam (`LlamaFactory`, `SessionFactory`, `TokenizerFactory`): tests pass a dict, no `monkeypatch` needed. **Documented future path**, recorded so it is not rediscovered: when one engine must serve N models, the file becomes the source and env vars become per-key overrides (file < env), and `WorkerConfig` gains a second `from_file` constructor — no consumer changes, because the Composition Root already only sees `WorkerConfig` |
| **D20** | **Model reference selection (Q2): `dependencies[0]`, always. Zero entries raise `MissingModelDependencyError`. More than one uses the first and emits a `Warning` event naming the count** — implemented once, in `dispatch.resolve_model_ref(context)` | Requiring exactly one and rejecting N>1; scanning for a "model-shaped" entry; matching against the descriptor's families | The frozen spec settles the shape of the answer, and only one option fits all three of its scenarios: zero must fail explicitly, one must be *the* one, and with N>1 *"the same `ResolvedModelRef` is selected both times"* — a scenario that presumes a selection occurs, so rejecting N>1 would contradict it. `dependencies` is an **ordered** tuple by D10 and is converted order-preservingly by `worker-wire-conversion`, so index 0 is stable across processes, not an artifact of dict iteration. This also lands exactly where the predecessor design left it: `worker-context-wiring/design.md:289` records the interim rule verbatim — *"a Provider needing exactly one dependency takes `dependencies[0]`"*. The `Warning` (existing event type, `code="extra_dependencies"`) is what keeps the ignoring honest rather than silent, and it costs no new machinery. The residual N>1 ambiguity is a **wire-contract** gap (no dependency role/name field), not something a Provider may resolve by inspection |
| **D21** | **Failure taxonomy (Q6): one base, five subclasses, and cancellation deliberately outside the hierarchy.** `capabilities/errors.py` gains `ProviderExecutionError(Exception)` with `NoBackendAvailableError` (re-parented, unchanged signature), `UnresolvableBackendError`, `BackendExecutionError`, `MissingModelDependencyError`, `RequestParseError`. `selection/errors.py` adds `UnsatisfiablePlanError`. **A wired Provider returns a report only for `COMPLETED` and `CANCELLED`; every failure is a raise** that `WorkerRuntime._dispatch` already translates | Four independent unrelated types; keeping one catch-all error and distinguishing by message; a `*ParseError` per capability; returning a `FAILED` report from the Provider; letting the Backend's own exception propagate unwrapped | The spec requires four *behaviorally distinguishable* outcomes; this gives type-level distinction under a direct `execute()` (how conformance tests call it) and message-level distinction through the wire, since `_failed_report` sets `failure=str(error)` (`worker_runtime.py:55`). `errors.py`'s current docstring argues against a base class because *"there is exactly one catch site and exactly one error"* — that premise is precisely what this change breaks, so the base arrives with a caller that needs it, not as speculative indirection. Re-parenting is non-breaking: `NoBackendAvailableError` remains an `Exception` subclass, so `WorkerRuntime`'s bare catch and every existing `pytest.raises` still hold. `BackendExecutionError` **wraps** (`raise … from error`, carrying `backend`, `stage ∈ {acquire, execute, release}`, and `repr(error)` in the message) — the alternative leaves the FAILED report's `failure` string indistinguishable from an internal bug. Cancellation is *not* an exception, by D5: raising would unwind the stack and skip acknowledge → cleanup → final events → Report. `UnsatisfiablePlanError` lives in `selection/` because `selection/` must not import `capabilities/` |
| **D22** | **`capabilities/requests.py` holds the `CapabilityRequest` Protocol and all three Requests.** `ChatRequest(prompt, max_tokens, temperature=1.0, stop=())`, `EmbeddingRequest(inputs)`, `RerankRequest(query, documents)`. Validation is `parse()`'s alone; **unknown keys are ignored, malformed known keys are rejected**. One shared `RequestParseError(capability=…, parameter=…, reason=…)` | Defining each Request inside its own Provider module; a `capabilities/requests/` package; one exception type per capability; rejecting unrecognised keys; a defaulted `max_tokens`; carrying `messages` and templating them into a prompt | A single module keeps ADR-0004's *"lives exclusively there"* literally true, keeps the three wired Provider modules free of the parse conditionals the no-branching guard has to reason about, and matches `capabilities/`'s existing flat-module style (`names.py`, `descriptor.py`, `errors.py`). Three near-identical error subclasses would recreate exactly the indirection CP3 rejected — *which* capability failed is **data**, and `NoBackendAvailableError` already carries `capability=` as a kwarg for that reason. Ignoring unknown keys is not a relaxation of reject-don't-guess: that rule forbids *inventing values*, and failing on an additive producer-side key would break a backward-compatible `tibios-core` change. `max_tokens` is required because a default is a guessed generation budget with a cost; `temperature`'s default is `TextRequest`'s own documented default, inherited rather than invented. **`ChatRequest` carries `prompt: str`, not messages** — `TextGenerationBackend.generate()` takes `TextRequest(prompt: str, …)`, nothing below the Provider can apply a chat template, and synthesizing one in the Provider would be model-specific logic in the wrong layer *and* a hardcoded model assumption the `capability-providers` spec forbids. Message→prompt templating is named in Open Questions, not smuggled in |
| **D23** | **Quantization (Q4): no Backend acts on it, and that is structural, not a TODO.** The policy returns the documented sentinel `ARTIFACT_DEFINED = Quantization(scheme="artifact-defined", bits=0)`, meaning *"no runtime choice was made; the configured artifact is already quantized"*. A test asserts no `engines/` module reads `.quantization` | `acquire()` selecting a variant; `acquire()` raising when it cannot serve the requested quantization; widening `ServingPlanLike` with `.quantization`; a per-engine configured quantization declaration; leaving the question implicitly open | ADR-0002 defers this here, and the codebase answers it: `acquire(plan: ServingPlanLike)` receives a parameter type that exposes **only `.backend`** (`backends/adapter.py:50-56`), so a Backend structurally cannot read quantization without a `backends/` contract change this change puts out of scope, and `vllm.py:39-40` already states the consequence outright — *"Quantization never reaches the engine."* More importantly, acting on it would be meaningless today: for **all three** engines quantization is a property of the artifact chosen at construction (the GGUF file *is* its quantization; vLLM's is an `AsyncEngineArgs` fact; an ONNX graph is exported at a fixed precision), so a Backend given one model path has exactly one variant and nothing to select. Raising on mismatch was rejected for the same reason — it would compare a plan value against a fact the Backend does not possess. The sentinel is legitimate under `policy.py`'s own rule that `scheme` is *"an opaque token … Phase 3 does not own a closed vocabulary"*; `bits=0` reads as "not asserted", and a fabricated `"int4"` would be a lie about an artifact nobody inspected. Future path: the first Backend that can serve multiple quantized variants of one model adds `.quantization` to `ServingPlanLike` and either selects or raises — a `backends/` change with its own spec delta |
| **D24** | **Channel serialization (Q5): the codec is a property of the capability, which both ends already know from `ExecutionContext.capability`, so `data` needs no self-describing envelope.** Chat → raw UTF-8 bytes of each delta, one `OutputChunk` per non-empty `TextChunk`, `sequence` incrementing from 0. Embedding → **one** chunk, `sequence=0`, UTF-8 JSON `{"vectors": [[…], …]}`. Rerank → one chunk, `sequence=0`, UTF-8 JSON `{"results": [{"index": i, "score": s}, …]}` | Uniform JSON for all three (JSON-wrapping every token); msgpack/CBOR; protobuf `Any`; a length-prefixed custom struct; chunking the batch results; putting them on `ExecutionReport` | There is **no existing bytes-payload codec in this repo** to reuse — `rg` over `src/` finds `OutputChunk.data` only in `events.py`, and `transport/convert.py:408` passes it to the wire untouched; `json` is not imported anywhere today. The nearest precedent is therefore ADR-0004's own *"structured values are JSON-encoded"* at the request boundary, so JSON keeps one codec at both ends of the same request, in the stdlib, with no dependency. Chat is the deliberate exception: `{"text":"Hi"}` roughly triples the byte volume of every token and forces a JSON parse per delta, for structure a delta does not have — `sequence` already carries the only metadata (ordering) a token stream needs, and `TextChunk.text` is a `str`, so each chunk encodes to complete, valid UTF-8 with no risk of splitting a multi-byte character. The terminal `TextChunk(text="", finished=True)` emits **no** chunk: an empty payload carries nothing, and `EndOfStream` is the terminator. Batch results are one chunk because both protocols return the complete `Sequence` from one call — splitting would fabricate a stream that does not exist. JSON field names mirror `Vector.values` / `RerankResult.index,score` exactly, so the wire shape is derivable from the domain type |
| **D25** | **`WorkerRuntime` remains the sole emitter of the terminal `EndOfStream`. Providers emit `OutputChunk`s (and `Warning`s) only** | Each wired Provider emitting its own `EndOfStream`; removing the Runtime's emit; a "terminate only if not already terminated" flag | `worker_runtime.py:69` already emits `EndOfStream` after *every* dispatch outcome — success, failure and cancellation alike — and `runtime/` is out of scope by `proposal.md:23`. A Provider emitting one too would put **two** terminal markers on one execution's channel, contradicting `EndOfStream`'s own contract (*"no further `ExecutionEvent`s will be emitted"*) and D14's "Report is last" ordering. The spec's *"`OutputChunk`s terminated by `EndOfStream`"* is satisfied as a channel-observable outcome; only ownership of the emit is a design choice, and only one owner can be correct. **Consequence for tests:** a direct `execute()` call in a unit test sees chunks with no terminator; the terminator is asserted through `WorkerRuntime.execute()`, which is where it is produced |
| **D26** | **`LlamaCppTextBackend` pool: N pre-warmed `Llama` instances in an `asyncio.Queue`, built eagerly in `__init__`. `acquire()` = `await queue.get()` under `asyncio.timeout(acquire_timeout)`; `release()` = join the pump thread off-loop, then `put_nowait` the instance back. Exhaustion behaviour is **wait, then reject on a bounded timeout** (`TIBIOS_RAY_LLAMACPP_ACQUIRE_TIMEOUT_SECONDS`, documented default 30) raising `PoolExhaustedError`. Instances are never `close()`d — process lifetime (ADR-0001)** | Reject immediately when exhausted; wait forever; a `Semaphore` plus a shared instance list; constructing an (N+1)th instance under load | Rejecting immediately turns *transient* contention into a `FAILED` workload and makes the Worker perform admission control — a scheduling decision `18-worker-model.md` puts in the Runtime, not the Worker. Waiting forever is worse in the other direction: a Provider parked in `acquire()` polls no `CancellationToken`, so a saturated pool would make cancellation unobservable and a stuck request indistinguishable from a slow one. The bounded wait absorbs the common case and converts genuine saturation into a distinguishable, attributable failure. Because the timeout fires **inside** `acquire()`, no session exists and `release()` is correctly never called — exactly the spec's *"Release is not called when `acquire()` itself fails"*. `_Residency.lock` (LC4) is **kept** even though a checked-out instance is exclusively owned: it still prevents two concurrent `generate()` calls on one session from starting two pump threads on one `Llama`. `release()` no longer closes: closing would defeat the pool, and no explicit teardown path exists in the process (the ONNX precedent — dropping the reference is teardown) |
| **D27** | **Startup viability validation = eager construction of all N instances in `__init__`, preceded by two cheap deterministic pre-checks: `pool_size >= 1`, and `model_path` exists and is a readable file. No RAM/VRAM estimate. Failure propagates out of `build_runtime()` and the process exits** | A `pool_size × file_size` vs available-RAM check; `psutil`; reading `/proc/meminfo`; lazy construction with a warm-up ping; degrading N downward on failure | Eager construction *is* the strongest viability proof available, because it is the allocation itself: if the Nth load OOMs it OOMs at boot, which is precisely ADR-0003's *"fail fast rather than degrade or OOM later at request time."* A memory estimate would be a guess this repo's own rules forbid — GGUF file size is not resident footprint once context and KV cache are allocated, `n_ctx` is not configured here, and available-memory probing is platform-specific with no current dependency. The file pre-checks are worth their two lines because they turn the most common operator error (a typo'd path) into a one-line message instead of an SDK stack trace. Degrading N was rejected outright: silently serving at a concurrency the operator did not ask for is the "guess" failure mode this change exists to eliminate. **Accepted limitation:** boot time now scales with pool size and the gRPC port does not open until every instance is warm — arguably correct, since a half-warm Worker advertising capabilities it cannot serve is worse |
| **D28** | **`PreferenceOrderPolicy(preference: tuple[BackendId, ...])` in `selection/preference.py`: return the first `BackendId` in `preference` that is present in `constraints.available_backends`; if none matches, fall back to the lexicographically smallest `BackendId.value` in the set; if the set is empty, raise `UnsatisfiablePlanError`. Quantization is always `ARTIFACT_DEFINED` (D23)** | Iterating `available_backends` directly; sorting only; scoring by model size/family/cost; consulting the catalog; a policy that reads configuration | `available_backends` is a `frozenset`, whose iteration order is nondeterministic — `errors.py:32-35` already documents that exact hazard for `CapabilityDescriptor.backends` — so determinism requires an explicit total order, not a set traversal. The preference tuple is a **Composition Root output** (ADR-0002's shape), which is where a deployment's "prefer vLLM over llama.cpp on this box" belief belongs; the lexicographic fallback guarantees totality even for a `BackendId` the operator never ranked, so `plan()` can never return an unranked-and-therefore-arbitrary answer. Anything richer would be scoring, which the `model-selection-policy` spec forbids outright |
| **D29** | **`build_runtime(config: WorkerConfig \| None = None)` stays a plain function that constructs a fresh engine set per call; `None` means `WorkerConfig.from_env()`. "Constructed once at startup" is guaranteed by there being exactly one call in production (`server.py`), not by memoization. The construction-count test asserts *per `build_runtime()` call*: engines are built exactly once, never per request** | An `lru_cache`d or module-global singleton engine set; a `Backends` container built at import time; deleting the "independent registries" test | This is the tension `proposal.md:82` flags, and the resolution is D6's, unchanged: a memoized composition root is global mutable state, and it would make every test in the suite share loaded model weights and a live thread pool. `test_worker.py:23`'s `build_runtime() is not build_runtime()` therefore stays green untouched, and ADR-0001's "once at startup, lifetime of the process" stays true where it is actually claimed — of the running Worker, which calls `build_runtime()` exactly once from `server.py:22`. The per-request claim, which is the one ADR-0003 cares about, is what the counter test proves |

### Accepted, explicit limitations

- **`engines/vllm.py` and `engines/onnxrt.py` still construct their heavyweight resource on *first* `acquire()`** (VL2/OR2), not at Backend init as ADR-0003 requires. Only `llamacpp.py` is changed here, because ADR-0003 names it specifically and `proposal.md` puts the other engines out of scope. Closing the gap needs a `warmup()` seam on those Backends — an eager `acquire()`+`release()` at boot cannot do it, since refcount-zero release tears the resource straight back down (VL13/OR2). Recorded in Open Questions, not hidden.
- **Artifact resolution stays out of band** (LC12/VL4/OR10 debt, consumed not repaid): `supports()` still cannot verify the adapter serves `plan.model`, and nothing validates that an ONNX model/tokenizer pair actually match.
- **One `OutputChunk` per batch result means one large gRPC message** for a large embedding batch. Bounded by the transport's max message size; chunking is deferred until a real payload exceeds it.
- **ONNX execution-provider selection is not configurable here.** CPU only, per OR10's deterministic default.

## Key Contracts

```python
# capabilities/errors.py — D21
class ProviderExecutionError(Exception): ...
class NoBackendAvailableError(ProviderExecutionError):      # empty mapping, or an unwired Provider
    def __init__(self, *, capability: CapabilityName, provider: str) -> None: ...   # unchanged
class UnresolvableBackendError(ProviderExecutionError):     # plan.backend absent from the mapping
    def __init__(self, *, capability: CapabilityName, backend: BackendId,
                 available: tuple[str, ...]) -> None: ...   # sorted → stable message
class BackendExecutionError(ProviderExecutionError):        # raise … from error
    def __init__(self, *, backend: BackendId, stage: str, error: Exception) -> None: ...
class MissingModelDependencyError(ProviderExecutionError): ...
class RequestParseError(ProviderExecutionError):
    def __init__(self, *, capability: CapabilityName, parameter: str, reason: str) -> None: ...

# capabilities/requests.py — D22, ADR-0004
class CapabilityRequest(Protocol):
    @classmethod
    def parse(cls, parameters: Mapping[str, str]) -> Self: ...
```

| Request | Key | Required | Decoding | Rejected when |
|---|---|---|---|---|
| `ChatRequest` | `prompt` | yes | plain `str` | absent, or empty after strip |
| | `max_tokens` | yes | `int(value)` | absent, non-integer, `<= 0` |
| | `temperature` | no (`1.0`) | `float(value)` | non-float, `< 0` |
| | `stop` | no (`()`) | JSON array → `tuple[str, ...]` | invalid JSON, not an array, non-string element |
| `EmbeddingRequest` | `inputs` | yes | JSON array → `tuple[str, ...]` | absent, invalid JSON, not an array, empty, non-string element |
| `RerankRequest` | `query` | yes | plain `str` | absent, or empty after strip |
| | `documents` | yes | JSON array → `tuple[str, ...]` | absent, invalid JSON, not an array, empty, non-string element |

Every rejection raises `RequestParseError` naming the capability, the parameter and the reason. Unknown keys are ignored (D22).

```python
# capabilities/dispatch.py — D18/D20/D21, module-level functions, no state
async def resolve_model_ref(context: ExecutionContext, *,
                            capability: CapabilityName) -> ResolvedModelRef: ...
def resolve_backend[B](backends: Mapping[BackendId, B], policy: ModelSelectionPolicy,
                       model: ResolvedModelRef, *, capability: CapabilityName) -> tuple[B, ServingPlan]: ...
def completed_report(*, started_at: float, trace_id: str) -> ExecutionReport: ...
def cancelled_report(*, started_at: float, trace_id: str) -> ExecutionReport: ...

# config.py — D19. Every field None-able; None means "this engine is not configured".
@dataclass(frozen=True, slots=True, kw_only=True)
class WorkerConfig:
    llamacpp: LlamaCppConfig | None
    vllm: VllmConfig | None
    onnx_embedding: OnnxConfig | None
    onnx_rerank: OnnxConfig | None
    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Self: ...   # defaults to os.environ
```

The Composition Root's shape, and the only place a concrete engine class is named:

```python
def build_runtime(config: WorkerConfig | None = None) -> WorkerRuntime:
    config = config if config is not None else WorkerConfig.from_env()
    policy = PreferenceOrderPolicy(preference=_BACKEND_PREFERENCE)
    text: dict[BackendId, TextGenerationBackend] = {}
    if config.llamacpp is not None:
        text[LLAMA_CPP_BACKEND_ID] = LlamaCppTextBackend(...)      # eager pool build (D26/D27)
    if config.vllm is not None:
        text[VLLM_BACKEND_ID] = VllmTextBackend(model=config.vllm.model)
    ...
    providers = (ChatProvider(backends=text, selection_policy=policy), ...)
    return WorkerRuntime(CapabilityRegistry(providers))
```

## File Changes

| File | Action | Slice | Description |
|---|---|---|---|
| `src/tibios_ray/config.py` | Create | 1 | `WorkerConfig` + three per-engine configs, `from_env` (D19) |
| `src/tibios_ray/selection/{preference,errors}.py` | Create | 2 | `PreferenceOrderPolicy`, `ARTIFACT_DEFINED`, `UnsatisfiablePlanError` (D28/D23) |
| `src/tibios_ray/selection/__init__.py` | Modify | 2 | Re-export the new names |
| `src/tibios_ray/testing/{policy,text_backend,embedding_backend,rerank_backend}.py` | Create | 2 | Fakes following `RecordingBackend`'s shape; registered in `testing/__init__.py` `__all__` |
| `src/tibios_ray/capabilities/errors.py` | Modify | 3 | `ProviderExecutionError` family; docstring's CP3 rationale updated (D21) |
| `src/tibios_ray/capabilities/requests.py` | Create | 3 | `CapabilityRequest` + three Requests (D22) |
| `src/tibios_ray/capabilities/dispatch.py` | Create | 3 | Model-ref selection, backend resolution, report builders (D18/D20) |
| `src/tibios_ray/capabilities/chat.py` | Modify | 4 | Two fields, streaming `execute()` (D24) |
| `src/tibios_ray/capabilities/{embedding,rerank}.py` | Modify | 5 | Two fields, batch `execute()` (D24) |
| `src/tibios_ray/engines/llamacpp.py` | Modify | 6 | Pool, `PoolExhaustedError`, eager init, pre-checks (D26/D27) |
| `src/tibios_ray/worker.py` | Modify | 7 | Real Composition Root (D29) |
| `tests/unit/capabilities/test_provider_conformance.py` | Modify | 4/5/7 | Wired/unwired parameterization split |
| `tests/unit/capabilities/test_catalog_conformance.py` | Modify | 7 | No-branching scan narrowed to the four unwired modules, exemption list asserted |
| `tests/unit/{config,selection,capabilities,engines}/…`, `tests/unit/test_worker.py` | Create/Modify | all | See Testing Strategy |
| `src/tibios_ray/{runtime,transport,backends}/**`, `engines/{vllm,onnxrt}.py` | Untouched | — | No contract change; D25 depends on `worker_runtime.py` staying exactly as it is |

## Testing Strategy

Strict TDD, `uv run pytest`. No real SDK, no model files, no network: every Backend in a Provider test is a fake from `testing/`, and every engine test keeps its existing stub.

| Decision | What a test asserts |
|---|---|
| D18 | Wired Providers declare exactly `backends` + `selection_policy`; mutating `provider.backends` raises; mutating the dict passed to the constructor does not change `provider.backends` |
| D19 | Empty env → every config `None`; one engine configured → only it is non-`None`; ONNX model without tokenizer → raises; `POOL_SIZE="abc"`/`"0"` → raises; a configured path is returned byte-identical |
| D19 | `rg` guard: no module outside `worker.py`/`config.py` reads `os.environ` or imports `tibios_ray.config` |
| D20 | 0 deps → `MissingModelDependencyError`; 1 dep → that ref reaches `plan()`; 3 deps → `dependencies[0]` reaches `plan()` twice identically, and exactly one `Warning` with `code="extra_dependencies"` is emitted |
| D21 | Each of the five errors raised from its own trigger; `BackendExecutionError.__cause__` is the backend's exception and `.stage` distinguishes acquire/execute/release; cancellation returns `CANCELLED` and raises nothing |
| D22 | Table-driven: every Required/Rejected row above, plus "unknown key present → parse succeeds" |
| D23 | No file under `engines/` contains `.quantization`; `plan().quantization == ARTIFACT_DEFINED` |
| D24 | Chat: N non-empty deltas → N chunks, `sequence` 0..N-1, `data == text.encode()`, terminal empty delta emits nothing. Embedding/rerank: exactly one chunk, `json.loads(data)` round-trips the vectors/results in order. All three: no report field contains output |
| D25 | Direct `execute()` emits **no** `EndOfStream`; through `WorkerRuntime.execute()` exactly one exists and is last |
| D26 | Pool size N → factory called exactly N times at construction and never again across M > N acquires; N+1 concurrent acquires with N returned → the last one waits, then succeeds once one is released; with none released → `PoolExhaustedError` after the timeout and `release()` never called; `release()` returns the instance without calling `close()` |
| D27 | `pool_size=0` → raises; missing path → raises before the factory is called; a factory raising on the 2nd of 3 → construction raises and `build_runtime()` propagates |
| D28 | Deterministic across two identical calls; preference order honoured; unranked backend → lexicographic fallback; empty set → `UnsatisfiablePlanError`; the returned `backend` is always in `available_backends` |
| D29 | `build_runtime() is not build_runtime()` (unchanged); zero config → runtime returned, every wired Provider's mapping empty; one engine configured → exactly that `BackendId` present |
| Guards | `rg` for concrete engine imports finds only `worker.py`; existing layering/naming/`no_engine_imports` guards still zero |
| Release | Backend raises mid-stream → `release()` called exactly once with that session before the error propagates; `acquire()` raises → `release()` never called |

## Slice Plan

Seven chained PRs (`auto-chain`), each green under `uv run pytest && uv run ruff check && uv run pyright`. Total revised to **~1000-1300 hand-written lines** — above `proposal.md:115`'s 600-900, because that estimate predates the ADR-0003 pool work (slice 6) its own Affected Areas table omitted.

| # | Slice | Adds | Depends on |
|---|---|---|---|
| 1 | Config surface | `config.py`, `from_env`, absent/malformed rules, the `os.environ` guard | — |
| 2 | Policy + doubles | `selection/{preference,errors}.py`, `ARTIFACT_DEFINED`, four `testing/` fakes | — |
| 3 | Requests + taxonomy + dispatch | `capabilities/{requests,dispatch}.py`, `errors.py` family | 2 |
| 4 | ChatProvider | Streaming `execute()`, D24 chat codec, conformance split (wired half, chat only) | 3 |
| 5 | Embedding + Rerank | Both batch `execute()`s, D24 JSON codec, conformance split completed | 4 |
| 6 | llama.cpp pool | Pool, exhaustion, eager init, pre-checks, construction-count test | 1 |
| 7 | Composition Root | Real `build_runtime()`, catalog no-branching narrowing, end-to-end wiring tests | 1-6 |

Slice 6 is independent of 3-5 and may land in parallel.

## Migration / Rollout

No data migration, no feature flag. A deployment that sets no `TIBIOS_RAY_*` artifact variable behaves exactly as today — every capability fails as unwired, the process starts clean. Reverting the slice commits restores zero-field Providers, the zero-arg composition, and per-call `Llama` construction; `runtime/`, `transport/`, `backends/`, `engines/{vllm,onnxrt}.py` and `../proto/` are untouched, so nothing downstream of a Provider can regress.

## Spec Conformance Notes (for `sdd-verify`)

- **D25** and **D20** were resolved by correcting `provider-backend-composition/spec.md` itself (EndOfStream ownership assigned to `WorkerRuntime`; the dependency-count conditional added to the dispatch-mechanical allow-list) rather than by reinterpreting a `MUST` here — the design implements the spec as written, it does not explain around it.
- **D21** returns no `FAILED` report from a Provider. The spec's *"the resulting `FAILED` report"* is produced by `WorkerRuntime._dispatch`, unchanged.

## Open Questions

- [ ] **ADR-0003 is only partially discharged.** vLLM and ONNX still build their resource on first `acquire()`. Needs a `warmup()` seam on `BackendAdapter` — a `backends/` contract change with its own spec delta.
- [ ] **Chat messages → prompt templating (D22).** `ChatRequest` carries a `prompt` because nothing below the Provider can apply a chat template. Whoever adds it must decide between a `ChatBackend` protocol taking messages and a templating seam in `engines/`.
- [ ] **How a Provider names a *specific* dependency (D20, inherited from D10).** Still a `.proto` gap; the `Warning` makes the ambiguity visible, it does not resolve it.
- [ ] **Config file source (D19's future path).** Triggered by the first engine that must serve N models — the same change that resolves `ResolvedModelRef` into an artifact path.
- [ ] **Pool acquisition timeout default (D26).** 30s is a judgment call, not a measurement — the same honesty `_QUEUE_MAXSIZE`/`_PUT_POLL_SECONDS` are documented with.
- [ ] **Batch chunking (D24).** One chunk per batch until a real payload exceeds the transport's max message size.
- [ ] **ONNX execution-provider configuration.** CPU-only here; belongs to whichever change first ships a GPU deployment (OR4).
