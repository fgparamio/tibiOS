"""Model-reference selection, backend resolution, and report builders
shared by the three wired Providers (`ChatProvider`, `EmbeddingProvider`,
`RerankProvider`) — module-level pure functions, no state (D18/D20/D21).

Everything a wired Provider needs that is *not* capability-specific
lives here, so each Provider's `execute()` body stays roughly its own
modality's worth of code and the "no selection logic" guard has almost
nothing to police (`design.md`'s Technical Approach).

`resolve_backend`'s `provider: str` keyword-only parameter is not shown
in `design.md`'s Key Contracts sketch (which lists only `capability`),
but `NoBackendAvailableError`'s own signature is pinned "unchanged" by
D21 and requires a `provider` class name — the same `type(self).__name__`
each wired Provider already passes when raising it directly. The sketch
omission is a Key-Contracts abbreviation, not a spec requirement:
nothing in `provider-backend-composition/spec.md` fixes `resolve_backend`'s
exact parameter list, only the behavioral outcome (a distinguishable
"no backend configured" failure) — the deliberately-frozen NoBackendAvailableError
signature is honored here by having callers (the wired Providers,
Slice 4/5) supply their own class name exactly as they do today.
"""

from collections.abc import Mapping
from datetime import timedelta
from time import monotonic

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.errors import (
    MissingModelDependencyError,
    NoBackendAvailableError,
    UnresolvableBackendError,
)
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.execution.context import ExecutionContext, ResolvedModelRef
from tibios_ray.execution.events import Warning as WarningEvent
from tibios_ray.execution.report import ExecutionPhase, ExecutionReport
from tibios_ray.selection.policy import ModelSelectionPolicy, ServingConstraints, ServingPlan


async def resolve_model_ref(
    context: ExecutionContext, *, capability: CapabilityName
) -> ResolvedModelRef:
    """Select the one `ResolvedModelRef` a wired Provider's `execute()`
    passes to `ModelSelectionPolicy.plan()` (D20).

    Zero entries in `context.dependencies` fails explicitly with
    `MissingModelDependencyError` — never an unhandled `IndexError`.
    More than one entry uses `dependencies[0]` (an ordered tuple, D10 —
    index 0 is stable across processes) and emits exactly one `Warning`
    event (`code="extra_dependencies"`) naming the count, so the
    ignoring is visible rather than silent."""

    dependencies = context.dependencies
    if not dependencies:
        raise MissingModelDependencyError(capability=capability)
    first = dependencies[0]

    if len(dependencies) > 1:
        await context.channel.emit(
            WarningEvent(
                message=(
                    f"{capability.value!r} execution received "
                    f"{len(dependencies)} dependencies; using the first "
                    "and ignoring the rest"
                ),
                code="extra_dependencies",
            )
        )

    return first


def resolve_backend[B](
    backends: Mapping[BackendId, B],
    policy: ModelSelectionPolicy,
    model: ResolvedModelRef,
    *,
    capability: CapabilityName,
    provider: str,
) -> tuple[B, ServingPlan]:
    """Resolve which Backend a wired Provider dispatches to (ADR-0002's
    flow): build `ServingConstraints` from `backends`' keys, call
    `policy.plan(...)`, then look up `plan.backend` in `backends`.

    An empty mapping fails as `NoBackendAvailableError` before the
    policy is even consulted — "no backend configured" is a property of
    the injected mapping, not something a policy call can determine
    (`provider-backend-composition` spec: "Empty mapping fails
    distinguishably from an absent-backend plan"). A plan naming a
    `BackendId` absent from `backends` fails as `UnresolvableBackendError`
    and never falls back to another entry (spec: "A plan naming an
    absent backend fails, not silently picks another")."""

    if not backends:
        raise NoBackendAvailableError(capability=capability, provider=provider)

    constraints = ServingConstraints(available_backends=frozenset(backends))
    plan = policy.plan(model, constraints)

    if plan.backend not in backends:
        raise UnresolvableBackendError(
            capability=capability,
            backend=plan.backend,
            available=tuple(sorted(backend.value for backend in backends)),
        )

    return backends[plan.backend], plan


def completed_report(*, started_at: float, trace_id: str) -> ExecutionReport:
    """Build the `COMPLETED` `ExecutionReport` a wired Provider returns
    after a successful dispatch (D21). Never carries application
    output — that travels only through `context.channel` (D24)."""

    return ExecutionReport(
        phase=ExecutionPhase.COMPLETED,
        duration=timedelta(seconds=monotonic() - started_at),
        resource_usage={},
        metrics={},
        trace_id=trace_id,
    )


def cancelled_report(*, started_at: float, trace_id: str) -> ExecutionReport:
    """Build the `CANCELLED` `ExecutionReport` a wired Provider returns
    after observing `context.cancellation` mid-execution (D21).
    Cancellation is not raised as an exception (D5) — it is returned as
    a report, like `completed_report`."""

    return ExecutionReport(
        phase=ExecutionPhase.CANCELLED,
        duration=timedelta(seconds=monotonic() - started_at),
        resource_usage={},
        metrics={},
        trace_id=trace_id,
    )
