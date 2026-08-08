"""design decision D35 — "Construction is blocking": `default_engine_
factory`'s SDK constructor call MUST run off the event loop
(`asyncio.to_thread`), never on-loop, since `tensorrt_llm.LLM(...)` is a
plain synchronous constructor that loads an engine into VRAM.

Two complementary techniques, both against the real, unmocked
`asyncio.to_thread`:

- Thread-identity assertion: a fake `tensorrt_llm.LLM` (the "injected
  factory" target) records the OS thread it was constructed on; the
  test asserts that thread differs from the one running the event loop.
- A thin recording wrapper around `asyncio.to_thread` proves the
  production code actually routes through it, rather than happening to
  construct on a coincidentally-different thread some other way.
"""

import asyncio
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tibios_ray.engines.tensorrt import default_engine_factory


class _ThreadRecordingLLM:
    """Stands in for `tensorrt_llm.LLM` — records the OS thread identity
    at construction time, nothing else."""

    def __init__(self, *, model: str) -> None:
        self.model = model
        self.construction_thread_id = threading.get_ident()

    def shutdown(self) -> None:  # pragma: no cover - unused in this test
        pass


@pytest.fixture
def fake_tensorrt_llm_module(tmp_path: Path) -> Path:
    engine_dir = tmp_path / "engine"
    engine_dir.mkdir()
    (engine_dir / "rank0.engine").write_text("")

    module = ModuleType("tensorrt_llm")
    module.LLM = _ThreadRecordingLLM  # type: ignore[attr-defined]
    previous = sys.modules.get("tensorrt_llm")
    sys.modules["tensorrt_llm"] = module
    try:
        yield engine_dir
    finally:
        if previous is None:
            del sys.modules["tensorrt_llm"]
        else:
            sys.modules["tensorrt_llm"] = previous


def test_default_factory_constructs_the_engine_off_the_event_loop(
    fake_tensorrt_llm_module: Path,
) -> None:
    main_thread_id = threading.get_ident()

    llm: Any = asyncio.run(default_engine_factory(str(fake_tensorrt_llm_module)))

    assert llm.construction_thread_id != main_thread_id


def test_default_factory_routes_construction_through_asyncio_to_thread(
    fake_tensorrt_llm_module: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Callable[..., object]] = []
    real_to_thread = asyncio.to_thread

    async def recording_to_thread(
        func: Callable[..., object], /, *args: object, **kwargs: object
    ) -> object:
        calls.append(func)
        return await real_to_thread(func, *args, **kwargs)

    monkeypatch.setattr("tibios_ray.engines.tensorrt.asyncio.to_thread", recording_to_thread)

    asyncio.run(default_engine_factory(str(fake_tensorrt_llm_module)))

    assert calls == [_ThreadRecordingLLM]
