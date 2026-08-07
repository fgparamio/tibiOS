"""Marks `tests/unit/transport/` as a package — see
`tests/unit/backends/__init__.py` for why this is needed (basename
collisions such as `test_channel.py` against `tests/unit/execution/` and
`test_registry.py` against `tests/unit/runtime/` under pytest's default
"prepend" import mode).
"""
