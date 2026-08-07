"""`onnxruntime-backend` spec, Requirement "Residency Lifecycle Governs
Model Access Through Acquire and Release" (design decision OR2) —
residency is shared and refcounted, reusing VL2/VL6/VL13 verbatim:
`InferenceSession` owns no per-request mutable state, so multiple
`acquire()`s for the same model share one constructed session and
tokenizer, each getting a distinct `session_id`.
"""

import asyncio

from stub_onnx import make_stub_session_factory, make_stub_tokenizer_factory

from tibios_ray.backends.adapter import BackendId
from tibios_ray.engines.onnxrt import ONNXRUNTIME_BACKEND_ID, OnnxEmbeddingBackend


class _Plan:
    def __init__(self, backend: BackendId) -> None:
        self.backend = backend


_PLAN = _Plan(ONNXRUNTIME_BACKEND_ID)


def _backend_with_stubs():
    session_factory, sessions = make_stub_session_factory()
    tokenizer_factory, tokenizers = make_stub_tokenizer_factory()
    backend = OnnxEmbeddingBackend(
        model_path="model.onnx",
        tokenizer_path="tok",
        session_factory=session_factory,
        tokenizer_factory=tokenizer_factory,
    )
    return backend, sessions, tokenizers


def test_three_acquires_share_one_session_but_get_distinct_session_ids() -> None:
    backend, sessions, tokenizers = _backend_with_stubs()

    async def scenario() -> tuple[str, str, str]:
        first = await backend.acquire(_PLAN)
        second = await backend.acquire(_PLAN)
        third = await backend.acquire(_PLAN)
        return first.session_id, second.session_id, third.session_id

    first_id, second_id, third_id = asyncio.run(scenario())

    assert len({first_id, second_id, third_id}) == 3  # three distinct session_ids
    assert len(sessions) == 1  # session factory invoked exactly once
    assert len(tokenizers) == 1  # tokenizer factory invoked exactly once


def test_acquire_returns_a_session_bound_to_the_onnxruntime_backend_id() -> None:
    backend, _, _ = _backend_with_stubs()

    async def scenario() -> BackendId:
        session = await backend.acquire(_PLAN)
        return session.backend_id

    assert asyncio.run(scenario()) == ONNXRUNTIME_BACKEND_ID


def test_two_distinct_backend_instances_get_two_distinct_sessions() -> None:
    # OR2's accepted limitation: residency is per-Backend-instance, not
    # per-process — two instances load the model twice.
    backend_a, made_a, _ = _backend_with_stubs()
    backend_b, made_b, _ = _backend_with_stubs()

    async def scenario() -> None:
        await backend_a.acquire(_PLAN)
        await backend_b.acquire(_PLAN)

    asyncio.run(scenario())

    assert len(made_a) == 1
    assert len(made_b) == 1
    assert made_a[0] is not made_b[0]


def test_acquire_queries_the_graphs_declared_input_names_exactly_once() -> None:
    # OR8: the graph's own `get_inputs()` is the authority, queried and
    # cached at `acquire()` time (once, at construction) so `_infer()`'s
    # hot path (PR 2) is a plain set intersection, never a repeat query.
    session_factory, sessions = make_stub_session_factory(
        input_names=("input_ids", "attention_mask")
    )
    tokenizer_factory, _ = make_stub_tokenizer_factory()
    backend = OnnxEmbeddingBackend(
        model_path="model.onnx",
        tokenizer_path="tok",
        session_factory=session_factory,
        tokenizer_factory=tokenizer_factory,
    )

    async def scenario() -> None:
        await backend.acquire(_PLAN)
        await backend.acquire(_PLAN)  # reuse: must not re-query get_inputs()

    asyncio.run(scenario())

    assert sessions[0].get_inputs_calls == 1
