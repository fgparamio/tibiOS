"""Model Catalog — reference data for the concrete published models
inside each advertised `ModelFamily` (`model-catalog` spec). Adds zero
production callers (design.md): nothing outside `catalog/` and its tests
imports this package, enforced by `tests/unit/catalog/test_layering.py`.

Re-exports value types, `family_of`, `ModelCatalog`, and errors — never
`entries/`'s static data tables. Entry data is filing convenience only
and is reached by importing `tibios_ray.catalog.entries` explicitly, not
through this package root.
"""

from tibios_ray.catalog.catalog import ModelCatalog
from tibios_ray.catalog.errors import (
    AmbiguousFootprintError,
    CatalogError,
    DuplicateModelError,
    FamilyDerivationError,
    FamilyMismatchError,
    UnknownModelError,
    UnsupportedServingError,
)
from tibios_ray.catalog.model import BackendSupport, ModelDescriptor
from tibios_ray.catalog.names import PublishedModelName, family_of

__all__ = [
    "AmbiguousFootprintError",
    "BackendSupport",
    "CatalogError",
    "DuplicateModelError",
    "FamilyDerivationError",
    "FamilyMismatchError",
    "ModelCatalog",
    "ModelDescriptor",
    "PublishedModelName",
    "UnknownModelError",
    "UnsupportedServingError",
    "family_of",
]
