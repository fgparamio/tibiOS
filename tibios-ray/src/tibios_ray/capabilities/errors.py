"""`capabilities/`-local failure surface (design decisions CP2, CP3, CP4,
D21).

`ProviderExecutionError` is the base of the failure taxonomy the three
*wired* Providers (`ChatProvider`, `EmbeddingProvider`, `RerankProvider`)
raise from `execute()` (`provider-backend-composition` spec: "Failure
Outcomes Are Behaviorally Distinguishable"). Unwired Providers (Vision,
Speech, OCR) still raise only `NoBackendAvailableError` unconditionally.

This family is deliberately a plain `Exception` hierarchy, NOT rooted in
`runtime.errors.DispatchError`: `runtime/errors.py` already imports
`CapabilityName` from `capabilities/names.py` and `CapabilityProvider`
from `capabilities/provider.py`, so importing `DispatchError` back into
`capabilities/` here would close a literal import cycle. Behavior is
identical either way — `WorkerRuntime._dispatch` catches bare
`Exception` around `provider.execute()` and translates it into a Failed
`ExecutionReport`; nothing about that catch site depends on a shared
base class.

`ProviderExecutionError` itself arrives now because it has a caller that
needs it: five behaviorally distinguishable failure types (D21) instead
of CP3's original "exactly one catch site and exactly one error" (a
premise this change breaks). A wired Provider never returns a `FAILED`
report itself — every failure here is a raise that `WorkerRuntime`
translates; only `COMPLETED`/`CANCELLED` are ever returned directly.
"""

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.names import CapabilityName


class ProviderExecutionError(Exception):
    """Base of the wired-Provider failure taxonomy (D21). Never raised
    directly — always one of the five subclasses below."""


class NoBackendAvailableError(ProviderExecutionError):
    """Raised unconditionally by every unwired Provider's `execute()`,
    and by a wired Provider whose injected backend mapping is empty.

    Carries the `capability` that was requested and the `provider` class
    name that raised (CP4: not the provider instance itself — an
    exception the Runtime stringifies onto the Execution Channel should
    not hold a live reference; not the set of advertised backend ids —
    `CapabilityDescriptor.backends` is a `frozenset` whose iteration
    order is nondeterministic, unsuited to a stable error message).
    Re-parented under `ProviderExecutionError` by D21; signature
    unchanged so every pre-existing `pytest.raises(NoBackendAvailableError)`
    still holds."""

    def __init__(self, *, capability: CapabilityName, provider: str) -> None:
        self.capability = capability
        self.provider = provider
        super().__init__(
            f"{provider!r} has no Backend Adapter available to execute "
            f"{capability.value!r}"
        )


class UnresolvableBackendError(ProviderExecutionError):
    """Raised when `ModelSelectionPolicy.plan()` names a `BackendId`
    absent from the Provider's injected mapping — the Provider never
    falls back to another entry (`provider-backend-composition` spec: "A
    plan naming an absent backend fails, not silently picks another").
    `available` is a stable, sorted `tuple[str, ...]` snapshot of the
    mapping's keys, not the mapping itself."""

    def __init__(
        self, *, capability: CapabilityName, backend: BackendId, available: tuple[str, ...]
    ) -> None:
        self.capability = capability
        self.backend = backend
        self.available = available
        super().__init__(
            f"plan named backend {backend.value!r} for {capability.value!r}, "
            f"which is absent from the available backends {available!r}"
        )


class BackendExecutionError(ProviderExecutionError):
    """Wraps an exception raised by a Backend Adapter itself, at one of
    three stages: `acquire`, `execute`, or `release`. Always raised via
    `raise ... from error` so `__cause__` carries the original
    exception — the FAILED report's `failure` string stays
    distinguishable from an internal bug (D21)."""

    def __init__(self, *, backend: BackendId, stage: str, error: Exception) -> None:
        self.backend = backend
        self.stage = stage
        super().__init__(
            f"backend {backend.value!r} raised during {stage!r}: {error!r}"
        )


class MissingModelDependencyError(ProviderExecutionError):
    """Raised by `dispatch.resolve_model_ref` when
    `ExecutionContext.dependencies` is empty — a wired Provider needs
    exactly one `ResolvedModelRef` to call `ModelSelectionPolicy.plan()`
    (D20; `provider-backend-composition` spec: "Zero dependencies fails
    explicitly, not with an unhandled exception")."""

    def __init__(self, *, capability: CapabilityName) -> None:
        self.capability = capability
        super().__init__(
            f"{capability.value!r} execution has no ResolvedModelRef in "
            "context.dependencies"
        )


class RequestParseError(ProviderExecutionError):
    """Raised by a `CapabilityRequest.parse()` classmethod when a
    required parameter is absent or a present parameter is malformed
    (D22, ADR-0004). One shared error type across all three Requests —
    *which* capability/parameter/reason failed is data, not a distinct
    type per capability (mirrors `NoBackendAvailableError`'s own
    `capability=` kwarg, CP4)."""

    def __init__(self, *, capability: CapabilityName, parameter: str, reason: str) -> None:
        self.capability = capability
        self.parameter = parameter
        self.reason = reason
        super().__init__(
            f"{capability.value!r} request parameter {parameter!r} is invalid: {reason}"
        )
