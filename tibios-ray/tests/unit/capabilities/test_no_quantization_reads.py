"""D23 guard: no Backend acts on `ServingPlan.quantization` — the policy
returns the sentinel `ARTIFACT_DEFINED` and nothing under `engines/`
reads `.quantization` at all, since `backends/adapter.py`'s
`ServingPlanLike` exposes only `.backend` (`design.md` D23).
"""

from pathlib import Path

import tibios_ray


def test_no_engines_module_reads_quantization() -> None:
    engines_root = Path(tibios_ray.__file__).resolve().parent / "engines"
    offenders = [
        path
        for path in engines_root.rglob("*.py")
        if ".quantization" in path.read_text()
    ]

    assert offenders == []
