"""Catalog <-> descriptor consistency harness (`design.md`'s "Catalog
<-> descriptor consistency (slice 8)"). Every earlier per-group test
file (`test_chat_entries.py`, `test_vision_entries.py`, ...) deliberately
asserted only its own data (design.md, "assert only their own data" per-
group test scoping) — this is where the full, end-to-end check finally
runs, over the fully assembled `DEFAULT_CATALOG`:

- descriptor -> catalog: every family advertised by any of the seven
  Capability Providers has >=1 entry in `DEFAULT_CATALOG`.
- catalog -> descriptor: every entry's backends are a subset of the
  UNION of backends advertised for that family across every Provider
  that advertises it (MC8's union rule) -- `gemma`, advertised by both
  `chat.generate` and `vision.understand`, is the two-capability case
  this proves for the first time end-to-end, rather than per-group.

Descriptors are discovered by module introspection over
`tibios_ray.capabilities` (MC10), never a hand-maintained tuple --
`_advertised()` below is design.md's Testing Strategy code verbatim.
"""

import importlib
import pkgutil

import pytest

import tibios_ray.capabilities
from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import CapabilityDescriptor, ModelFamily
from tibios_ray.catalog.entries import ALL_ENTRIES, DEFAULT_CATALOG
from tibios_ray.catalog.model import ModelDescriptor
from tibios_ray.catalog.names import family_of


def _advertised() -> tuple[CapabilityDescriptor, ...]:
    found: dict[str, CapabilityDescriptor] = {}
    for info in pkgutil.iter_modules(tibios_ray.capabilities.__path__):
        module = importlib.import_module(f"tibios_ray.capabilities.{info.name}")
        for attr, value in vars(module).items():
            if isinstance(value, CapabilityDescriptor):
                found[f"{info.name}.{attr}"] = value
    return tuple(found[key] for key in sorted(found))


def _advertised_families() -> frozenset[ModelFamily]:
    return frozenset().union(*(descriptor.families for descriptor in _advertised()))


def _advertised_backends(family: ModelFamily) -> frozenset[BackendId]:
    """MC8: the union over every descriptor advertising `family`."""
    return frozenset().union(
        *(descriptor.backends for descriptor in _advertised() if family in descriptor.families)
    )


_ADVERTISED_FAMILIES = sorted(_advertised_families(), key=lambda family: family.value)

_EXPECTED_CAPABILITY_NAMES = frozenset(
    {
        "chat.generate",
        "embedding.generate",
        "rerank.documents",
        "vision.understand",
        "speech.transcribe",
        "speech.synthesize",
        "ocr.extract",
    }
)


class TestHarnessSanity:
    # A Provider deleted or renamed upstream must fail *here*, rather
    # than silently shrinking the parametrizations below to nothing.
    def test_discovers_exactly_seven_descriptors(self) -> None:
        assert len(_advertised()) == 7

    def test_discovered_capability_names_match_the_archived_set(self) -> None:
        discovered = {descriptor.capability.value for descriptor in _advertised()}
        assert discovered == _EXPECTED_CAPABILITY_NAMES

    def test_discovers_seventeen_distinct_advertised_families(self) -> None:
        # 6 chat + 4 embedding + 2 rerank + 3 vision (qwen_vl,
        # llama_vision, gemma) + 2 speech + 1 ocr = 18, minus 1 for
        # gemma (advertised by both chat.generate and vision.understand).
        assert len(_advertised_families()) == 17


class TestDescriptorToCatalog:
    @pytest.mark.parametrize(
        "family", _ADVERTISED_FAMILIES, ids=[family.value for family in _ADVERTISED_FAMILIES]
    )
    def test_every_advertised_family_has_at_least_one_catalog_entry(
        self, family: ModelFamily
    ) -> None:
        assert DEFAULT_CATALOG.models(family)


class TestCatalogToDescriptor:
    @pytest.mark.parametrize("entry", ALL_ENTRIES, ids=[entry.name.value for entry in ALL_ENTRIES])
    def test_entry_backends_are_a_subset_of_the_advertised_union(
        self, entry: ModelDescriptor
    ) -> None:
        entry_backends = {row.backend for row in entry.serving}
        assert entry_backends <= _advertised_backends(entry.family)

    @pytest.mark.parametrize("entry", ALL_ENTRIES, ids=[entry.name.value for entry in ALL_ENTRIES])
    def test_entry_family_is_advertised(self, entry: ModelDescriptor) -> None:
        # Stricter than the proposal's bare minimum (design.md): an
        # entry for a family no Provider advertises is dead data with
        # no reachable query path, caught for free.
        assert entry.family in _advertised_families()

    @pytest.mark.parametrize("entry", ALL_ENTRIES, ids=[entry.name.value for entry in ALL_ENTRIES])
    def test_entry_family_matches_family_of(self, entry: ModelDescriptor) -> None:
        assert entry.family == family_of(entry.name)

    @pytest.mark.parametrize("entry", ALL_ENTRIES, ids=[entry.name.value for entry in ALL_ENTRIES])
    def test_entry_serving_is_non_empty(self, entry: ModelDescriptor) -> None:
        assert entry.serving

    @pytest.mark.parametrize("entry", ALL_ENTRIES, ids=[entry.name.value for entry in ALL_ENTRIES])
    def test_entry_parameter_count_is_positive(self, entry: ModelDescriptor) -> None:
        assert entry.parameter_count > 0

    @pytest.mark.parametrize("entry", ALL_ENTRIES, ids=[entry.name.value for entry in ALL_ENTRIES])
    def test_entry_context_window_is_positive(self, entry: ModelDescriptor) -> None:
        assert entry.context_window > 0

    @pytest.mark.parametrize("entry", ALL_ENTRIES, ids=[entry.name.value for entry in ALL_ENTRIES])
    def test_entry_every_serving_row_has_positive_min_vram(self, entry: ModelDescriptor) -> None:
        assert all(row.min_vram_gb > 0 for row in entry.serving)


class TestAllEntriesAssembly:
    def test_all_entries_has_exactly_one_gemma_entry_set_not_a_duplicate(self) -> None:
        # entries/vision.py deliberately does not restate gemma (MC8/
        # MC12, confirmed in Phase 4/6) -- assembling every group
        # together must not accidentally duplicate it either. Verified
        # here, not merely assumed from the individual groups' isolation.
        gemma = ModelFamily("gemma")
        gemma_names = [entry.name.value for entry in ALL_ENTRIES if entry.family == gemma]
        assert len(gemma_names) == len(set(gemma_names))
        assert sorted(gemma_names) == [
            "google/gemma-3-12b-it",
            "google/gemma-3-27b-it",
            "google/gemma-3-4b-it",
        ]

    def test_default_catalog_families_match_all_entries_families(self) -> None:
        assert DEFAULT_CATALOG.families() == frozenset(entry.family for entry in ALL_ENTRIES)
