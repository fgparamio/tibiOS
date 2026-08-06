"""`tibios_ray.runtime` re-exports its public vocabulary at the package
level, so consumers write `from tibios_ray.runtime import WorkerRuntime`
rather than reaching into submodules — mirrors
`tests/unit/capabilities/test_capabilities_exports.py`.
"""

import tibios_ray.runtime as runtime


def test_package_exports_all_phase_5_public_names() -> None:
    expected = {
        "CapabilityRegistry",
        "DispatchError",
        "DuplicateCapabilityError",
        "EmptyCatalogError",
        "RegistrationError",
        "UnknownCapabilityError",
        "WorkerRuntime",
    }
    assert expected <= set(runtime.__all__)
    for name in expected:
        assert hasattr(runtime, name), f"tibios_ray.runtime.{name} missing"
