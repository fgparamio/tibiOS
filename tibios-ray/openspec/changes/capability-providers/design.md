# Design: The Six Official Capability Providers

Change: `capability-providers` · Artifact store: hybrid (file + Engram `sdd/capability-providers/design`).
Extends — never renumbers — `ray-worker-runtime`'s frozen decisions **D1-D7**. New decisions here are numbered **CP1-CP8**.

## Technical Approach

Phase 2 fills the one hole the frozen foundation left: `capabilities/` defines the `CapabilityProvider` protocol but nothing implements it, so `CapabilityRegistry.catalog()` is empty and tibios-ray advertises nothing. This change lands **seven descriptor-carrying value objects** in `capabilities/`, plus the single failure they can all produce.

```
capabilities/
  names.py       (frozen)  CapabilityName
  descriptor.py  (frozen)  CapabilityDescriptor, CapabilityFlags, ModelFamily, CapabilityCatalog
  provider.py    (frozen)  CapabilityProvider (Protocol)
  errors.py      NEW       NoBackendAvailableError
  chat.py        NEW       CHAT_GENERATE_DESCRIPTOR      + ChatProvider
  embedding.py   NEW       EMBEDDING_GENERATE_DESCRIPTOR + EmbeddingProvider
  rerank.py      NEW       RERANK_DOCUMENTS_DESCRIPTOR   + RerankProvider
  vision.py      NEW       VISION_UNDERSTAND_DESCRIPTOR  + VisionProvider
  speech.py      NEW       SPEECH_TRANSCRIBE_DESCRIPTOR  + SpeechTranscriptionProvider
                           SPEECH_SYNTHESIZE_DESCRIPTOR  + SpeechSynthesisProvider
  ocr.py         NEW       OCR_EXTRACT_DESCRIPTOR        + OcrProvider
```

No new layer, no new package, no new protocol. The dependency direction `runtime -> capabilities -> selection -> backends` is unchanged: provider modules import `capabilities.{descriptor,names,errors}`, `backends.adapter` (for `BackendId`) and `execution.{context,report}` — and **nothing from `runtime/`**, enforced by a permanent test (see Testing Strategy).

Every Provider is a **zero-field frozen slotted dataclass**. That is not decoration: `slots=True` on a fieldless class makes it structurally impossible for a Provider to hold a backend reference, which is exactly the invariant this change must preserve until Phase 4. State-free also means `ChatProvider() == ChatProvider()`, instances are free, and the composition root can build them inline.

## Architecture Decisions

| # | Decision | Alternatives rejected | Rationale |
|---|---|---|---|
| CP1 | Each Provider is a **zero-field `@dataclass(frozen=True, slots=True)`** with a `descriptor` property returning a **module-level constant**, satisfying `CapabilityProvider` structurally (no base class, per D1) | Shared `BaseProvider` ABC/mixin; descriptor built inside the property; plain class | A base class would reintroduce the import edge D1 removed and would be pure ceremony for a two-member protocol. `slots=True` with zero fields mechanically forbids stashing a backend/adapter/session — the invariant becomes a language guarantee, not a review convention. A module constant makes `provider.descriptor is provider.descriptor` true, so a `CapabilityCatalog` `frozenset` dedupes by identity as well as by value, and tests/`Phase 3` can import the catalog data without instantiating anything. Note the constant cannot be a dataclass *field* named `descriptor` — that slot would shadow the property (this is why `testing/StubProvider` uses `capability_descriptor` + a property; concrete Providers need no field at all). |
| CP2 | `NoBackendAvailableError(Exception)` in `capabilities/errors.py`, carrying `capability: CapabilityName` and `provider: str` | Subclass `runtime.errors.DispatchError`; return a fake COMPLETED report; delegate to a `BackendAdapter` | Subclassing `DispatchError` is not a style violation, it is a **literal circular import**: `runtime/errors.py` already imports `capabilities.names` and `capabilities.provider`, so `capabilities/errors.py` importing `runtime.errors` closes the cycle at module-load time. Nothing is lost: `WorkerRuntime._dispatch` wraps `provider.execute()` in `except Exception` (`worker_runtime.py:81`), so a plain `Exception` is translated into a Failed `ExecutionReport` identically to a `DispatchError`. The `DispatchError` catch on line 76 guards `registry.resolve()` only, which Providers never reach. |
| CP3 | **No base class in `capabilities/errors.py`** — one concrete exception, no `CapabilityError` parent | `CapabilityError` base mirroring `runtime/errors.py`'s two families | `runtime/errors.py` splits `DispatchError`/`RegistrationError` because their **catch sites differ** (per-execution vs composition-root). Here there is exactly one catch site and one error; a parent class would carry zero behavior and zero discrimination. Adding one later is additive and non-breaking. |
| CP4 | The error carries **capability + provider class name only** | Also carry `frozenset[BackendId]` of advertised-but-unavailable backends; carry the provider instance | The advertised backends are already retrievable from `registry.catalog()`; duplicating them into the message buys nothing actionable and imports `frozenset` iteration-order nondeterminism into an assertion the tests must make deterministic. Carrying the *instance* would keep a live reference inside an exception that `WorkerRuntime` stringifies into a Report and then emits on the Channel — `type(self).__name__` is the only part that is actually used. |
| CP5 | **Family Label Convention (FLC)** — a family label is a pure, context-free function of the model's *published lineage name* (see below) | Closed `Enum` of families; raw HuggingFace repo ids; strip every role/modality qualifier; keep only "context-distinguishing" qualifiers | `descriptor.py` deliberately keeps `ModelFamily` an opaque open string ("rather than being over-engineered into a closed enum") — an enum reopens a frozen module and blocks additive catalog growth. Repo ids (`Qwen/Qwen2.5-VL-7B-Instruct`) are model-pinning, forbidden by "Capability-First, Not Model-Pinned". Stripping *all* qualifiers turns `paddleocr` into `paddle` (a DL framework, not a model lineage) — the rule breaks on its own examples. A context-dependent rule ("qualify only when two lineages collide in this catalog") is not a pure function of the model name, so the Phase-3 Model Catalog could not reproduce it and exact matching would silently fail. |
| CP6 | FLC is enforced by the **conformance harness**, not by `ModelFamily.__post_init__` | Add validation to `capabilities/descriptor.py` | The proposal declares zero Modified Capabilities and the foundation specs are frozen. The FLC binds *this change's catalog data*, not the open-ended value type — a future phase may legitimately advertise a third-party label this convention does not describe. A test that scans every advertised label gives the same guarantee with none of the coupling. |
| CP7 | **One shared conformance harness** parametrized over a typed tuple of all seven Providers; per-Provider test files assert only catalog data | Six independent full test modules; a `ProviderTestCase` base class inherited per Provider | Behavior is byte-identical across all seven — only catalog data varies (the proposal's own reason for one spec, not six). The single annotated tuple `_PROVIDERS: tuple[CapabilityProvider, ...]` doubles as the **static** conformance check: pyright verifies structural conformance of all seven in one expression, which no runtime `isinstance` can do (the protocol is not `runtime_checkable`). |
| CP8 | Provider modules import from **submodules**, never from the `tibios_ray.capabilities` package root | `from tibios_ray.capabilities import CapabilityDescriptor` | `capabilities/__init__.py` will import the seven provider modules to re-export them; if `chat.py` imported the package root back, the package would be circularly importable at load time. Absolute submodule imports (`from tibios_ray.capabilities.descriptor import ...`) resolve fine against a partially initialized package — the same pattern `runtime/registry.py` already uses. |

## The Family Label Convention (FLC)

**Rule.** A `ModelFamily` label is derived from the model's **published lineage name** by a pure function:

1. **Shape** — the result matches `^[a-z][a-z0-9_]*$`: lowercase ASCII, `_` as the only separator, no dots, no hyphens, no slashes. (Same alphabet as one `CapabilityName` segment, no dots — a family is not hierarchical.)
2. **Drop** — organisation/vendor prefix (`Qwen/`, `BAAI/`, `meta-llama/`), version tokens (`3`, `2.5`, `v2`, `m3`), parameter/size tokens (`7b`, `large`, `base`, `mini`), quantization/precision tokens (`q4_k_m`, `fp16`, `awq`, `gguf`), tuning-stage suffixes (`instruct`, `chat`, `it`, `sft`, `dpo`), and locale/variant tokens (`multilingual`, `en`, `zh`).
3. **Keep** — every remaining published token, in published order, joined by `_`. This includes modality/role tokens **that the publisher put in the lineage name** (`vl`, `vision`, `reranker`, `embed`, `embeddings`, `ocr`).
4. **Never pin** — if the result still identifies one deployable artifact (a size, a version, a quantization), the label is wrong.
5. **Purity** — the function depends only on the published name, never on what else happens to be in this catalog. This is the load-bearing property: Phase 3's Model Catalog applies the same function to the model it resolved, so exact `ModelFamily` equality matching works across the boundary without a synonym table.

**Worked derivations** (these are the audit trail for every label below):

| Published name | Drop | Label |
|---|---|---|
| `Qwen/Qwen3-8B-Instruct` | org, `3`, `8b`, `instruct` | `qwen` |
| `deepseek-ai/DeepSeek-V3` | org, `v3` | `deepseek` |
| `Qwen/Qwen2.5-VL-7B-Instruct` | org, `2.5`, `7b`, `instruct` | `qwen_vl` |
| `meta-llama/Llama-3.2-11B-Vision` | org, `3.2`, `11b` | `llama_vision` |
| `google/gemma-3-12b-it` | org, `3`, `12b`, `it` | `gemma` |
| `BAAI/bge-m3` | org, `m3` | `bge` |
| `BAAI/bge-reranker-v2-m3` | org, `v2`, `m3` | `bge_reranker` |
| `nomic-ai/nomic-embed-text-v1.5` | org, `text`, `v1.5` | `nomic_embed` |
| `jinaai/jina-embeddings-v3` | org, `v3` | `jina_embeddings` |
| `jinaai/jina-reranker-v2-base-multilingual` | org, `v2`, `base`, `multilingual` | `jina_reranker` |
| `intfloat/multilingual-e5-large` | org, `multilingual`, `large` | `e5` |
| `openai/whisper-large-v3` | org, `large`, `v3` | `whisper` |
| `hexgrad/Kokoro-82M` | org, `82m` | `kokoro` |
| `PaddlePaddle/PaddleOCR` | org | `paddleocr` |

**Authoritative catalog map** (refines the proposal's shorthand; deviations are the FLC applied, and are the answer to the proposal's open question):

| Module | Capability | Families | Backends | Flags |
|---|---|---|---|---|
| `chat.py` | `chat.generate` | `qwen`, `llama`, `deepseek`, `gemma`, `mistral`, `kimi` | `llama_cpp`, `tensorrt_llm`, `vllm` | streaming, tools, json, reasoning |
| `embedding.py` | `embedding.generate` | `bge`, `nomic_embed`†, `e5`, `jina_embeddings`† | `onnxruntime` | *(none)* |
| `rerank.py` | `rerank.documents` | `bge_reranker`, `jina_reranker` | `onnxruntime` | *(none)* |
| `vision.py` | `vision.understand` | `qwen_vl`, `llama_vision`, `gemma`† | `vllm`, `tensorrt_llm` | streaming, json |
| `speech.py` | `speech.transcribe` | `whisper` | `faster_whisper` | streaming |
| `speech.py` | `speech.synthesize` | `kokoro` | `onnxruntime` | streaming |
| `ocr.py` | `ocr.extract` | `paddleocr` | `onnxruntime` | json |

† deviates from `proposal.md`'s shorthand: `nomic` → `nomic_embed`, `jina` → `jina_embeddings` (rule 3 keeps published role tokens), `gemma_vision` → `gemma` (rule 3 keeps only *published* tokens, and Google publishes no "Gemma Vision" lineage — Gemma 3 is natively multimodal). `gemma` therefore appears under two capabilities, which is truthful: one lineage serves both. `paligemma` is an additive future label, not a rename.

**Flag rationale** (flags are a catalog claim about the capability contract, honored once Phase 4 lands; nothing can dispatch today, so no claim is currently falsifiable in production): chat is the full surface; embedding and rerank produce fixed-shape numeric output with no stream, no tools, no structure, no reasoning trace — all four `False` via the `CapabilityFlags()` default; vision streams generated text and supports structured extraction, but this catalog claims no VLM tool-calling; both speech directions stream (segments / audio chunks); OCR returns structured layout in one shot.

## Key Contracts

`capabilities/errors.py` — the whole module:

```python
from tibios_ray.capabilities.names import CapabilityName


class NoBackendAvailableError(Exception):
    """A Capability Provider advertises a capability it cannot yet execute:
    it holds no Backend Adapter reference (Phase 4 integrates engines).

    A plain `Exception`, deliberately NOT a `runtime.errors.DispatchError`
    (decision CP2): `runtime/errors.py` already imports `capabilities.names`
    and `capabilities.provider`, so inheriting would close a genuine import
    cycle. `WorkerRuntime._dispatch` catches bare `Exception` around
    `provider.execute()`, so this is translated into a Failed
    `ExecutionReport` exactly like a `DispatchError` would be.
    """

    def __init__(self, *, capability: CapabilityName, provider: str) -> None:
        self.capability = capability
        self.provider = provider
        super().__init__(
            f"{provider} advertises {capability.value!r} but no Backend "
            "Adapter is available to execute it"
        )
```

`capabilities/chat.py` — the reference shape every other module mirrors:

```python
from dataclasses import dataclass

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import CapabilityDescriptor, CapabilityFlags, ModelFamily
from tibios_ray.capabilities.errors import NoBackendAvailableError
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.execution.context import ExecutionContext
from tibios_ray.execution.report import ExecutionReport

CHAT_GENERATE_DESCRIPTOR = CapabilityDescriptor(
    capability=CapabilityName("chat.generate"),
    families=frozenset(
        {
            ModelFamily("qwen"),
            ModelFamily("llama"),
            ModelFamily("deepseek"),
            ModelFamily("gemma"),
            ModelFamily("mistral"),
            ModelFamily("kimi"),
        }
    ),
    backends=frozenset(
        {BackendId("llama_cpp"), BackendId("tensorrt_llm"), BackendId("vllm")}
    ),
    flags=CapabilityFlags(streaming=True, tools=True, json=True, reasoning=True),
)


@dataclass(frozen=True, slots=True)
class ChatProvider:
    """Advertises `chat.generate`. Holds no Backend Adapter — zero fields
    plus `slots=True` make that a language guarantee, not a convention."""

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return CHAT_GENERATE_DESCRIPTOR

    async def execute(self, context: ExecutionContext) -> ExecutionReport:
        raise NoBackendAvailableError(
            capability=CHAT_GENERATE_DESCRIPTOR.capability,
            provider=type(self).__name__,
        )
```

`capabilities/speech.py` — the only two-class module (`CapabilityDescriptor.capability` is singular and the registry is one-provider-per-capability, so transcription and synthesis are two registrable Providers sharing one module):

```python
SPEECH_TRANSCRIBE_DESCRIPTOR = CapabilityDescriptor(
    capability=CapabilityName("speech.transcribe"),
    families=frozenset({ModelFamily("whisper")}),
    backends=frozenset({BackendId("faster_whisper")}),
    flags=CapabilityFlags(streaming=True),
)

SPEECH_SYNTHESIZE_DESCRIPTOR = CapabilityDescriptor(
    capability=CapabilityName("speech.synthesize"),
    families=frozenset({ModelFamily("kokoro")}),
    backends=frozenset({BackendId("onnxruntime")}),
    flags=CapabilityFlags(streaming=True),
)


@dataclass(frozen=True, slots=True)
class SpeechTranscriptionProvider:
    @property
    def descriptor(self) -> CapabilityDescriptor:
        return SPEECH_TRANSCRIBE_DESCRIPTOR

    async def execute(self, context: ExecutionContext) -> ExecutionReport:
        raise NoBackendAvailableError(
            capability=SPEECH_TRANSCRIBE_DESCRIPTOR.capability,
            provider=type(self).__name__,
        )


@dataclass(frozen=True, slots=True)
class SpeechSynthesisProvider:
    @property
    def descriptor(self) -> CapabilityDescriptor:
        return SPEECH_SYNTHESIZE_DESCRIPTOR

    async def execute(self, context: ExecutionContext) -> ExecutionReport:
        raise NoBackendAvailableError(
            capability=SPEECH_SYNTHESIZE_DESCRIPTOR.capability,
            provider=type(self).__name__,
        )
```

`capabilities/embedding.py` — the minimal-flags shape (`CapabilityFlags()` default, all four `False`; the `flags` argument is omitted entirely rather than spelled out as four `False`s):

```python
EMBEDDING_GENERATE_DESCRIPTOR = CapabilityDescriptor(
    capability=CapabilityName("embedding.generate"),
    families=frozenset(
        {
            ModelFamily("bge"),
            ModelFamily("nomic_embed"),
            ModelFamily("e5"),
            ModelFamily("jina_embeddings"),
        }
    ),
    backends=frozenset({BackendId("onnxruntime")}),
)
```

**Naming rules the harness enforces mechanically** (this is what keeps seven chained slices from drifting):

- Descriptor constant name = capability string uppercased with `.` → `_`, suffixed `_DESCRIPTOR`: `chat.generate` → `CHAT_GENERATE_DESCRIPTOR`.
- Class name = CapWords of the module, suffixed `Provider`, with no acronym special-casing (`ocr.py` → `OcrProvider`, not `OCRProvider`); `speech.py` is the one module whose two classes are named after their capability (`SpeechTranscriptionProvider`, `SpeechSynthesisProvider`).
- No identifier contains "Worker" (existing `tests/unit/runtime/test_naming_audit.py` audits `capabilities/` and would fail).

`capabilities/__init__.py` re-exports the seven classes and `NoBackendAvailableError`. Descriptor constants stay module-level and are *not* re-exported: the package namespace is about types, the modules are about data. The existing `test_capabilities_exports.py` asserts `expected <= set(__all__)`, so it stays green while `__all__` grows.

## Data Flow

Nothing new flows; the point is what happens at the end.

```
worker.py                WorkerRuntime            CapabilityRegistry        ChatProvider
 (unwired — blocked           │                          │                       │
  on proto-worker-contract)   │                          │                       │
        │  ExecutionContext   │                          │                       │
        ├────────────────────>│ resolve("chat.generate") │                       │
        │                     ├─────────────────────────>│                       │
        │                     │<──────── provider ───────┤                       │
        │                     ├──── await execute(ctx) ─────────────────────────>│
        │                     │<─── raise NoBackendAvailableError ───────────────┤
        │                     │ except Exception -> _failed_report(str(error))   │
        │  <── EndOfStream(reason=report.failure) ── ctx.channel.emit()           │
        │  <── ExecutionReport(phase=FAILED, failure="ChatProvider advertises …") │
```

Two consequences worth stating explicitly:

1. The exception message is **user-visible**: `WorkerRuntime.execute` emits `EndOfStream(reason=report.failure)` on the Channel, so the message must read as an operational failure, not as a roadmap note. Roadmap context lives in the docstring, not in the string.
2. The Provider never touches `context` — not the channel, not the cancellation token, not the dependencies. Raising *before* any emission is what keeps "no Provider ever returns a COMPLETED report" trivially true and keeps the Channel's only event the terminal `EndOfStream` the Runtime itself emits.

## Testing Strategy

Strict TDD: every slice writes the failing test first. No `pytest-asyncio` is installed — async assertions use `asyncio.run(...)` inside a sync test, matching the existing suite (`tests/unit/capabilities/test_provider.py`).

### Shared conformance harness

`tests/unit/capabilities/test_provider_conformance.py` (per-Provider generics) and `tests/unit/capabilities/test_catalog_conformance.py` (whole-catalog). Both key off one table:

```python
_PROVIDERS: tuple[CapabilityProvider, ...] = (
    ChatProvider(),
    EmbeddingProvider(),
    RerankProvider(),
    VisionProvider(),
    SpeechTranscriptionProvider(),
    SpeechSynthesisProvider(),
    OcrProvider(),
)
```

That annotated tuple **is** the static conformance check — pyright verifies all seven satisfy `CapabilityProvider` structurally in one expression; a runtime `isinstance` is impossible (the protocol is not `runtime_checkable`), which is exactly why the check has to be a typed binding rather than an assertion. Each slice appends one line.

Per-Provider generics, `@pytest.mark.parametrize("provider", _PROVIDERS, ids=lambda p: type(p).__name__)`:

| Check | Assertion |
|---|---|
| Descriptor is a stable module constant | `provider.descriptor is provider.descriptor`; two independently constructed instances return the identical object; `hash(descriptor)` succeeds (required for `CapabilityCatalog`'s `frozenset`) |
| Descriptor constant naming | the provider's module (`sys.modules[type(provider).__module__]`) defines `<CAPABILITY>_DESCRIPTOR` and it **is** `provider.descriptor` |
| Non-empty catalog | `families` and `backends` are both non-empty `frozenset`s — stricter than `CapabilityRegistry._has_catalog`'s `or`, so no Provider can ever be registration-rejected |
| Element typing at runtime | every family is a `ModelFamily`, every backend a `BackendId` — never a bare `str` that pyright happened not to see |
| FLC compliance | every family label matches `^[a-z][a-z0-9_]*$` and no `_`-split token matches the banned-token regex `^(v?\d+(\.\d+)*\|\d+[bmk]\|q\d.*\|fp\d+\|bf\d+\|awq\|gptq\|gguf\|instruct\|chat\|base\|it\|sft\|dpo\|small\|medium\|large\|mini\|xl)$` — this is FLC rules 2 and 4 made executable (note `e5` passes: it starts with a letter) |
| Backend id shape | matches `^[a-z][a-z0-9_]*$` (`llama_cpp`, `tensorrt_llm`, `vllm`, `onnxruntime`, `faster_whisper`) |
| `execute()` always raises | `pytest.raises(NoBackendAvailableError)` for **three arbitrary contexts**: default `FakeExecutionContext()`, one whose `capability` is a *different* capability than the Provider's, and one whose `ManualCancellation` is already cancelled — the Provider must not branch on any of them |
| Error payload | the raised error's `.capability == provider.descriptor.capability` and `.provider == type(provider).__name__`; `str(error)` is non-empty |
| Never a report | `execute()` returns no value on any path (guaranteed by the `raises` checks; asserted as "no `ExecutionReport` observed") |
| End-to-end through the Runtime | a real `CapabilityRegistry([provider])` + `WorkerRuntime`: `execute(ctx)` returns `phase == FAILED` with non-empty `failure`, raises nothing, and the `InMemoryExecutionChannel` recorded exactly one event, an `EndOfStream` whose `reason` is that failure |

Whole-catalog checks (not parametrized):

| Check | Assertion |
|---|---|
| Co-registration | all seven in **one** `CapabilityRegistry` — no `DuplicateCapabilityError`, no `EmptyCatalogError` |
| Aggregated catalog | `registry.catalog().descriptors` has exactly 7 entries and equals `frozenset(p.descriptor for p in _PROVIDERS)` |
| Round-trip | `registry.resolve(p.descriptor.capability) is p` for all seven |
| Capability set | the seven capability strings are exactly `{chat.generate, embedding.generate, rerank.documents, vision.understand, speech.transcribe, speech.synthesize, ocr.extract}` |
| No branching | AST scan of the six provider modules finds **zero** `ast.If` / `ast.Match` / `ast.Compare` / `ast.IfExp` nodes — a far stricter, provider-scoped version of `test_no_local_infer_routing.py`'s repo-wide heuristic, and the direct proof of "no size/cost routing conditional exists in any Provider". Intentionally absolute; Phase 4 relaxes it when real execution lands |
| Layering | AST scan of every `src/tibios_ray/capabilities/*.py` finds no `import`/`from` referencing `tibios_ray.runtime` — the permanent guard behind decision CP2 |

Per-Provider files (`test_chat.py`, `test_embedding.py`, …) then only assert **catalog data**: one full `provider.descriptor == CapabilityDescriptor(...)` equality (the stability assertion the proposal's success criteria require) plus the individual flag values. ~30-40 lines each, no behavior duplicated.

`tests/unit/capabilities/test_errors.py` covers `NoBackendAvailableError` independently: attribute payload, message content, `isinstance(e, Exception)` and **`not isinstance(e, DispatchError)`** — pinning CP2 so no one "tidies" the hierarchy later.

## Module / Slice Plan

`auto-chain`, stacked PRs, each ≤400 changed lines, each green (`uv run pytest && uv run ruff check && uv run pyright`, executed from inside `tibios-ray/`).

| # | Slice | Adds | Est. lines |
|---|---|---|---|
| 1 | `errors.py` | `capabilities/errors.py`, `tests/unit/capabilities/test_errors.py`, `__init__.py` export | ~90 |
| 2 | per-Provider harness + Chat | `test_provider_conformance.py`, `capabilities/chat.py`, `test_chat.py`, exports | ~250 |
| 3 | Embedding + catalog harness | `capabilities/embedding.py`, `test_embedding.py`, `test_catalog_conformance.py`, exports | ~230 |
| 4 | Rerank | `capabilities/rerank.py`, `test_rerank.py`, exports | ~100 |
| 5 | Vision | `capabilities/vision.py`, `test_vision.py`, exports | ~105 |
| 6 | Speech (two classes) | `capabilities/speech.py`, `test_speech.py`, exports | ~160 |
| 7 | OCR | `capabilities/ocr.py`, `test_ocr.py`, exports | ~100 |

**Ordering, and why it refines the proposal.** The proposal said slice 1 carries `errors.py` *and* the harness. Two adjustments:

- `errors.py` lands **alone, first**. Every Provider raises it, so it is the true root of the dependency order; landing it separately makes slice 2's review purely about the harness. It is ~35 source lines with no consumer for one PR — accepted deliberately, because the alternative is a ~330-line slice 2 that reviews as three unrelated things at once.
- The harness cannot land *before* a Provider: a parametrize over an empty tuple produces a green suite that tests nothing, which is a TDD lie. So the harness lands **with Chat** (the richest flags case, best exercise of the generic checks).
- The **whole-catalog** half of the harness lands with slice 3, the first slice where two Providers exist — co-registration, union and round-trip are vacuous with a single Provider. It then grows one tuple line per remaining slice.

Every slice touches `capabilities/__init__.py`. In a stacked chain that is sequential, not concurrent, so it is a rebase-clean one-line addition per slice, not a conflict surface.

`src/tibios_ray/worker.py` stays untouched: composition is blocked on `proto-worker-contract`. The seven Providers are therefore constructed nowhere in production code until that change lands — which is precisely why "advertising capabilities that cannot execute" carries no runtime risk today.

## Migration / Rollout

Purely additive: seven new source modules, nine new test modules, one `__init__.py` edit. No frozen module is modified, no contract reshaped, no spec requirement changed. `git revert` of the slice commits restores the archived `ray-worker-runtime` state exactly.

## Open Questions

- [ ] **`gemma` under two capabilities** — truthful under the FLC (Gemma 3 is natively multimodal) but it means a family label alone does not disambiguate modality. Harmless while the Capability Filter matches on capability first; revisit only if Phase 3's Model Catalog needs family→modality to be a function.
- [ ] **`paligemma` / `mixtral` and friends** — deliberately absent. Adding a family is an additive catalog change; renaming one is breaking. The tests assert stability and shape, never exhaustiveness.
- [ ] **Provider construction cost at the composition root** — zero-field frozen dataclasses are free, but whether `worker.py` builds them inline or imports a `DEFAULT_PROVIDERS` tuple is a `proto-worker-contract`-era decision, not this change's.
- [ ] **When Phase 4 relaxes the no-branching AST check** — real `execute()` bodies will contain conditionals. The check must then narrow from "zero branches" to "no size/cost-shaped comparison", i.e. converge on `test_no_local_infer_routing.py`'s heuristic. Flagged now so the relaxation is a deliberate decision rather than a quiet test deletion.
