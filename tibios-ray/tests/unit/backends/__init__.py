"""Marks `tests/unit/backends/` as a package — see
`tests/unit/capabilities/__init__.py` for why this is needed (basename
collisions such as `test_embedding.py` / `test_rerank.py` / `test_speech.py`
between these two directories under pytest's default "prepend" import
mode).
"""
