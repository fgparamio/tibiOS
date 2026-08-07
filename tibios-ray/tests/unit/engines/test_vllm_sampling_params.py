"""`vllm-text-backend` spec references design decision VL9 —
`default_sampling_params_factory` MUST set `output_kind=RequestOutputKind.
DELTA` (never the SDK's default `CUMULATIVE`, which would make the
Provider concatenate the whole completion O(n) times) and `n=1` (the
only field `TextRequest` maps, and the only index `generate()` reads).

Faking `sys.modules["vllm.sampling_params"]` lets this test call the
*real* default factory with zero SDK installed — `importlib.import_
module` consults `sys.modules` first (LC11's seam, VL8), so this is
testing production code, not a substitute for it.
"""

import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from types import ModuleType
from typing import Any

import pytest

from tibios_ray.backends.text import TextRequest
from tibios_ray.engines.vllm import default_sampling_params_factory


class _FakeRequestOutputKind(Enum):
    CUMULATIVE = auto()
    DELTA = auto()


@dataclass
class _FakeSamplingParams:
    max_tokens: int
    temperature: float
    stop: list[str] = field(default_factory=list)
    n: int = 1
    output_kind: _FakeRequestOutputKind = _FakeRequestOutputKind.CUMULATIVE


@pytest.fixture
def fake_vllm_sampling_params_module():
    module = ModuleType("vllm.sampling_params")
    module.SamplingParams = _FakeSamplingParams  # type: ignore[attr-defined]
    module.RequestOutputKind = _FakeRequestOutputKind  # type: ignore[attr-defined]
    previous = sys.modules.get("vllm.sampling_params")
    sys.modules["vllm.sampling_params"] = module
    try:
        yield module
    finally:
        if previous is None:
            del sys.modules["vllm.sampling_params"]
        else:
            sys.modules["vllm.sampling_params"] = previous


def test_default_factory_sets_delta_output_kind_and_n_equals_one(
    fake_vllm_sampling_params_module: ModuleType,
) -> None:
    request = TextRequest(prompt="hi", max_tokens=16, temperature=0.7, stop=("</s>",))

    params: Any = default_sampling_params_factory(request)

    assert params.output_kind is _FakeRequestOutputKind.DELTA
    assert params.n == 1


def test_default_factory_maps_max_tokens_temperature_and_stop(
    fake_vllm_sampling_params_module: ModuleType,
) -> None:
    request = TextRequest(prompt="hi", max_tokens=42, temperature=0.3, stop=("</s>", "\n\n"))

    params: Any = default_sampling_params_factory(request)

    assert params.max_tokens == 42
    assert params.temperature == 0.3
    assert params.stop == ["</s>", "\n\n"]


def test_source_carries_the_vl9_comment() -> None:
    # tasks.md 2.3: this comment is mandatory, not optional — the
    # ceiling it documents (silent O(n^2) duplication if vLLM's default
    # CUMULATIVE ever gets copy-pasted back in) is invisible from the
    # diff alone, so it must survive in the committed source itself.
    import inspect

    source = inspect.getsource(default_sampling_params_factory)
    assert "# DELTA, not CUMULATIVE — see VL9" in source
