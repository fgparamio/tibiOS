"""Family Label Convention (FLC), promoted from `capabilities/`'s
test-only regex to a real production function (design decision MC2).

`family_of` is the archived FLC's executable form (`design.md`, "The FLC
in production"): four phases, no branching on catalog contents, no I/O,
no state — strip the org prefix, tokenise (MC4's alpha->digit boundary
split, guarded to a >=2-letter prefix so `e5`/`m3`/`a3b` are left whole),
drop version/size/quantization/tuning-stage/locale tokens unconditionally,
then keep the head token by construction and drop any *tail* token that
looks like a version mark (MC3: `e5` survives as a head, `m3` is dropped
as a tail — the two are string-identical in shape, so only position can
tell them apart). Purity (FLC rule 5) is what lets the Model Catalog and
the seven Capability Providers agree on `ModelFamily` equality with no
synonym table — `family_of` depends only on `name.value`, never on
catalog contents.
"""

import re
from dataclasses import dataclass

from tibios_ray.capabilities.descriptor import ModelFamily
from tibios_ray.catalog.errors import FamilyDerivationError


@dataclass(frozen=True, slots=True)
class PublishedModelName:
    """The identity a model is published under, e.g. `"Qwen/Qwen3-8B"`.
    Deliberately not named `ModelId` (design decision MC1): unlike
    `execution/ids.py`'s `ObjectId`, this carries no resolution proof —
    it is what a human writes down, not what the Runtime resolved. A
    frozen dataclass, not a `NewType`, for the same reason `ObjectId` is:
    a `NewType` is erased at runtime, so a bare string could impersonate
    it. Positional, not kw-only, matching every other single-field
    wrapper in the codebase (`BackendId`, `ModelFamily`)."""

    value: str


_SEPARATORS = re.compile(r"[^a-z0-9]+")

# MC4: `qwen3` -> ("qwen", "3"); `e5`/`m3`/`a3b` are left whole (the
# alphabetic prefix must be >=2 characters for the split to fire).
_FUSED_VERSION = re.compile(r"^([a-z]{2,})(\d.*)$")

_VERSION_TOKEN = re.compile(r"^v?\d+$")  # 3, 2, 5, v2, v0, 2506
_SIZE_TOKEN = re.compile(r"^[a-z]?\d+(x\d+)?[bmk]$")  # 8b, 82m, 8x7b, a3b, a22b
_QUANT_TOKEN = re.compile(r"^(q\d.*|fp\d+|bf\d+|int\d+|awq|gptq|gguf|mlx)$")
_TAIL_VERSION_MARK = re.compile(r"^[a-z]\d+$")  # m3, k2, r1  (tail only)

_FLC_SHAPE = re.compile(r"^[a-z][a-z0-9_]*$")  # FLC rule 1

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
    _, _, tail = published.rpartition("/")  # phase 1: drop the org prefix
    tokens: list[str] = []
    for part in _SEPARATORS.split(tail.lower()):  # phase 2: tokenise
        if not part:
            continue
        fused = _FUSED_VERSION.fullmatch(part)
        if fused is None:
            tokens.append(part)
        else:
            tokens.append(fused.group(1))
            tokens.append(fused.group(2))
    return tokens


def _is_dropped(token: str) -> bool:  # phase 3
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

    head, *tail = survivors  # phase 4: MC3 head rule
    kept = [head] + [t for t in tail if _TAIL_VERSION_MARK.fullmatch(t) is None]
    label = "_".join(kept)

    if _FLC_SHAPE.fullmatch(label) is None:  # FLC rule 1, belt and braces
        raise FamilyDerivationError(name, reason=f"derived label {label!r} violates FLC shape")
    return ModelFamily(label)
