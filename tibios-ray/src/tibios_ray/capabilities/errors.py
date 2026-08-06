"""`capabilities/`-local failure surface (design decision CP2, CP3, CP4).

`NoBackendAvailableError` is the single error every Capability Provider's
`execute()` raises unconditionally (`capability-providers` spec:
"Uniform No-Backend Execution Failure") — no Provider holds a backend
reference, so none can ever fabricate a COMPLETED `ExecutionReport`.

This is deliberately a plain `Exception` subclass, NOT a
`runtime.errors.DispatchError` subclass: `runtime/errors.py` already
imports `CapabilityName` from `capabilities/names.py` and
`CapabilityProvider` from `capabilities/provider.py`, so importing
`DispatchError` back into `capabilities/` here would close a literal
import cycle. Behavior is identical either way — `WorkerRuntime._dispatch`
catches bare `Exception` around `provider.execute()` and translates it
into a Failed `ExecutionReport`; nothing about that catch site depends on
a shared base class.

No `CapabilityError` base class either (CP3) — `runtime/errors.py` splits
its two families because they have two different catch sites; here there
is exactly one catch site and exactly one error, so a base class would
add indirection with no caller that needs it.
"""

from tibios_ray.capabilities.names import CapabilityName


class NoBackendAvailableError(Exception):
    """Raised unconditionally by every Capability Provider's `execute()`.

    Carries the `capability` that was requested and the `provider` class
    name that raised (CP4: not the provider instance itself — an
    exception the Runtime stringifies onto the Execution Channel should
    not hold a live reference; not the set of advertised backend ids —
    `CapabilityDescriptor.backends` is a `frozenset` whose iteration
    order is nondeterministic, unsuited to a stable error message)."""

    def __init__(self, *, capability: CapabilityName, provider: str) -> None:
        self.capability = capability
        self.provider = provider
        super().__init__(
            f"{provider!r} has no Backend Adapter available to execute "
            f"{capability.value!r}"
        )
