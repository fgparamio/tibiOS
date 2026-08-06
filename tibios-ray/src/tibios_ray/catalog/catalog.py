"""`ModelCatalog` — immutable, ctor-built index of concrete models,
mirroring `runtime/registry.py`'s `CapabilityRegistry` (design decision
MC6). No `add()`/`register()`; construction validates, then the object is
read-only for life.

Slice 2a builds the `_by_name`/`_by_family` indices and the two
construction invariants that do not depend on a model's serving table
(`DuplicateModelError`, `FamilyMismatchError`), plus `families()`,
`models()`, `get()`. The `_footprints` index, `AmbiguousFootprintError`,
and `supports()`/`quantizations()`/`requirements()` land in slice 2b, per
the documented 2a/2b fallback split (`design.md` Module/Slice Plan).
"""

from collections.abc import Sequence
from types import MappingProxyType

from tibios_ray.capabilities.descriptor import ModelFamily
from tibios_ray.catalog.errors import DuplicateModelError, FamilyMismatchError, UnknownModelError
from tibios_ray.catalog.model import ModelDescriptor
from tibios_ray.catalog.names import PublishedModelName, family_of


class ModelCatalog:
    """Immutable, ctor-built index of concrete models. See module
    docstring and `design.md`'s Key Contracts for the full invariant
    list; slice 2a enforces `DuplicateModelError` and
    `FamilyMismatchError` only."""

    def __init__(self, entries: Sequence[ModelDescriptor]) -> None:
        by_name: dict[PublishedModelName, ModelDescriptor] = {}
        by_family: dict[ModelFamily, list[ModelDescriptor]] = {}

        for entry in entries:
            if entry.name in by_name:
                raise DuplicateModelError(entry.name)
            derived = family_of(entry.name)
            if entry.family != derived:
                raise FamilyMismatchError(entry.name, stated=entry.family, derived=derived)

            by_name[entry.name] = entry
            by_family.setdefault(entry.family, []).append(entry)

        self._by_name: MappingProxyType[PublishedModelName, ModelDescriptor] = MappingProxyType(
            by_name
        )
        self._by_family: MappingProxyType[ModelFamily, tuple[ModelDescriptor, ...]] = (
            MappingProxyType(
                {
                    family: tuple(sorted(models, key=lambda model: model.name.value))
                    for family, models in by_family.items()
                }
            )
        )

    def families(self) -> frozenset[ModelFamily]:
        """Every family with at least one entry. A `frozenset` so it is
        directly comparable with `CapabilityDescriptor.families`."""
        return frozenset(self._by_family)

    def models(self, family: ModelFamily) -> tuple[ModelDescriptor, ...]:
        """Entries in `family`, ordered by `name.value`. Empty tuple for
        an unknown family — "which models are in X" has an honest empty
        answer (MC7)."""
        return self._by_family.get(family, ())

    def get(self, name: PublishedModelName) -> ModelDescriptor:
        """Raises `UnknownModelError` — an identity lookup's absence is a
        caller error, exactly like `CapabilityRegistry.resolve` (MC7)."""
        return self._require(name)

    def _require(self, name: PublishedModelName) -> ModelDescriptor:
        try:
            return self._by_name[name]
        except KeyError:
            raise UnknownModelError(name) from None
