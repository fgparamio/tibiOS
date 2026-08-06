# Design: Model Catalog

## Context

`ray-worker-runtime` (Phase 1/2) built the execution vocabulary and the layering rule `runtime -> capabilities -> selection -> backends`. `capability-providers` (Phase 4, archived) added seven Providers advertising `ModelFamily` labels under the **Family Label Convention (FLC)**, enforced by a *test-only* regex pair in `tests/unit/capabilities/test_provider_conformance.py`. FLC rule 5 (purity) named this change as its caller:

> "Phase 3's Model Catalog applies the same function to the model it resolved, so exact `ModelFamily` equality matching works across the boundary without a synonym table."

This change discharges that promise. It adds a new leaf package `src/tibios_ray/catalog/` holding (a) the value types describing a concrete published model, (b) `family_of` — the FLC promoted from regex-in-a-test to a real pure function, (c) a six-query immutable `ModelCatalog`, and (d) reference data for every advertised family.

It adds **zero production callers**. The catalog is inert, verified reference data until an Object Store metadata/tag query exists cross-repo. That is a deliberate, stated position, not an oversight.

## Goals / Non-Goals

**Goals**

- Concrete, hashable, frozen value types for a published model and its per-backend serving footprint.
- `family_of(PublishedModelName) -> ModelFamily` reproducing all fourteen archived FLC derivations exactly, as a pure function of the input string alone.
- Six queries answered from data, with no per-family branch anywhere.
- A structural guard proving nothing from `execution/` can enter or leave the catalog.
- A two-way consistency check between catalog data and the seven Providers' descriptors.

**Non-Goals** (beyond the proposal's, which all carry forward)

- No `ResolvedModelRef`, no `ObjectId`/`ObjectVersion`/`ContentHash` anywhere in `catalog/`.
- No `choose`/`best`/`select` query. Ranking is selection, not catalog.
- No unification of Phase 2's conformance harness onto `family_of` (explicit proposal non-goal; see MC11).
- No arithmetic in `requirements()`. Footprint figures are stated data, not derived at query time (MC5).

## Architecture Overview

```
src/tibios_ray/catalog/
├── __init__.py          re-exports types, family_of, ModelCatalog, errors  (NOT entries)
├── errors.py            CatalogError + 6 concrete failures
├── names.py             PublishedModelName, family_of, FLC token tables
├── model.py             BackendSupport, ModelDescriptor
├── catalog.py           ModelCatalog — ctor-validated immutable index, 6 queries
└── entries/
    ├── __init__.py      ALL_ENTRIES, DEFAULT_CATALOG            (last slice only)
    ├── chat.py          qwen, llama, deepseek, gemma, mistral, kimi
    ├── embedding.py     bge, nomic_embed, e5, jina_embeddings
    ├── rerank.py        bge_reranker, jina_reranker
    ├── vision.py        qwen_vl, llama_vision
    ├── speech.py        whisper, kokoro
    └── ocr.py           paddleocr
```

Dependency edges out of `catalog/`, and only these:

| Import | For | Note |
|---|---|---|
| `capabilities.descriptor` | `ModelFamily` | |
| `backends.adapter` | `BackendId` | |
| `selection.policy` | `Quantization` | reused, not mirrored — see MC5 |
| stdlib | `dataclasses`, `re`, `types.MappingProxyType`, `collections.abc` | |

`catalog -> selection` transitively reaches `execution/` (because `selection/policy.py` imports `ResolvedModelRef`). That is a *module graph* fact, not a *type surface* fact, and the guard in MC9 is written against the type surface precisely because a transitive module edge is unavoidable once `Quantization` is reused. Nothing in `catalog/` may name `tibios_ray.execution` or `tibios_ray.runtime` in an import statement, and no catalog field or signature may mention a type defined there.

Nothing imports `catalog/`. That is enforced permanently, the same way `capabilities/`↛`runtime/` already is.

## Architecture Decisions

| # | Decision | Alternatives rejected | Rationale |
|---|---|---|---|
| MC1 | `PublishedModelName` is a **single-field frozen slotted dataclass** (`value: str`), positional like `BackendId`/`ModelFamily`/`ObjectId` — not kw-only | `NewType("PublishedModelName", str)`; a bare `str`; naming it `ModelId` | A `NewType` is erased at runtime, so any string could impersonate a model name — exactly the failure D3 rejected for `ObjectId`. But the *reason* differs, and the name records it: `ObjectId` is type-distinct because it carries **resolution proof**; `PublishedModelName` is type-distinct because it carries **publication identity** and deliberately carries no proof. Calling it `ModelId` would imply the opposite and invite someone to accept it where a `ResolvedModelRef` belongs. Positional (not kw-only) matches every other single-field wrapper in the codebase; kw-only is reserved for multi-field records. |
| MC2 | `family_of` is a **module-level pure function in `catalog/names.py`**, driven by frozen token tables | A method on `PublishedModelName`; validation in `ModelFamily.__post_init__`; leaving the regex in the test suite | A method would make the FLC an attribute of the *name* type, so any future third-party name type would have to reimplement it; a free function is applicable to any name and trivially table-testable. `__post_init__` validation is CP6 all over again — `descriptor.py` is a frozen foundation module and `ModelFamily` must stay an open label a future phase can populate from outside the FLC. Leaving it in the test is what FLC rule 5 explicitly forbids. |
| MC3 | **The head-token rule**: the first token surviving unconditional drops is never itself dropped. Version-mark tokens (`^[a-z]\d+$`: `m3`, `k2`, `r1`) are dropped only in the tail | A lineage allowlist (`{"e5", "bge", ...}`); dropping every letter+digit token; a "context-distinguishing" heuristic | `e5` (keep) and `m3` (drop) are **string-identical in shape** — no context-free pattern can separate them. Position can: `intfloat/multilingual-e5-large` leaves `e5` as the head after `multilingual` and `large` fall away, while `BAAI/bge-m3` leaves `m3` behind `bge`. This keeps rule 5 purity intact (position within the input is a property of the input) where an allowlist would smuggle catalog knowledge into the function and break the moment a new lineage appears. It also generalises for free: `Kimi-K2` → `kimi`, `DeepSeek-R1` → `deepseek`. |
| MC4 | Split a token at an alpha→digit boundary **only when the alphabetic prefix is ≥2 characters** | Unconditional boundary split; no boundary split at all | `Qwen3-8B` publishes the version *fused* to the lineage (`qwen3`), so some split is required. An unconditional split destroys `e5` (→ `e`,`5`) and `m3`. The ≥2-letter guard splits every real fused-version case (`qwen3`, `llama3`, `gemma3`, `phi4`, `internvl2`, `glm4`) and leaves every single-letter mark intact for MC3 to judge. Two rules, no overlap. |
| MC5 | `BackendSupport` is keyed by **(backend, footprint tier)**, not by backend. `ModelDescriptor.serving` may hold several entries for one `BackendId`; `quantizations` groups the schemes that share one `min_vram_bytes` | `min_vram_bytes: Mapping[Quantization, int]`; a new `QuantizedFootprint` type; computing the figure in `requirements()` from a bits ratio | The proposal states both "footprint is a function of quantization" **and** a single scalar `min_vram_bytes` per `BackendSupport` — latent contradiction, resolved here. A `Mapping` field is unhashable and kills `frozenset[BackendSupport]`. A `QuantizedFootprint` type renames a field the proposal fixed. Computing the figure puts arithmetic into a layer whose entire premise is "reference data, no logic", and would be estimate-derived-from-estimate. Multiple `BackendSupport` rows keep all three field names verbatim, make `requirements()` a pure lookup, and are *truthful*: `awq` and `gptq` at 4 bits genuinely share a footprint tier, which is why `quantizations` is a set and not a scalar. |
| MC6 | `ModelCatalog` is a **ctor-validated class building `MappingProxyType` indices**, mirroring `CapabilityRegistry` — not a frozen dataclass | Frozen dataclass over `frozenset[ModelDescriptor]` + linear-scan queries; `__post_init__` + `object.__setattr__` index stuffing; module-level dicts + free functions | Three invariants must be enforced *somewhere* (duplicate name, FLC mismatch, ambiguous footprint), and `registry.py`'s docstring already set the precedent that construction-time rules live in the index, never in the value type. A frozen dataclass leaves them unenforced or forces `object.__setattr__`, which defeats `frozen=True` while looking like it doesn't. Linear scan over ~45 entries is genuinely free, but `frozenset` iteration order is nondeterministic, which would make error messages and `models()` output flaky. Free functions over module dicts offer no seam to construct an alternate catalog, and slice 2's query tests depend on exactly that seam (fabricated fixture data, no real entries). No `add()`/`register()` method exists — immutability satisfies the same "no global mutable state" rule as D6. |
| MC7 | **Asymmetric error contract**: `get()` and `requirements()` raise; `models()`, `supports()`, `quantizations()` answer emptily/falsely | Every query returns `None` on miss; every query raises; every query returns a sentinel | The split follows what the *subject* of each question is. `get(name)` is an identity lookup — absence is a caller error, exactly like `CapabilityRegistry.resolve` raising `UnknownCapabilityError`. "Which models are in family X" has an honest empty answer; "does this model run on backend B" has an honest `False`; "which quantizations" has an honest empty set. `requirements()` returns a scalar with no honest empty value — `0`/`-1` are sentinels and `None` forces every caller into an `if`, which is the exact shape that grows into selection logic. Uniform `None` would push all six into caller-side branching; uniform raising would make "is this backend supported" an exception-driven question. |
| MC8 | A family's **advertised backend set is the union** over every `CapabilityDescriptor` advertising that family | Partition the catalog per capability; scope the ⊆ check to a single descriptor | `gemma` is advertised by both `chat.generate` (`llama_cpp`, `tensorrt_llm`, `vllm`) and `vision.understand` (`vllm`, `tensorrt_llm`). Scoping the ⊆ check per descriptor would make `google/gemma-3-12b-it` on `llama_cpp` a violation of vision's set while being valid under chat's — the same entry both legal and illegal. This answers the archived design's open question ("`gemma` under two capabilities … revisit only if Phase 3's Model Catalog needs family→modality to be a function"): it does **not**. The catalog is keyed by family, capability-agnostic; family→modality never needs to be a function. |
| MC9 | The resolution guard is **generic type introspection + AST + a pyright fixture**, never a hardcoded `"ObjectId"` name check | `rg`-style string scan for `ObjectId`/`ContentHash`/`ResolvedModelRef` in `catalog/` | D3 made those types real dataclasses so a *structural* check is possible; using them only as strings throws that away. The guard walks `dataclasses.fields()` of every public catalog type and `inspect.signature()` of every public `ModelCatalog` method, asserting no annotated type has `__module__` starting with `tibios_ray.execution`. That catches a field added in 2027 whose name nobody thought to blacklist. The pyright fixture (mirroring `tests/unit/selection/pyright_fixtures/rejects_bare_family_string.py`) closes the static half: under `reportUnnecessaryTypeIgnoreComment = true`, widening `get()` to accept a `ResolvedModelRef` turns a passing build red. |
| MC10 | The consistency harness **discovers descriptors by module introspection** over `tibios_ray.capabilities`, not from a maintained tuple | Import `_PROVIDERS` from `tests/unit/capabilities/test_provider_conformance.py`; hand-maintain a `_ADVERTISED` tuple | Importing another package's test module (as `test_catalog_conformance.py` does today) couples two test trees and makes the catalog's correctness depend on a test fixture rather than on production data. A maintained tuple silently under-checks the day an eighth Provider lands. Iterating `pkgutil.iter_modules` and collecting every module-level `CapabilityDescriptor` is exhaustive by construction. D6 forbids auto-discovery in **production wiring** (`worker.py` builds providers explicitly); it says nothing about a test whose entire job is to be exhaustive. |
| MC11 | The FLC shape/banned-token regexes are **re-declared as production constants in `catalog/names.py`**; Phase 2's test copies stay untouched | Import the constants from the phase-2 test module into production; refactor phase 2 onto `family_of` | Production importing a test module is backwards. Refactoring phase 2 onto `family_of` is a named non-goal in this proposal, and would reopen an archived change. The duplication is two regex literals whose drift is itself caught: the consistency harness asserts `family_of(entry.name) == entry.family` **and** that every advertised label satisfies the catalog's own shape regex — if the two copies diverge, one of those two assertions fails. Accepted duplication with a failing-test tripwire. |
| MC12 | `catalog/entries/*.py` modules are **filing convenience by capability group only**; the catalog itself is keyed by family | One entries module per family; partition entries by capability | 17 family modules is filing overhead with no behavioural payoff. The consequence that matters: `gemma` entries live in `entries/chat.py` **once** and satisfy `vision.understand`'s advertisement too — `entries/vision.py` therefore holds only `qwen_vl` and `llama_vision`. A capability partition would force `gemma` to be duplicated or arbitrarily assigned, and would re-introduce exactly the family→modality function MC8 rejects. |
| MC13 | `min_vram_bytes` is **stated data with a documented derivation**, advisory, never an admission input | Measured benchmarks; omit the field; a `VramEstimate` type with a confidence band | The figures come from `ceil_to_gib(parameter_count × (bits / 8) × 1.2)`, the 1.2 covering KV cache and activations at a modest batch and the entry's stated `context_window`. Writing the formula down makes every number in the tables auditable and falsifiable by inspection. Measured benchmarks are a named non-goal and would require hardware this change does not have. A confidence band is a type nobody reads while zero production callers exist. |
| MC14 | `DEFAULT_CATALOG` is assembled in `entries/__init__.py` in the **final slice**; earlier slices export only their own `*_ENTRIES` tuple | Assemble incrementally, one line per slice (the phase-2 `capabilities/__init__.py` pattern) | Phase 2 accepted every slice touching one shared file because a stacked chain makes it sequential, not concurrent. But here the shared file would be *executable assembly* whose construction validates all invariants at import time — so a data bug in slice 5 breaks slice 3's tests through an `ImportError`, not through the test that owns the data. Deferring assembly means slices 3–7 touch **no shared file at all**, and each group's tests build a local `ModelCatalog(CHAT_ENTRIES)` scoped to its own data. The final slice's whole job is then the union and its invariants. |

## The FLC in production: `family_of`

The archived FLC is five rules, of which rules 2–4 were prose. This is the executable form. Rules 1 and 5 (shape, purity) are properties of the function, not steps in it.

### Algorithm

Four phases, no branching on catalog contents, no I/O, no state:

1. **Strip the org prefix** — everything up to and including the last `/`. (FLC rule 2, first clause.)
2. **Tokenise** — lowercase, split on every non-alphanumeric run, then split each part at an alpha→digit boundary *if and only if* the alphabetic prefix is ≥2 characters (MC4).
3. **Unconditional drop** — remove version tokens, size tokens, quantization tokens, and any token in the frozen drop table (tuning stages, size adjectives, locales, content qualifiers). (FLC rule 2, remaining clauses.)
4. **Head rule + tail version marks** — the first survivor is the lineage head and is retained by construction; each *tail* token matching `^[a-z]\d+$` is dropped (MC3). Join the rest with `_` in published order. (FLC rules 3 and 4.)

### Implementation

```python
_SEPARATORS = re.compile(r"[^a-z0-9]+")

# MC4: `qwen3` -> ("qwen", "3"); `e5`/`m3`/`a3b` are left whole.
_FUSED_VERSION = re.compile(r"^([a-z]{2,})(\d.*)$")

_VERSION_TOKEN = re.compile(r"^v?\d+$")                     # 3, 2, 5, v2, v0, 2506
_SIZE_TOKEN = re.compile(r"^[a-z]?\d+(x\d+)?[bmk]$")        # 8b, 82m, 8x7b, a3b, a22b
_QUANT_TOKEN = re.compile(r"^(q\d.*|fp\d+|bf\d+|int\d+|awq|gptq|gguf|mlx)$")
_TAIL_VERSION_MARK = re.compile(r"^[a-z]\d+$")              # m3, k2, r1  (tail only)

_FLC_SHAPE = re.compile(r"^[a-z][a-z0-9_]*$")               # FLC rule 1

_DROPPED_TOKENS = frozenset(
    {
        # tuning stage
        "instruct", "chat", "base", "it", "sft", "dpo", "rl", "distill", "thinking",
        # size adjective
        "tiny", "mini", "small", "medium", "large", "xl", "xxl", "huge",
        # locale / release variant
        "multilingual", "en", "zh", "es", "turbo", "preview", "latest", "beta",
        # content qualifier the archived derivation table already drops
        "text",
    }
)


def _tokenize(published: str) -> list[str]:
    _, _, tail = published.rpartition("/")           # phase 1: drop the org prefix
    tokens: list[str] = []
    for part in _SEPARATORS.split(tail.lower()):     # phase 2: tokenise
        if not part:
            continue
        fused = _FUSED_VERSION.fullmatch(part)
        if fused is None:
            tokens.append(part)
        else:
            tokens.append(fused.group(1))
            tokens.append(fused.group(2))
    return tokens


def _is_dropped(token: str) -> bool:                 # phase 3
    return (
        token in _DROPPED_TOKENS
        or _VERSION_TOKEN.fullmatch(token) is not None
        or _SIZE_TOKEN.fullmatch(token) is not None
        or _QUANT_TOKEN.fullmatch(token) is not None
    )


def family_of(name: PublishedModelName) -> ModelFamily:
    """Derive the FLC family label from a published model name.

    Pure: depends only on `name.value`. Never on catalog contents — this
    is FLC rule 5, the property that lets the catalog and the seven
    Providers agree on `ModelFamily` equality with no synonym table.
    """
    survivors = [token for token in _tokenize(name.value) if not _is_dropped(token)]
    if not survivors:
        raise FamilyDerivationError(name, reason="no lineage token survived")

    head, *tail = survivors                          # phase 4: MC3 head rule
    kept = [head] + [t for t in tail if _TAIL_VERSION_MARK.fullmatch(t) is None]
    label = "_".join(kept)

    if _FLC_SHAPE.fullmatch(label) is None:          # FLC rule 1, belt and braces
        raise FamilyDerivationError(name, reason=f"derived label {label!r} violates FLC shape")
    return ModelFamily(label)
```

### Verification against all fourteen archived derivations

Every row is a test case in slice 1; the "tokens" column shows the state after phase 2, with dropped tokens struck by the phase that removes them.

| Published name | Tokens after phase 2 | Dropped by | Result |
|---|---|---|---|
| `Qwen/Qwen3-8B-Instruct` | qwen · 3 · 8b · instruct | version, size, table | `qwen` |
| `deepseek-ai/DeepSeek-V3` | deepseek · v3 | version | `deepseek` |
| `Qwen/Qwen2.5-VL-7B-Instruct` | qwen · 2 · 5 · vl · 7b · instruct | version ×2, size, table | `qwen_vl` |
| `meta-llama/Llama-3.2-11B-Vision` | llama · 3 · 2 · 11b · vision | version ×2, size | `llama_vision` |
| `google/gemma-3-12b-it` | gemma · 3 · 12b · it | version, size, table | `gemma` |
| `BAAI/bge-m3` | bge · m3 | tail version mark | `bge` |
| `BAAI/bge-reranker-v2-m3` | bge · reranker · v2 · m3 | version, tail mark | `bge_reranker` |
| `nomic-ai/nomic-embed-text-v1.5` | nomic · embed · text · v1 · 5 | table, version ×2 | `nomic_embed` |
| `jinaai/jina-embeddings-v3` | jina · embeddings · v3 | version | `jina_embeddings` |
| `jinaai/jina-reranker-v2-base-multilingual` | jina · reranker · v2 · base · multilingual | version, table ×2 | `jina_reranker` |
| `intfloat/multilingual-e5-large` | multilingual · e5 · large | table ×2 — **`e5` survives as head (MC3)** | `e5` |
| `openai/whisper-large-v3` | whisper · large · v3 | table, version | `whisper` |
| `hexgrad/Kokoro-82M` | kokoro · 82m | size | `kokoro` |
| `PaddlePaddle/PaddleOCR` | paddleocr | — | `paddleocr` |

Additional cases this change introduces, proving MC3/MC4 generalise:

| Published name | Mechanism | Result |
|---|---|---|
| `Qwen/Qwen3-30B-A3B` | `a3b` caught by `_SIZE_TOKEN`'s optional letter prefix | `qwen` |
| `moonshotai/Kimi-K2-Instruct` | `k2` is a tail version mark | `kimi` |
| `mistralai/Mistral-Small-3.2-24B-Instruct-2506` | `2506` is a bare version token | `mistral` |
| `openai/whisper-large-v3-turbo` | `turbo` in the drop table | `whisper` |
| `intfloat/e5-large-v2` | `e5` head, both tails dropped | `e5` |
| `mistralai/Mixtral-8x7B-Instruct-v0.1` | `8x7b` caught by `_SIZE_TOKEN`'s `x` clause | `mixtral` |

Two known non-derivable shapes, deliberately excluded from catalog data rather than papered over (see Open Questions):

| Published name | Derives to | Why it is excluded |
|---|---|---|
| `meta-llama/Meta-Llama-3.1-8B-Instruct` | `meta_llama` | vendor token echoed inside the model name; Meta also publishes the canonical `meta-llama/Llama-3.1-8B-Instruct`, which the catalog uses instead |
| `deepseek-ai/DeepSeek-R1-Distill-Qwen-32B` | `deepseek_qwen` | a cross-lineage distill has no single truthful family under a pure function |

The `entry.family == family_of(entry.name)` invariant (MC6, enforced at construction) is what keeps these out mechanically: an entry whose name does not derive cleanly cannot be added without either fixing the name or amending the FLC, and amending the FLC is a spec change.

## Key Contracts

### `catalog/names.py`

```python
@dataclass(frozen=True, slots=True)
class PublishedModelName:
    """The identity a model is published under, e.g.
    `"Qwen/Qwen3-8B"`. Deliberately not `ModelId`: unlike
    `execution/ids.py`'s `ObjectId` (design decision D3), this carries no
    resolution proof — it is what a human writes down, not what the
    Runtime resolved. It is a frozen dataclass for the same reason
    `ObjectId` is: a `NewType` is erased, so a bare string could
    impersonate it."""

    value: str
```

### `catalog/model.py`

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class BackendSupport:
    """One (backend, footprint tier) row of a model's serving table.

    `quantizations` holds the schemes that share `min_vram_bytes` — `awq`
    and `gptq` at 4 bits do; `fp16` does not. A `ModelDescriptor` may
    therefore carry several `BackendSupport` rows for the same
    `BackendId`, one per tier (design decision MC5). `min_vram_bytes` is
    advisory, derived as `parameter_count * bits / 8 * 1.2` rounded up to
    a whole GiB (MC13); nothing in this change makes an admission
    decision from it."""

    backend: BackendId
    quantizations: frozenset[Quantization]
    min_vram_bytes: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelDescriptor:
    """One concrete published model. `family` is redundant with
    `family_of(name)` by construction — `ModelCatalog` rejects any entry
    where they disagree — and is stated explicitly anyway so the entry
    tables are readable without mentally running the FLC.

    `parameter_count` is *total* parameters, including inactive experts on
    a MoE model, because that is what determines resident VRAM.
    `context_window` is the natively published window, not an extended
    one (Qwen3's 32 768, not its YaRN-extended 131 072)."""

    name: PublishedModelName
    family: ModelFamily
    parameter_count: int
    context_window: int
    serving: frozenset[BackendSupport]
```

### `catalog/catalog.py`

```python
class ModelCatalog:
    """Immutable, ctor-built index of concrete models, mirroring
    `runtime/registry.py`'s `CapabilityRegistry` (design decision MC6).
    No `add()`/`register()`; construction validates, then the object is
    read-only for life.

    Three construction-time invariants, each with its own error:
      - no duplicate `PublishedModelName`            -> DuplicateModelError
      - `entry.family == family_of(entry.name)`      -> FamilyMismatchError
      - no (backend, quantization) pair appears in
        two `BackendSupport` rows of one entry       -> AmbiguousFootprintError
    """

    def __init__(self, entries: Sequence[ModelDescriptor]) -> None: ...

    def families(self) -> frozenset[ModelFamily]:
        """Every family with at least one entry. A `frozenset` so it is
        directly comparable with `CapabilityDescriptor.families`."""

    def models(self, family: ModelFamily) -> tuple[ModelDescriptor, ...]:
        """Entries in `family`, ordered by `name.value`. Empty tuple for an
        unknown family — "which models are in X" has an honest empty
        answer (MC7). Ordered, not a `frozenset`, so output is
        deterministic."""

    def get(self, name: PublishedModelName) -> ModelDescriptor:
        """Raises `UnknownModelError` — an identity lookup's absence is a
        caller error, exactly like `CapabilityRegistry.resolve` (MC7)."""

    def supports(self, name: PublishedModelName, backend: BackendId) -> bool:
        """`False` for a known model on an unadvertised backend;
        `UnknownModelError` for an unknown model. The backend is the
        question, the model is the subject (MC7)."""

    def quantizations(
        self, name: PublishedModelName, backend: BackendId
    ) -> frozenset[Quantization]:
        """Union across every `BackendSupport` row for `backend`. Empty
        when `supports()` is `False`; `UnknownModelError` for an unknown
        model."""

    def requirements(
        self, name: PublishedModelName, backend: BackendId, quantization: Quantization
    ) -> int:
        """Advisory minimum VRAM in bytes for that exact triple — a pure
        lookup, no arithmetic (MC5). Raises `UnsupportedServingError` when
        the pair is not in the model's serving table: a scalar has no
        honest empty value, and `None` would push every caller into a
        branch (MC7)."""
```

Internal indices, built once in `__init__` and wrapped in `MappingProxyType`:

| Index | Type | Serves |
|---|---|---|
| `_by_name` | `Mapping[PublishedModelName, ModelDescriptor]` | `get`, and every query that starts from a name |
| `_by_family` | `Mapping[ModelFamily, tuple[ModelDescriptor, ...]]` | `families`, `models` |
| `_footprints` | `Mapping[tuple[PublishedModelName, BackendId, Quantization], int]` | `supports`, `quantizations`, `requirements` |

`_footprints` is where `AmbiguousFootprintError` comes from: a duplicate key during construction *is* the ambiguity. The invariant and the index are the same object, so the check cannot be forgotten.

### `catalog/errors.py`

```python
class CatalogError(Exception):
    """Base for every catalog failure."""
```

Six concrete subclasses: `FamilyDerivationError` (name → no valid label), `UnknownModelError`, `UnsupportedServingError` (query-time); `DuplicateModelError`, `FamilyMismatchError`, `AmbiguousFootprintError` (construction-time). Each carries typed payload (the offending `PublishedModelName`, and for the serving errors the `BackendId`/`Quantization`), never a bare message.

A base class here — unlike CP3, which rejected one for `capabilities/errors.py` — because CP3's test was "do the catch sites differ": there, one error, one catch site, so a parent carried zero discrimination. Here six failure modes share one plausible catch site (a future selection layer asking "could the catalog answer?") *and* need discrimination between construction bugs and query misses. `runtime/errors.py`'s own two-family split is the same reasoning applied at a smaller scale.

## Reference data — the Chat family group (worked example)

All figures derive from MC13's formula: `ceil_gib(parameter_count × bits/8 × 1.2)`. Backends are constrained by MC8's union rule; for every chat family that union is `{llama_cpp, tensorrt_llm, vllm}` (`gemma` additionally appears under `vision.understand`, whose backends are a subset, so the union is unchanged).

Quantization vocabulary used (all `selection.policy.Quantization`): `fp16/16`, `fp8/8`, `int8/8`, `awq/4`, `gptq/4`, `q4_k_m/4`, `q8_0/8`.

### `qwen`

| Name | Params | Ctx | Serving rows (backend · quantizations · min VRAM) |
|---|---|---|---|
| `Qwen/Qwen3-8B` | 8_200_000_000 | 32_768 | `llama_cpp`·{q4_k_m}·5 GiB · `llama_cpp`·{q8_0}·10 GiB · `vllm`·{fp16}·20 GiB · `vllm`·{awq,gptq}·5 GiB · `tensorrt_llm`·{fp16}·20 GiB |
| `Qwen/Qwen3-14B` | 14_800_000_000 | 32_768 | `llama_cpp`·{q4_k_m}·9 GiB · `vllm`·{fp16}·36 GiB · `vllm`·{awq,gptq}·9 GiB |
| `Qwen/Qwen3-32B` | 32_800_000_000 | 32_768 | `vllm`·{fp16}·79 GiB · `vllm`·{awq,gptq}·20 GiB · `tensorrt_llm`·{fp16}·79 GiB |
| `Qwen/Qwen3-30B-A3B` | 30_500_000_000 | 32_768 | `vllm`·{fp16}·74 GiB · `vllm`·{awq,gptq}·19 GiB |
| `Qwen/Qwen2.5-7B-Instruct` | 7_600_000_000 | 32_768 | `llama_cpp`·{q4_k_m}·5 GiB · `vllm`·{fp16}·19 GiB |

`Qwen3-8B` is the deliberate five-row flagship: it is the one entry that exercises every shape the type permits (two tiers on one backend, a multi-scheme tier, and the same tier on two backends). Every other entry stays at two or three rows — the tables are reference data, not a combinatorial exercise.

### `llama`

| Name | Params | Ctx | Serving rows |
|---|---|---|---|
| `meta-llama/Llama-3.1-8B-Instruct` | 8_030_000_000 | 131_072 | `llama_cpp`·{q4_k_m}·5 GiB · `vllm`·{fp16}·20 GiB · `vllm`·{awq,gptq}·5 GiB |
| `meta-llama/Llama-3.3-70B-Instruct` | 70_600_000_000 | 131_072 | `vllm`·{fp16}·170 GiB · `vllm`·{awq,gptq}·43 GiB · `tensorrt_llm`·{fp16}·170 GiB |
| `meta-llama/Llama-3.2-3B-Instruct` | 3_210_000_000 | 131_072 | `llama_cpp`·{q4_k_m}·2 GiB · `vllm`·{fp16}·8 GiB |

### `deepseek`

| Name | Params | Ctx | Serving rows |
|---|---|---|---|
| `deepseek-ai/DeepSeek-V3` | 671_000_000_000 | 163_840 | `vllm`·{fp8}·805 GiB · `vllm`·{awq,gptq}·403 GiB · `tensorrt_llm`·{fp8}·805 GiB |
| `deepseek-ai/DeepSeek-R1` | 671_000_000_000 | 163_840 | `vllm`·{fp8}·805 GiB · `tensorrt_llm`·{fp8}·805 GiB |

No `llama_cpp` row: a 671 B model is a multi-node deployment, and claiming single-GPU GGUF support would be catalog fiction. The advertised backend set is an upper bound, not a requirement to use all of it.

### `gemma`

| Name | Params | Ctx | Serving rows |
|---|---|---|---|
| `google/gemma-3-4b-it` | 4_300_000_000 | 131_072 | `llama_cpp`·{q4_k_m}·3 GiB · `vllm`·{fp16}·11 GiB |
| `google/gemma-3-12b-it` | 12_200_000_000 | 131_072 | `llama_cpp`·{q4_k_m}·8 GiB · `vllm`·{fp16}·30 GiB · `vllm`·{awq,gptq}·8 GiB |
| `google/gemma-3-27b-it` | 27_400_000_000 | 131_072 | `vllm`·{fp16}·66 GiB · `vllm`·{awq,gptq}·17 GiB · `tensorrt_llm`·{fp16}·66 GiB |

These three rows are also the *entire* `gemma` answer for `vision.understand` (MC8/MC12). `entries/vision.py` does not restate them.

### `mistral`

| Name | Params | Ctx | Serving rows |
|---|---|---|---|
| `mistralai/Mistral-7B-Instruct-v0.3` | 7_250_000_000 | 32_768 | `llama_cpp`·{q4_k_m}·5 GiB · `vllm`·{fp16}·18 GiB |
| `mistralai/Mistral-Small-3.2-24B-Instruct-2506` | 24_000_000_000 | 131_072 | `vllm`·{fp16}·58 GiB · `vllm`·{awq,gptq}·15 GiB |

### `kimi`

| Name | Params | Ctx | Serving rows |
|---|---|---|---|
| `moonshotai/Kimi-K2-Instruct` | 1_000_000_000_000 | 131_072 | `vllm`·{fp8}·1200 GiB · `vllm`·{awq,gptq}·600 GiB · `tensorrt_llm`·{fp8}·1200 GiB |

One entry satisfies the "≥1 entry per advertised family" invariant. `moonshotai/Kimi-VL-A3B-Instruct` derives to `kimi_vl`, which no Provider advertises, so it is out of scope until one does.

**Remaining groups** (tasks phase populates them the same way, ≥1 entry per family): `bge` ← `BAAI/bge-m3`, `BAAI/bge-large-en-v1.5`; `nomic_embed` ← `nomic-ai/nomic-embed-text-v1.5`; `e5` ← `intfloat/multilingual-e5-large`, `intfloat/e5-large-v2`; `jina_embeddings` ← `jinaai/jina-embeddings-v3`; `bge_reranker` ← `BAAI/bge-reranker-v2-m3`; `jina_reranker` ← `jinaai/jina-reranker-v2-base-multilingual`; `qwen_vl` ← `Qwen/Qwen2.5-VL-7B-Instruct`, `Qwen/Qwen2.5-VL-72B-Instruct`; `llama_vision` ← `meta-llama/Llama-3.2-11B-Vision-Instruct`; `whisper` ← `openai/whisper-large-v3`, `openai/whisper-large-v3-turbo`; `kokoro` ← `hexgrad/Kokoro-82M`; `paddleocr` ← `PaddlePaddle/PaddleOCR`. All twelve derive cleanly under the algorithm above; that was verified before this design was written, so no slice discovers a non-derivable name late.

## Testing Strategy

Strict TDD: every slice writes the failing test first. No `pytest-asyncio` and nothing async here — the catalog is entirely synchronous.

### `family_of` (slice 1)

One parametrized table of `(published_name, expected_label)` covering all fourteen archived derivations plus the six generalisation cases, each an `id` so a failure names the model. Separate negative cases: `FamilyDerivationError` for `""`, `"openai/"`, `"large-v3"` (every token dropped), `"7B"`. Plus a property-style assertion that every produced label satisfies both `_FLC_SHAPE` and the banned-token check — the same two predicates the phase-2 harness applies to advertised labels (MC11).

### Query behaviour (slice 2)

Tested against a **fabricated three-entry fixture catalog**, not real data. Query semantics and catalog data are independent concerns and must fail independently; a query bug should not be discoverable only by reading a 300-line entry table. The fixture deliberately includes one model with two tiers on one backend and one model absent from a backend, so `supports`/`quantizations`/`requirements` all have a real negative case.

Construction invariants get one test each: duplicate name → `DuplicateModelError`; `ModelDescriptor(name=PublishedModelName("Qwen/Qwen3-8B"), family=ModelFamily("llama"), ...)` → `FamilyMismatchError`; two `BackendSupport` rows sharing `(vllm, fp16)` → `AmbiguousFootprintError`.

### Structural guards

| Guard | Where | Assertion |
|---|---|---|
| Layering out | slice 1, `test_layering.py` | AST over `src/tibios_ray/catalog/**/*.py`: no `Import`/`ImportFrom` naming `tibios_ray.execution` or `tibios_ray.runtime` |
| Layering in | slice 1, `test_layering.py` | AST over every `src/tibios_ray/**/*.py` **outside** `catalog/`: no import naming `tibios_ray.catalog` — the "zero production callers" claim made mechanical |
| Package-root imports | slice 1, `test_layering.py` | no module under `catalog/` imports `tibios_ray.catalog` itself (CP8's rule, same circular-init hazard) |
| No resolution types in fields | slice 2, `test_no_resolution_types.py` | for every public class in `catalog/`, every `dataclasses.fields()` annotation resolved via `typing.get_type_hints`, unwrapped through `frozenset`/`tuple`/`Mapping` args — no type with `__module__.startswith("tibios_ray.execution")` |
| No resolution types in signatures | slice 2, same file | `inspect.signature` of every public `ModelCatalog` method: same predicate on every parameter and the return annotation |
| No selection surface | slice 2, same file | no callable in `catalog/` named `choose`/`best`/`select`/`plan`; no class in `catalog/` structurally satisfying `ModelSelectionPolicy` (checked by name-set comparison, since the protocol is not `runtime_checkable`) |
| Static rejection | slice 2, `pyright_fixtures/rejects_resolved_model_ref.py` | `catalog.get(resolved_ref)  # type: ignore[arg-type]` plus a no-ignore control `catalog.get(PublishedModelName(...))`; `reportUnnecessaryTypeIgnoreComment = true` fails the build if `get` is ever widened |

### Catalog ↔ descriptor consistency (slice 8)

`tests/unit/catalog/test_catalog_consistency.py`. Descriptors are discovered, not listed (MC10):

```python
def _advertised() -> tuple[CapabilityDescriptor, ...]:
    found: dict[str, CapabilityDescriptor] = {}
    for info in pkgutil.iter_modules(tibios_ray.capabilities.__path__):
        module = importlib.import_module(f"tibios_ray.capabilities.{info.name}")
        for attr, value in vars(module).items():
            if isinstance(value, CapabilityDescriptor):
                found[f"{info.name}.{attr}"] = value
    return tuple(found[key] for key in sorted(found))


def _advertised_backends(family: ModelFamily) -> frozenset[BackendId]:
    """MC8: the union over every descriptor advertising `family`."""
    return frozenset().union(
        *(d.backends for d in _advertised() if family in d.families)
    )
```

Then two parametrized suites plus a sanity check:

| Direction | Parametrized over | Assertion |
|---|---|---|
| descriptor → catalog | every advertised `ModelFamily` (17 distinct), `id=family.value` | `DEFAULT_CATALOG.models(family)` is non-empty — the proposal's "every advertised family has ≥1 entry" |
| catalog → descriptor | every entry in `ALL_ENTRIES`, `id=entry.name.value` | `{row.backend for row in entry.serving} <= _advertised_backends(entry.family)`; `entry.family in advertised_families`; `entry.family == family_of(entry.name)`; `entry.serving` non-empty; `parameter_count > 0`; `context_window > 0`; every `min_vram_bytes > 0` |
| harness sanity | — | `len(_advertised()) == 7` and the seven capability strings match the archived set exactly — so a Provider deleted or renamed upstream fails *here* rather than silently shrinking the parametrization to nothing |

The `entry.family in advertised_families` check is stricter than the proposal requires (which only demands the backend ⊆ direction) and is deliberate: an entry for a family no Provider advertises is dead data that no query path can ever reach, and catching it is free.

Per-group test modules (`test_chat_entries.py`, …) assert only their own data: family coverage within the group, one full `ModelDescriptor` equality per family as the stability assertion, and the derivation round-trip for each name. ~50-70 lines each, no behaviour duplicated — the same division the phase-2 per-Provider files use.

## Module / Slice Plan

`auto-chain`, stacked PRs, each ≤400 changed lines, each green from inside `tibios-ray/` (`uv run pytest && uv run ruff check && uv run pyright`).

| # | Slice | Adds | Est. lines |
|---|---|---|---|
| 1 | Names + FLC | `catalog/errors.py`, `catalog/names.py`, `catalog/__init__.py`, `tests/unit/catalog/{test_errors,test_names,test_layering}.py` | ~340 |
| 2 | Types + query surface | `catalog/model.py`, `catalog/catalog.py`, `__init__.py` update, `tests/unit/catalog/{test_model,test_catalog,test_no_resolution_types}.py`, `pyright_fixtures/rejects_resolved_model_ref.py` | ~390 |
| 3 | Chat A | `catalog/entries/chat.py` (qwen, llama, deepseek — 10 entries), `test_chat_entries.py` | ~330 |
| 4 | Chat B | `catalog/entries/chat.py` (gemma, mistral, kimi — 6 entries), test extension | ~230 |
| 5 | Embedding + Rerank | `catalog/entries/{embedding,rerank}.py` (6 families, ~8 entries), two tests | ~250 |
| 6 | Vision | `catalog/entries/vision.py` (qwen_vl, llama_vision — 3 entries), test | ~180 |
| 7 | Speech + OCR | `catalog/entries/{speech,ocr}.py` (3 families, ~4 entries), two tests | ~170 |
| 8 | Assembly + consistency | `catalog/entries/__init__.py` (`ALL_ENTRIES`, `DEFAULT_CATALOG`), `test_catalog_consistency.py` | ~300 |

**How this refines the proposal's six-slice sketch.**

- The proposal's slice 1 was "types + `family_of` + query surface" — that is ~700 lines together and reviews as three unrelated things. Split into **1** (names + FLC, the load-bearing piece, reviewed on its own with its 20-case derivation table) and **2** (types + the six queries). `family_of` must land first regardless: `ModelCatalog.__init__` calls it to enforce `FamilyMismatchError`.
- The proposal's slice 2 ("chat families") is six families, sixteen entries, ~560 lines of literal data. Split into **3** and **4** at the family boundary. Both append to the same `entries/chat.py`; in a stacked chain that is sequential, so it is a rebase-clean append, not a conflict surface.
- Structural guards land **with the thing they guard**, not with the consistency harness: layering in slice 1 (meaningful the moment `catalog/` exists), the resolution-type guards in slice 2 (meaningful the moment there are types and signatures to introspect). Deferring them to slice 8 would mean five slices of data written without the guard that makes the boundary claim true.
- `entries/__init__.py` and `DEFAULT_CATALOG` land **last** (MC14), so slices 3–7 touch no shared file and each group's tests build a `ModelCatalog` over its own entries only. This is a deliberate departure from phase 2, where every slice touched `capabilities/__init__.py` — there the shared file was a re-export list; here it would be executable assembly whose import-time validation would attribute a slice-7 data bug to a slice-3 test.

Slice 2 at ~390 is the only one near the ceiling. Documented fallback if it exceeds 400: split at the index boundary — 2a delivers `model.py` + `ModelCatalog.__init__`/`families`/`models`/`get` (the `_by_name`/`_by_family` indices), 2b delivers `supports`/`quantizations`/`requirements` (the `_footprints` index) plus the resolution guards.

`src/tibios_ray/worker.py`, `capabilities/`, `selection/`, and `runtime/` stay untouched across all eight slices. That is not incidental — the "layering in" guard in slice 1 makes any accidental wiring a test failure from the first commit onward.

## Migration / Rollout

Purely additive: one new package, twelve new source modules, eleven new test modules, zero edits to any existing file. No frozen module is modified, no contract reshaped, no spec requirement changed. `git revert` of the slice commits restores the archived `capability-providers` state exactly. No data, schema, or contract migration exists because nothing consumes the catalog.

## Open Questions

- [ ] **MoE `parameter_count` is total, not active.** Correct for `min_vram_bytes` (all experts are resident) but wrong for anything throughput-shaped. `Qwen3-30B-A3B` (3.3 B active) and `DeepSeek-V3` (37 B active) both under-report their speed and over-report their cost by this measure. Adding `active_parameter_count` is additive; deferred until a consumer needs it, since inventing a field with zero readers is how catalogs rot.
- [ ] **Names the FLC cannot derive.** `Meta-Llama-*` (vendor echo) and `*-Distill-*` (cross-lineage) are excluded by the `FamilyMismatchError` invariant rather than accommodated. An org-echo drop rule was designed and rejected: dropping a leading token that matches an org token fixes `Meta-Llama` but destroys `nomic-ai/nomic-embed-*` → `embed`. Whether to amend the FLC or keep excluding is a decision for whoever first *needs* one of these models.
- [ ] **Quantization vocabulary owner** — still open, inherited verbatim from `selection/policy.py`'s own open question. This change is the first real pressure on it: the catalog now writes down `awq`, `gptq`, `q4_k_m`, `q8_0`, `fp8`, `fp16`, `int8` as if they were a vocabulary. They are still opaque tokens interpreted by a Phase 4 adapter that does not exist. If Phase 4 disagrees with any of these spellings, the entry tables change — which is why nothing depends on them.
- [ ] **Native vs extended context windows.** Entries record the natively published window (Qwen3: 32 768). YaRN/RoPE-extended windows are a *serving configuration*, so arguably they belong on `BackendSupport` next to the footprint, not on the model. Deferred; no consumer distinguishes them.
- [ ] **`min_vram_bytes`' 1.2 overhead factor is one number for every architecture.** A 131 072-token Llama 3.3 KV cache dwarfs a 32 768-token Qwen3's, and the formula ignores that entirely. Documented as advisory (MC13) and unused by any decision, so the error is currently harmless — but it will not survive first contact with a real admission check.
- [ ] **Whether `families()` may ever be non-exhaustive against the advertisement.** Currently impossible: slice 8's descriptor→catalog direction fails if any advertised family has zero entries. If a future Provider advertises a family whose models are all proprietary/unlistable, that test becomes the thing blocking it, and the decision will be whether to relax it to a warning or to require a placeholder entry.
