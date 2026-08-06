"""Marks `tests/unit/capabilities/` as a package so its test module
basenames (e.g. `test_embedding.py`, and future `test_rerank.py` /
`test_speech.py`) do not collide with same-named modules in
`tests/unit/backends/` under pytest's default "prepend" import mode,
which requires globally unique basenames across any directories that
are not themselves packages.
"""
