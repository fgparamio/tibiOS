"""Whole-catalog conformance harness (design decision CP7) — the other
half of the shared conformance harness alongside
`test_provider_conformance.py`. Both key off the same `_PROVIDERS` typed
tuple; this module imports it rather than redeclaring it, so every slice
still only ever appends one line, in `test_provider_conformance.py`.

Lands with slice 3 — the first slice where two or more Providers exist,
since co-registration/union/round-trip are vacuous with a single Provider
(design.md, Module / Slice Plan).
"""

import ast
from pathlib import Path

import tibios_ray
from capabilities.test_provider_conformance import _PROVIDERS
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.runtime.registry import CapabilityRegistry

_CAPABILITIES_ROOT = Path(tibios_ray.__file__).resolve().parent / "capabilities"

_THRESHOLD_OPS = (ast.If, ast.Match, ast.Compare, ast.IfExp)


def _provider_module_paths() -> list[Path]:
    """One file path per distinct module backing a Provider in
    `_PROVIDERS` — deduped, since `speech.py` will hold two Providers."""
    seen: dict[str, Path] = {}
    for provider in _PROVIDERS:
        module_name = type(provider).__module__
        if module_name in seen:
            continue
        module = __import__(module_name, fromlist=["__file__"])
        seen[module_name] = Path(module.__file__)
    return sorted(seen.values())


def _all_capabilities_source_files() -> list[Path]:
    return sorted(_CAPABILITIES_ROOT.rglob("*.py"))


class TestCatalogConformance:
    def test_all_providers_register_together_without_rejection(self) -> None:
        registry = CapabilityRegistry(list(_PROVIDERS))

        assert registry is not None

    def test_catalog_returns_the_union_of_every_descriptor(self) -> None:
        registry = CapabilityRegistry(list(_PROVIDERS))

        catalog = registry.catalog()

        assert catalog.descriptors == frozenset(provider.descriptor for provider in _PROVIDERS)
        assert len(catalog.descriptors) == len(_PROVIDERS)

    def test_resolve_round_trips_every_provider_by_capability(self) -> None:
        registry = CapabilityRegistry(list(_PROVIDERS))

        for provider in _PROVIDERS:
            assert registry.resolve(provider.descriptor.capability) is provider

    def test_capability_string_set_matches_exactly(self) -> None:
        registry = CapabilityRegistry(list(_PROVIDERS))

        capability_strings = {
            descriptor.capability.value for descriptor in registry.catalog().descriptors
        }

        expected = {provider.descriptor.capability.value for provider in _PROVIDERS}
        assert capability_strings == expected
        # Every provider currently registered must resolve to a real
        # CapabilityName instance sharing the same string vocabulary.
        assert all(
            isinstance(provider.descriptor.capability, CapabilityName) for provider in _PROVIDERS
        )

    def test_no_branching_exists_in_any_provider_module(self) -> None:
        violations: dict[str, list[str]] = {}

        for path in _provider_module_paths():
            tree = ast.parse(path.read_text())
            found = [
                type(node).__name__ for node in ast.walk(tree) if isinstance(node, _THRESHOLD_OPS)
            ]
            if found:
                violations[str(path)] = found

        assert not violations, (
            "found a conditional/comparison node in a Provider module — "
            "no Provider may branch on anything until Phase 4 lands real "
            f"execution (design.md 'No branching' check): {violations}"
        )

    def test_capabilities_package_imports_nothing_from_runtime(self) -> None:
        violations: dict[str, list[str]] = {}

        for path in _all_capabilities_source_files():
            tree = ast.parse(path.read_text())
            found: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    found.extend(
                        alias.name
                        for alias in node.names
                        if alias.name.startswith("tibios_ray.runtime")
                    )
                elif (
                    isinstance(node, ast.ImportFrom)
                    and node.module
                    and node.module.startswith("tibios_ray.runtime")
                ):
                    found.append(node.module)
            if found:
                violations[str(path)] = found

        assert not violations, (
            "found an import from tibios_ray.runtime inside "
            f"capabilities/ — this closes the layering CP2 depends on: {violations}"
        )
