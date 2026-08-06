"""Object identity vocabulary shared across the execution boundary.

`ObjectId`/`ObjectVersion` identify a Logical Object; `ContentHash`
identifies a Content Object (``13-object-model.md``). These are frozen,
slotted dataclasses — never ``NewType[str]`` aliases — precisely so that
``ObjectId("deepseek")`` fails at the type checker and at runtime: a
``NewType`` is a no-op, so a plain string could always impersonate an
identifier. Wrapping the value in a dataclass makes a resolved identity
*type-distinct* from any string an application might construct locally
(design decision D3, ``design.md``).
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ObjectId:
    """Identity of a Logical Object — a ULID string, per Runtime Primitives."""

    value: str


@dataclass(frozen=True, slots=True)
class ObjectVersion:
    """Monotonic version of a Logical Object (``13-object-model.md``)."""

    value: int


@dataclass(frozen=True, slots=True)
class ContentHash:
    """Identity of an immutable Content Object, e.g. ``sha256:...``."""

    value: str
