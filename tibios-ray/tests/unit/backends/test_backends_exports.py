"""`tibios_ray.backends` re-exports its public vocabulary at the package
level, so consumers write `from tibios_ray.backends import BackendAdapter`
rather than reaching into submodules — mirrors
`tests/unit/execution/test_package_exports.py`.
"""

import tibios_ray.backends as backends


def test_package_exports_all_phase_2_public_names() -> None:
    expected = {
        "AudioRef",
        "BackendAdapter",
        "BackendId",
        "BackendSession",
        "EmbeddingBackend",
        "RerankBackend",
        "RerankResult",
        "TextChunk",
        "TextGenerationBackend",
        "TextRequest",
        "TranscriptionBackend",
        "TranscriptSegment",
        "Vector",
    }
    assert expected <= set(backends.__all__)
    for name in expected:
        assert hasattr(backends, name), f"tibios_ray.backends.{name} missing"
