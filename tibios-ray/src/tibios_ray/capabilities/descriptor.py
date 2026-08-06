"""Capability catalog vocabulary (`capability-registry` spec).

A Capability Provider advertises a `CapabilityDescriptor`: which
capability it implements, which model families and backends it supports,
and which capability flags (streaming/tools/json/reasoning) it exposes —
never a hardcoded model list (`proposal.md`: "Design Principle:
Capability-First, Not Model-Pinned"). `CapabilityCatalog` is the
aggregated, read-only view of every registered Provider's descriptor
that `capability-registry`'s spec describes ("Aggregated Capability
Advertisement"); `runtime/`'s `CapabilityRegistry` (Phase 5) is what
builds one from a provider sequence and rejects duplicate capabilities —
this module only defines the value type it returns.

`ModelFamily` is outward catalog metadata only, per `design.md`'s
boundary rule: "Family strings appear only in `CapabilityDescriptor`
(outward advertisement); they never enter the inward execution path."
Unlike `execution/ids.py`'s `ObjectId`/`ContentHash` (proof-carrying
resolved identity, design decision D3), a `ModelFamily` carries no
resolution proof — it is a plain advertised label (e.g. `"deepseek"`,
`"qwen"`), matching `backends/adapter.py`'s `BackendId` shape (a single
opaque `value: str`, frozen, slotted) rather than being over-engineered
into a closed enum or a richer type.
"""

from dataclasses import dataclass, field

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.names import CapabilityName


@dataclass(frozen=True, slots=True)
class ModelFamily:
    """Outward-advertised model family label, e.g. `"deepseek"`,
    `"qwen"`, `"llama"`. Catalog metadata only — never used to resolve or
    select a concrete model (that is `ResolvedModelRef`'s job, already
    resolved by the Runtime before an execution starts)."""

    value: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CapabilityFlags:
    """Capability flags a Provider advertises for its capability, per
    `capability-registry` spec: streaming, tool calling, structured JSON
    output, and reasoning. All default to `False` — a Provider opts in
    explicitly to what it actually supports."""

    streaming: bool = False
    tools: bool = False
    json: bool = False
    reasoning: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class CapabilityDescriptor:
    """The catalog shape Scheduling's Capability Filter eventually
    consumes (`design.md` Key Contracts): which capability, which model
    families, which backends, which flags. Every field is hashable so a
    `CapabilityDescriptor` can itself be aggregated into a
    `CapabilityCatalog`'s `frozenset`."""

    capability: CapabilityName
    families: frozenset[ModelFamily] = field(default_factory=frozenset)
    backends: frozenset[BackendId] = field(default_factory=frozenset)
    flags: CapabilityFlags = field(default_factory=CapabilityFlags)


@dataclass(frozen=True, slots=True)
class CapabilityCatalog:
    """Aggregated, read-only view of all registered Capability
    Providers' descriptors (`capability-registry` spec: "Aggregated
    Capability Advertisement" — the union of every registered Provider's
    catalog, sourced from no hardcoded list). Construction, deduping, and
    duplicate-capability rejection are `runtime/`'s `CapabilityRegistry`
    responsibility (Phase 5); this type only carries the resulting
    immutable view."""

    descriptors: frozenset[CapabilityDescriptor]
