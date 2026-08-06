"""`tibios_ray.selection` re-exports its public vocabulary at the package
level, so consumers write `from tibios_ray.selection import
ModelSelectionPolicy` rather than reaching into submodules — mirrors
`tests/unit/backends/test_backends_exports.py`.
"""

import tibios_ray.selection as selection


def test_package_exports_all_phase_3_public_names() -> None:
    expected = {
        "ModelSelectionPolicy",
        "Quantization",
        "ServingConstraints",
        "ServingPlan",
    }
    assert expected <= set(selection.__all__)
    for name in expected:
        assert hasattr(selection, name), f"tibios_ray.selection.{name} missing"
