"""Capability Registry — the immutable, ctor-built index `WorkerRuntime`
dispatches through and the aggregated view it advertises
(`capability-registry` spec: "Capability Provider Interface", "Aggregated
Capability Advertisement").

Built once from an explicit `Sequence[CapabilityProvider]` at the
composition root (`worker.py`) — no `register()` mutation method, no
entry-point auto-discovery (design decision D6: "Auto-discovery/hot-reload
are declared non-goals; immutability satisfies the 'no global mutable
state' anti-pattern."). Two rejection rules are enforced here, not in
`capabilities/descriptor.py`, because they are registration-time
concerns:

- A Capability Provider whose descriptor declares no catalog (no
  families and no backends) is rejected (`capability-registry` spec).
- Two Capability Providers advertising the same capability is rejected —
  the registry's index is one-provider-per-capability by construction.
"""

from collections.abc import Sequence
from types import MappingProxyType

from tibios_ray.capabilities.descriptor import CapabilityCatalog, CapabilityDescriptor
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.capabilities.provider import CapabilityProvider
from tibios_ray.runtime.errors import (
    DuplicateCapabilityError,
    EmptyCatalogError,
    UnknownCapabilityError,
)


def _has_catalog(descriptor: CapabilityDescriptor) -> bool:
    return bool(descriptor.families) or bool(descriptor.backends)


class CapabilityRegistry:
    """Immutable index of registered Capability Providers, built once at
    construction (design decision D6). `WorkerRuntime` dispatches
    exclusively through `resolve()` — it never holds a direct reference
    to a concrete Provider (`worker-runtime` spec: "Dispatch Only via
    Capability Registry")."""

    def __init__(self, providers: Sequence[CapabilityProvider]) -> None:
        by_capability: dict[CapabilityName, CapabilityProvider] = {}
        for provider in providers:
            descriptor = provider.descriptor
            if not _has_catalog(descriptor):
                raise EmptyCatalogError(provider)
            if descriptor.capability in by_capability:
                raise DuplicateCapabilityError(descriptor.capability)
            by_capability[descriptor.capability] = provider
        self._by_capability = MappingProxyType(by_capability)

    def resolve(self, capability: CapabilityName) -> CapabilityProvider:
        """Return the Capability Provider registered for `capability`.
        Raises `UnknownCapabilityError` if none is registered —
        `WorkerRuntime` catches this and translates it into a Failed
        `ExecutionReport`; it never propagates as a bare exception."""
        try:
            return self._by_capability[capability]
        except KeyError:
            raise UnknownCapabilityError(capability) from None

    def catalog(self) -> CapabilityCatalog:
        """The aggregated, read-only view of every registered Provider's
        descriptor — the union `capability-registry`'s spec describes,
        sourced from no hardcoded provider/model/vendor list."""
        return CapabilityCatalog(
            descriptors=frozenset(provider.descriptor for provider in self._by_capability.values())
        )
