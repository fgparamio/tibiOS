"""`ModelCatalog` — immutable, ctor-built index of concrete models,
mirroring `runtime/registry.py`'s `CapabilityRegistry` (design decision
MC6). No `add()`/`register()`; construction validates, then the object is
read-only for life.

Three construction-time invariants, each with its own error:
  - no duplicate `PublishedModelName`                          -> `DuplicateModelError`
  - `entry.family == family_of(entry.name)`                    -> `FamilyMismatchError`
  - no `(backend, quantization)` pair repeated across two
    `BackendSupport` rows of one entry                         -> `AmbiguousFootprintError`

`_footprints` is where `AmbiguousFootprintError` comes from: a duplicate
key during construction *is* the ambiguity, so the invariant and the
index are the same object and cannot be forgotten (MC6).

Asymmetric error contract (MC7): `get()`/`requirements()` raise because
an identity lookup / scalar footprint has no honest empty answer;
`models()`/`supports()`/`quantizations()` answer emptily/falsely instead.
"""

from collections.abc import Sequence
from types import MappingProxyType

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import ModelFamily
from tibios_ray.catalog.errors import (
    AmbiguousFootprintError,
    DuplicateModelError,
    FamilyMismatchError,
    UnknownModelError,
    UnsupportedServingError,
)
from tibios_ray.catalog.model import ModelDescriptor
from tibios_ray.catalog.names import PublishedModelName, family_of
from tibios_ray.selection.policy import Quantization

_FootprintKey = tuple[PublishedModelName, BackendId, Quantization]


class ModelCatalog:
    """Immutable, ctor-built index of concrete models. See module
    docstring and `design.md`'s Key Contracts for the full invariant
    list and error contract."""

    def __init__(self, entries: Sequence[ModelDescriptor]) -> None:
        by_name: dict[PublishedModelName, ModelDescriptor] = {}
        by_family: dict[ModelFamily, list[ModelDescriptor]] = {}
        footprints: dict[_FootprintKey, int] = {}

        for entry in entries:
            if entry.name in by_name:
                raise DuplicateModelError(entry.name)
            derived = family_of(entry.name)
            if entry.family != derived:
                raise FamilyMismatchError(entry.name, stated=entry.family, derived=derived)

            for row in entry.serving:
                for quantization in row.quantizations:
                    key: _FootprintKey = (entry.name, row.backend, quantization)
                    if key in footprints:
                        raise AmbiguousFootprintError(
                            entry.name, backend=row.backend, quantization=quantization
                        )
                    footprints[key] = row.min_vram_gb

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
        self._footprints: MappingProxyType[_FootprintKey, int] = MappingProxyType(footprints)

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

    def supports(self, name: PublishedModelName, backend: BackendId) -> bool:
        """`False` for a known model on an unadvertised backend;
        `UnknownModelError` for an unknown model. The backend is the
        question, the model is the subject (MC7)."""
        entry = self._require(name)
        return any(row.backend == backend for row in entry.serving)

    def quantizations(
        self, name: PublishedModelName, backend: BackendId
    ) -> frozenset[Quantization]:
        """Union across every `BackendSupport` row for `backend`. Empty
        when `supports()` is `False`; `UnknownModelError` for an unknown
        model."""
        entry = self._require(name)
        result: frozenset[Quantization] = frozenset()
        for row in entry.serving:
            if row.backend == backend:
                result |= row.quantizations
        return result

    def requirements(
        self, name: PublishedModelName, backend: BackendId, quantization: Quantization
    ) -> int:
        """Advisory minimum VRAM in bytes for that exact triple — a pure
        lookup against `_footprints`, no arithmetic (MC5). Raises
        `UnsupportedServingError` when the pair is not in the model's
        serving table: a scalar has no honest empty value, and `None`
        would push every caller into a branch (MC7)."""
        self._require(name)  # raises UnknownModelError for an unknown model
        try:
            return self._footprints[(name, backend, quantization)]
        except KeyError:
            raise UnsupportedServingError(
                name, backend=backend, quantization=quantization
            ) from None

    def _require(self, name: PublishedModelName) -> ModelDescriptor:
        try:
            return self._by_name[name]
        except KeyError:
            raise UnknownModelError(name) from None
