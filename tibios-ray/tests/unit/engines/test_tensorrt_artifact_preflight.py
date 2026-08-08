"""`tensorrt-llm-text-backend` spec, Requirement "Missing or Incompatible
Engine Artifact Is a Configuration Error, Never Recovered Dynamically" —
Scenario "A configured but nonexistent or incompatible artifact fails
construction explicitly" (design decision D39).

`default_engine_factory`'s pre-flight predicate MUST run entirely on the
filesystem, before `tensorrt_llm` is ever imported: a missing path, a
path that is a file rather than a directory, and a directory containing
no `*.engine` file must each raise an actionable, `ConfigError`-shaped
failure (`InvalidEngineArtifactError`, module-local — `engines/` may
import only `tibios_ray.backends`, per the layering guard, so the real
`config.ConfigError` cannot be reused here) naming
`TIBIOS_RAY_TENSORRT_ENGINE_PATH`.

Every test sabotages `sys.modules["tensorrt_llm"]` with a module whose
every attribute access raises — proving the predicate short-circuits
before the SDK is ever touched, not merely that it happens to raise
first.
"""

import asyncio
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tibios_ray.engines.tensorrt import InvalidEngineArtifactError, default_engine_factory


class _ExplodingTensorrtLlmModule(ModuleType):
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(
            f"tensorrt_llm.{name} was accessed — the SDK must never be reached "
            "when the D39 pre-flight artifact check fails"
        )


@pytest.fixture
def sabotaged_tensorrt_llm_module() -> Any:
    previous = sys.modules.get("tensorrt_llm")
    sys.modules["tensorrt_llm"] = _ExplodingTensorrtLlmModule("tensorrt_llm")
    try:
        yield
    finally:
        if previous is None:
            del sys.modules["tensorrt_llm"]
        else:
            sys.modules["tensorrt_llm"] = previous


def test_missing_path_raises_naming_the_env_var(
    tmp_path: Path, sabotaged_tensorrt_llm_module: None
) -> None:
    missing = tmp_path / "does-not-exist"

    with pytest.raises(InvalidEngineArtifactError) as exc_info:
        asyncio.run(default_engine_factory(str(missing)))

    assert exc_info.value.variable == "TIBIOS_RAY_TENSORRT_ENGINE_PATH"
    assert "TIBIOS_RAY_TENSORRT_ENGINE_PATH" in str(exc_info.value)


def test_path_that_is_a_file_raises_naming_the_env_var(
    tmp_path: Path, sabotaged_tensorrt_llm_module: None
) -> None:
    a_file = tmp_path / "not-a-directory"
    a_file.write_text("")

    with pytest.raises(InvalidEngineArtifactError) as exc_info:
        asyncio.run(default_engine_factory(str(a_file)))

    assert exc_info.value.variable == "TIBIOS_RAY_TENSORRT_ENGINE_PATH"
    assert "TIBIOS_RAY_TENSORRT_ENGINE_PATH" in str(exc_info.value)


def test_directory_without_engine_file_raises_naming_the_env_var(
    tmp_path: Path, sabotaged_tensorrt_llm_module: None
) -> None:
    empty_dir = tmp_path / "empty-engine-dir"
    empty_dir.mkdir()

    with pytest.raises(InvalidEngineArtifactError) as exc_info:
        asyncio.run(default_engine_factory(str(empty_dir)))

    assert exc_info.value.variable == "TIBIOS_RAY_TENSORRT_ENGINE_PATH"
    assert "TIBIOS_RAY_TENSORRT_ENGINE_PATH" in str(exc_info.value)


def test_directory_with_an_engine_file_passes_preflight_and_reaches_the_sdk(
    tmp_path: Path,
) -> None:
    # Companion/triangulation case: proves the previous three failures
    # are not vacuous (the predicate does not reject every path) — a
    # directory that *does* satisfy D39's shape reaches the (here,
    # deliberately broken) SDK import instead of InvalidEngineArtifactError.
    engine_dir = tmp_path / "engine"
    engine_dir.mkdir()
    (engine_dir / "rank0.engine").write_text("")
    previous = sys.modules.pop("tensorrt_llm", None)
    try:
        with pytest.raises(ModuleNotFoundError):
            asyncio.run(default_engine_factory(str(engine_dir)))
    finally:
        if previous is not None:
            sys.modules["tensorrt_llm"] = previous
