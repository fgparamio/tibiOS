"""Worker Runtime lifecycle host (`worker-runtime` + `capability-registry`
specs).

See ``openspec/changes/ray-worker-runtime/design.md`` ("runtime/" block,
design decisions D2/D6). This package depends on ``capabilities/`` (for
`CapabilityProvider`/`CapabilityDescriptor`/`CapabilityCatalog`) and
``execution/`` (for `ExecutionContext`/`ExecutionReport`/`ExecutionEvent`)
— nothing depends on ``runtime/`` in return; it sits at the top of the
module dependency chain (`runtime -> capabilities -> selection ->
backends`).

`WorkerRuntime` is the sole sanctioned "Worker"-named identifier anywhere
in tibios-ray; see `tests/unit/runtime/test_naming_audit.py`.
"""

from tibios_ray.runtime.errors import (
    DispatchError,
    DuplicateCapabilityError,
    EmptyCatalogError,
    RegistrationError,
    UnknownCapabilityError,
)
from tibios_ray.runtime.registry import CapabilityRegistry
from tibios_ray.runtime.worker_runtime import WorkerRuntime

__all__ = [
    "CapabilityRegistry",
    "DispatchError",
    "DuplicateCapabilityError",
    "EmptyCatalogError",
    "RegistrationError",
    "UnknownCapabilityError",
    "WorkerRuntime",
]
