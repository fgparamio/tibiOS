"""Opt-in integration tests — exercise the real SDK/hardware boundary
that unit tests deliberately stub out (design.md "Testing Strategy":
"the stubbed seam cannot prove the real SDK signature"). Each module
in this package gates itself behind an environment variable and is
skipped by default; nothing here runs in the default `uv run pytest`
invocation unless the operator opts in.
"""
