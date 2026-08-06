"""Model Selection Policy contract (`model-selection-policy` spec).

See ``openspec/changes/ray-worker-runtime/design.md`` ("selection/"
block). This package depends on ``execution/`` and ``backends/`` only —
``capabilities/`` and ``runtime/`` depend on ``selection/``, never the
reverse.
"""

from tibios_ray.selection.policy import (
    ModelSelectionPolicy,
    Quantization,
    ServingConstraints,
    ServingPlan,
)

__all__ = [
    "ModelSelectionPolicy",
    "Quantization",
    "ServingConstraints",
    "ServingPlan",
]
