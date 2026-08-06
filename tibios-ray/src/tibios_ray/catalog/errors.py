"""`catalog/`-local failure surface (design decisions MC6, MC7, MC9).

Six concrete failures split by when they are raised: `FamilyDerivationError`
(from `family_of`, when no valid label can be derived) and
`UnknownModelError` / `UnsupportedServingError` are query-time;
`DuplicateModelError`, `FamilyMismatchError`, and `AmbiguousFootprintError`
are construction-time, raised only from `ModelCatalog.__init__`. Every
subclass carries typed payload — the offending `PublishedModelName`, and
for the serving/footprint errors the `BackendId`/`Quantization` involved —
never a bare message (MC7's asymmetric error contract: `get()` and
`requirements()` raise because a scalar/identity lookup has no honest
empty answer).

A shared `CatalogError` base exists here — unlike `capabilities/errors.py`'s
deliberate omission (design decision CP3) — because six failure modes here
share one plausible catch site (a future selection layer asking "could the
catalog answer?") and need discrimination between construction bugs and
query misses; CP3's single-error, single-catch-site case does not apply.

Type-only imports (`PublishedModelName`, `ModelFamily`, `BackendId`,
`Quantization`) are guarded under `TYPE_CHECKING` with
`from __future__ import annotations`: `catalog/names.py` raises
`FamilyDerivationError`, so importing `PublishedModelName` here eagerly
would close a circular import at runtime (`errors.py` -> `names.py` ->
`errors.py`). Static type checking is unaffected — pyright evaluates
`TYPE_CHECKING` imports regardless of runtime import order.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tibios_ray.backends.adapter import BackendId
    from tibios_ray.capabilities.descriptor import ModelFamily
    from tibios_ray.catalog.names import PublishedModelName
    from tibios_ray.selection.policy import Quantization


class CatalogError(Exception):
    """Base for every catalog failure (design decision MC9's error
    hierarchy note)."""


class FamilyDerivationError(CatalogError):
    """Raised by `family_of` when no valid `ModelFamily` label can be
    derived from a `PublishedModelName` — either every token was dropped
    or the derived label violates the FLC shape (design decision MC2)."""

    def __init__(self, name: PublishedModelName, *, reason: str) -> None:
        self.name = name
        self.reason = reason
        super().__init__(f"cannot derive a family label from {name.value!r}: {reason}")


class UnknownModelError(CatalogError):
    """Raised by `ModelCatalog.get()` (and any query that starts from a
    name) when no entry exists for the requested `PublishedModelName` —
    an identity lookup's absence is a caller error, mirroring
    `CapabilityRegistry.resolve` (design decision MC7)."""

    def __init__(self, name: PublishedModelName) -> None:
        self.name = name
        super().__init__(f"no catalog entry for {name.value!r}")


class UnsupportedServingError(CatalogError):
    """Raised by `ModelCatalog.requirements()` when the exact
    (backend, quantization) pair is not in the model's serving table — a
    scalar footprint has no honest empty value (design decision MC7)."""

    def __init__(
        self, name: PublishedModelName, *, backend: BackendId, quantization: Quantization
    ) -> None:
        self.name = name
        self.backend = backend
        self.quantization = quantization
        super().__init__(
            f"{name.value!r} has no serving row for backend {backend.value!r} at "
            f"quantization {quantization!r}"
        )


class DuplicateModelError(CatalogError):
    """Raised by `ModelCatalog.__init__` when two entries share one
    `PublishedModelName` (design decision MC6)."""

    def __init__(self, name: PublishedModelName) -> None:
        self.name = name
        super().__init__(f"duplicate catalog entry for {name.value!r}")


class FamilyMismatchError(CatalogError):
    """Raised by `ModelCatalog.__init__` when an entry's stated `family`
    disagrees with `family_of(entry.name)` — the invariant that keeps
    non-derivable names (e.g. `Meta-Llama-*`) out of the catalog
    mechanically (design decision MC6)."""

    def __init__(
        self, name: PublishedModelName, *, stated: ModelFamily, derived: ModelFamily
    ) -> None:
        self.name = name
        self.stated = stated
        self.derived = derived
        super().__init__(
            f"{name.value!r} states family {stated.value!r} but family_of derives "
            f"{derived.value!r}"
        )


class AmbiguousFootprintError(CatalogError):
    """Raised by `ModelCatalog.__init__` when one entry declares two
    `BackendSupport` rows for the same (backend, quantization) pair — the
    ambiguity the `_footprints` index cannot represent (design decision
    MC6)."""

    def __init__(
        self, name: PublishedModelName, *, backend: BackendId, quantization: Quantization
    ) -> None:
        self.name = name
        self.backend = backend
        self.quantization = quantization
        super().__init__(
            f"{name.value!r} declares two serving rows for backend "
            f"{backend.value!r} at quantization {quantization!r}"
        )
