"""`tibios_ray.testing` re-exports its public fakes at the package level, so
consumers write `from tibios_ray.testing import StubProvider` rather than
reaching into submodules — mirrors
`tests/unit/runtime/test_runtime_exports.py`.
"""

import tibios_ray.testing as testing


def test_package_exports_all_phase_6_public_names() -> None:
    expected = {
        "FakeExecutionContext",
        "InMemoryExecutionChannel",
        "ManualCancellation",
        "RecordingBackend",
        "StubProvider",
    }
    assert expected <= set(testing.__all__)
    for name in expected:
        assert hasattr(testing, name), f"tibios_ray.testing.{name} missing"
