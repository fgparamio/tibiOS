"""Shared test fakes (`design.md` Module Layout: "shipped in-package so
Phases 2-4 reuse them") — a fake Execution Context plus an in-memory
channel, no real infrastructure required (`18-worker-model.md` testability
principle). Consolidates the ad-hoc test doubles Phase 1-5 each hand-rolled
independently since this package did not exist yet.

Not part of the production Worker Contract surface (`worker.py`,
`WorkerRuntime`); imported only from `tests/`. Contains no "Worker"-named
identifier — `tests/unit/runtime/test_naming_audit.py` audits this package
too.
"""

from tibios_ray.testing.backend import RecordingBackend
from tibios_ray.testing.cancellation import ManualCancellation
from tibios_ray.testing.channel import InMemoryExecutionChannel
from tibios_ray.testing.context import FakeExecutionContext
from tibios_ray.testing.embedding_backend import FakeEmbeddingBackend
from tibios_ray.testing.policy import FakeModelSelectionPolicy
from tibios_ray.testing.provider import StubProvider
from tibios_ray.testing.rerank_backend import FakeRerankBackend
from tibios_ray.testing.text_backend import FakeTextBackend

__all__ = [
    "FakeEmbeddingBackend",
    "FakeExecutionContext",
    "FakeModelSelectionPolicy",
    "FakeRerankBackend",
    "FakeTextBackend",
    "InMemoryExecutionChannel",
    "ManualCancellation",
    "RecordingBackend",
    "StubProvider",
]
