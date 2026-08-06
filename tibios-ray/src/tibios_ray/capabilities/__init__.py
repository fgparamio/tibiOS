"""Capability Provider contract (`capability-registry` spec).

See ``openspec/changes/ray-worker-runtime/design.md`` ("capabilities/"
block, design decision D2). This package depends on ``execution/`` (for
`ExecutionContext`/`ExecutionReport`) and ``backends/`` (for
`BackendId`) only — ``runtime/`` depends on ``capabilities/``, never the
reverse.
"""

from tibios_ray.capabilities.descriptor import (
    CapabilityCatalog,
    CapabilityDescriptor,
    CapabilityFlags,
    ModelFamily,
)
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.capabilities.provider import CapabilityProvider

__all__ = [
    "CapabilityCatalog",
    "CapabilityDescriptor",
    "CapabilityFlags",
    "CapabilityName",
    "CapabilityProvider",
    "ModelFamily",
]
