"""`tibios_ray.capabilities` re-exports its public vocabulary at the
package level, so consumers write `from tibios_ray.capabilities import
CapabilityProvider` rather than reaching into submodules — mirrors
`tests/unit/selection/test_selection_exports.py`.
"""

import tibios_ray.capabilities as capabilities


def test_package_exports_all_phase_4_public_names() -> None:
    expected = {
        "CapabilityCatalog",
        "CapabilityDescriptor",
        "CapabilityFlags",
        "CapabilityName",
        "CapabilityProvider",
        "ModelFamily",
    }
    assert expected <= set(capabilities.__all__)
    for name in expected:
        assert hasattr(capabilities, name), f"tibios_ray.capabilities.{name} missing"
