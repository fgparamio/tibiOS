"""`tibios_ray.execution` re-exports its public vocabulary at the package
level, so consumers write `from tibios_ray.execution import ExecutionContext`
rather than reaching into submodules.
"""

import tibios_ray.execution as execution


def test_package_exports_all_phase_1_public_names() -> None:
    expected = {
        "AllocationContract",
        "CancellationToken",
        "CheckpointCreated",
        "ContentHash",
        "EndOfStream",
        "ExecutionChannel",
        "ExecutionContext",
        "ExecutionEvent",
        "ExecutionPhase",
        "ExecutionPulse",
        "ExecutionReport",
        "MetricsSnapshot",
        "ObjectId",
        "ObjectVersion",
        "OutputChunk",
        "Progress",
        "ResolvedModelRef",
        "Warning",
    }
    assert expected <= set(execution.__all__)
    for name in expected:
        assert hasattr(execution, name), f"tibios_ray.execution.{name} missing"
