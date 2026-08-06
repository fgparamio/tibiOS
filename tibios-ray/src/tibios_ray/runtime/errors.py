"""Worker Contract-conformant error hierarchy.

`worker-runtime` spec ("Unknown capability yields a Worker Contract
error, not a crash") and `capability-registry` spec ("A Capability
Provider without a catalog is rejected") both require a failure surface
that never crosses the Worker Contract boundary as a bare, unhandled
exception. This module splits that surface into two families:

- `DispatchError` — raised while `WorkerRuntime.execute()` resolves or
  invokes a Capability Provider for one execution. `WorkerRuntime` always
  catches these (and any other exception a Capability Provider raises)
  and translates them into a Failed `ExecutionReport` — they never
  escape across the Worker Contract boundary.
- `RegistrationError` — raised only from `CapabilityRegistry.__init__`,
  at the composition root (`worker.py`), before any `WorkerRuntime`
  exists to catch and translate it. A misconfigured registry is a
  startup failure, not a per-execution one, and is deliberately allowed
  to propagate.
"""

from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.capabilities.provider import CapabilityProvider


class DispatchError(Exception):
    """Base class for dispatch-time failures. `WorkerRuntime.execute()`
    catches every `DispatchError` and translates it into a Failed
    `ExecutionReport` instead of letting it escape across the Worker
    Contract boundary (`worker-runtime` spec: "Unknown capability yields
    a Worker Contract error, not a crash")."""


class UnknownCapabilityError(DispatchError):
    """Raised by `CapabilityRegistry.resolve()` when no Capability
    Provider is registered for the requested capability."""

    def __init__(self, capability: CapabilityName) -> None:
        self.capability = capability
        super().__init__(f"no Capability Provider registered for {capability.value!r}")


class RegistrationError(Exception):
    """Base class for `CapabilityRegistry` construction-time failures.
    Raised only from `__init__` — a startup/composition-root failure, not
    a per-execution `DispatchError` (design decision D6: the registry is
    immutable and built once, so every registration failure is discovered
    before a single execution is ever dispatched)."""


class DuplicateCapabilityError(RegistrationError):
    """Raised when two Capability Providers passed to `CapabilityRegistry`
    advertise the same capability."""

    def __init__(self, capability: CapabilityName) -> None:
        self.capability = capability
        super().__init__(
            f"duplicate Capability Provider registered for {capability.value!r}"
        )


class EmptyCatalogError(RegistrationError):
    """Raised when a Capability Provider passed to `CapabilityRegistry`
    declares no catalog: both `families` and `backends` are empty
    (`capability-registry` spec: "A Capability Provider without a catalog
    is rejected"). `capabilities/descriptor.py`'s `CapabilityDescriptor`
    deliberately allows empty collections — it is a plain value type, not
    a registration; this is where the spec's rejection rule is actually
    enforced, at registration time."""

    def __init__(self, provider: CapabilityProvider) -> None:
        self.provider = provider
        super().__init__(
            f"Capability Provider {type(provider).__name__!r} declares no "
            "catalog (no families and no backends advertised) and cannot "
            "be registered"
        )
