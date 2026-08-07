"""Tests for `tibios_ray.capabilities.embedding` — the Embedding
Capability Provider (`capability-providers` spec: "Descriptor Catalog
Correctness and Stability", "Chat advertises realistic flags; Embedding/
Rerank advertise none"; `provider-backend-composition` spec: "Per-Request
Dispatch Flow", "Backend Session Release Is Guaranteed", "Non-Streaming
Results Travel Through the Channel").

Catalog data (descriptor, flags) is asserted first — one full descriptor
equality plus flag values. Structural/behavioral conformance shared with
every other Provider (identity stability, element typing, FLC shape) is
covered generically by `test_provider_conformance.py` (design decision
CP7); the two injected fields' shape and immutability (D18) is covered
there too (task 5.1). This module covers what is unique to
`EmbeddingProvider`: successful dispatch, the D24 embedding codec, the
release guarantee, failure outcomes, cancellation, and the dispatch-
mechanical-only conditional shape of `execute()` (tasks 5.2, 5.3, 5.9).

Families here follow design.md's Family Label Convention deviations from
`proposal.md`'s shorthand: `nomic` -> `nomic_embed`, `jina` ->
`jina_embeddings` (rule 3 keeps published role tokens the FLC would
otherwise drop).

No pytest-asyncio installed — `asyncio.run(...)` inside sync tests,
matching the rest of `tests/unit/capabilities/` (`test_chat.py`).
"""

import ast
import asyncio
import inspect
import json
import textwrap
from collections.abc import Sequence

import pytest

from tibios_ray.backends.adapter import BackendId, BackendSession, ServingPlanLike
from tibios_ray.backends.embedding import Vector
from tibios_ray.capabilities.descriptor import CapabilityDescriptor, CapabilityFlags, ModelFamily
from tibios_ray.capabilities.embedding import EMBEDDING_GENERATE_DESCRIPTOR, EmbeddingProvider
from tibios_ray.capabilities.errors import (
    BackendExecutionError,
    NoBackendAvailableError,
    UnresolvableBackendError,
)
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.execution.context import ResolvedModelRef
from tibios_ray.execution.events import EndOfStream, OutputChunk
from tibios_ray.execution.ids import ContentHash, ObjectId, ObjectVersion
from tibios_ray.execution.report import ExecutionPhase
from tibios_ray.selection.policy import Quantization, ServingPlan
from tibios_ray.testing import (
    FakeEmbeddingBackend,
    FakeExecutionContext,
    FakeModelSelectionPolicy,
    InMemoryExecutionChannel,
    ManualCancellation,
)

_ONNXRUNTIME = BackendId("onnxruntime")

# Never actually consulted: only used to satisfy EmbeddingProvider's
# required `selection_policy` field in tests that don't exercise dispatch.
_UNRESOLVED_POLICY = FakeModelSelectionPolicy(
    raises=AssertionError("policy should not be consulted by a catalog-only test")
)


def _model_ref(suffix: str = "1") -> ResolvedModelRef:
    return ResolvedModelRef(
        object_id=ObjectId(f"model-{suffix}"),
        version=ObjectVersion(1),
        content_hash=ContentHash(f"hash-{suffix}"),
    )


def _plan(backend_id: BackendId = _ONNXRUNTIME) -> ServingPlan:
    return ServingPlan(
        model=_model_ref(),
        backend=backend_id,
        quantization=Quantization(scheme="artifact-defined", bits=0),
    )


def _embedding_execution_parameters(**overrides: str) -> dict[str, str]:
    parameters = {"inputs": json.dumps(["hello", "world"])}
    parameters.update(overrides)
    return parameters


class TestEmbeddingProvider:
    def test_descriptor_matches_the_spec_table_exactly(self) -> None:
        provider = EmbeddingProvider(backends={}, selection_policy=_UNRESOLVED_POLICY)

        assert provider.descriptor == CapabilityDescriptor(
            capability=CapabilityName("embedding.generate"),
            families=frozenset(
                {
                    ModelFamily("bge"),
                    ModelFamily("nomic_embed"),
                    ModelFamily("e5"),
                    ModelFamily("jina_embeddings"),
                }
            ),
            backends=frozenset({BackendId("onnxruntime")}),
        )

    def test_descriptor_is_the_module_level_constant(self) -> None:
        provider = EmbeddingProvider(backends={}, selection_policy=_UNRESOLVED_POLICY)

        assert provider.descriptor is EMBEDDING_GENERATE_DESCRIPTOR

    def test_flags_are_all_false(self) -> None:
        flags = EmbeddingProvider(
            backends={}, selection_policy=_UNRESOLVED_POLICY
        ).descriptor.flags

        assert flags == CapabilityFlags()
        assert flags.streaming is False
        assert flags.tools is False
        assert flags.json is False
        assert flags.reasoning is False


class TestEmbeddingProviderDispatch:
    """Task 5.2: successful dispatch acquires with the resolved plan,
    drives `embed()`, releases the session, emits the D24 batch chunk,
    and returns `COMPLETED` — a direct `execute()` call emits no
    `EndOfStream` (D25: that is `WorkerRuntime`'s job alone)."""

    def test_successful_dispatch_emits_output_and_completes(self) -> None:
        backend = FakeEmbeddingBackend(
            _ONNXRUNTIME,
            vectors=(Vector(values=(0.1, 0.2)), Vector(values=(0.3, 0.4))),
        )
        plan = _plan()
        provider = EmbeddingProvider(
            backends={_ONNXRUNTIME: backend},
            selection_policy=FakeModelSelectionPolicy(plan=plan),
        )
        channel = InMemoryExecutionChannel()
        context = FakeExecutionContext(
            execution_parameters=_embedding_execution_parameters(),
            dependencies=(plan.model,),
            channel=channel,
        )

        report = asyncio.run(provider.execute(context))

        assert len(backend.acquired) == 1
        acquired_session = backend.acquired[0]
        assert backend.embed_calls[0][0] is acquired_session
        assert backend.released == [acquired_session]
        assert report.phase == ExecutionPhase.COMPLETED

        chunks = [event for event in channel.emitted if isinstance(event, OutputChunk)]
        assert len(chunks) == 1
        assert not any(isinstance(event, EndOfStream) for event in channel.emitted)

    def test_embed_is_called_with_the_parsed_embedding_request(self) -> None:
        backend = FakeEmbeddingBackend(_ONNXRUNTIME, vectors=(Vector(values=(1.0,)),))
        plan = _plan()
        provider = EmbeddingProvider(
            backends={_ONNXRUNTIME: backend},
            selection_policy=FakeModelSelectionPolicy(plan=plan),
        )
        context = FakeExecutionContext(
            execution_parameters=_embedding_execution_parameters(),
            dependencies=(plan.model,),
        )

        asyncio.run(provider.execute(context))

        _, inputs = backend.embed_calls[0]
        assert tuple(inputs) == ("hello", "world")


class TestEmbeddingCodec:
    """Task 5.3: the D24 embedding codec — exactly one `OutputChunk`,
    `sequence=0`, `json.loads(data)` round-trips `{"vectors": [[...],
    ...]}` in input order; `ExecutionReport` carries none of the
    vectors (`provider-backend-composition` spec: "Embedding output
    appears on the channel, not the report")."""

    def test_one_chunk_sequence_zero_json_round_trips_vectors_in_order(self) -> None:
        vectors = (Vector(values=(0.1, 0.2, 0.3)), Vector(values=(1.0, 2.0, 3.0)))
        backend = FakeEmbeddingBackend(_ONNXRUNTIME, vectors=vectors)
        plan = _plan()
        provider = EmbeddingProvider(
            backends={_ONNXRUNTIME: backend},
            selection_policy=FakeModelSelectionPolicy(plan=plan),
        )
        channel = InMemoryExecutionChannel()
        context = FakeExecutionContext(
            execution_parameters=_embedding_execution_parameters(),
            dependencies=(plan.model,),
            channel=channel,
        )

        report = asyncio.run(provider.execute(context))

        chunks = [event for event in channel.emitted if isinstance(event, OutputChunk)]
        assert len(chunks) == 1
        assert chunks[0].sequence == 0
        decoded = json.loads(chunks[0].data)
        assert decoded == {"vectors": [[0.1, 0.2, 0.3], [1.0, 2.0, 3.0]]}

        # `provider-backend-composition` spec: "ExecutionReport never
        # carries application output" — `ExecutionReport`'s field set is
        # fixed (phase/duration/resource_usage/metrics/trace_id/logs/
        # failure), none of which is a vectors payload; asserted here by
        # inspecting the two Mapping fields that could smuggle it in.
        assert 0.1 not in report.resource_usage.values()
        assert 0.1 not in report.metrics.values()


class _CancelBeforeCompleteBackend:
    """Local fake conforming to `EmbeddingBackend`: cancels the
    caller-supplied token from inside `embed()`, simulating
    `context.cancellation` signaling cancelled before the Backend
    finishes (`provider-backend-composition` spec: "Cooperative
    cancellation is observed mid-execution"). Since a batch capability
    method is a single awaited call with no intermediate chunks, the
    only meaningful checkpoint is whether the Provider still emits the
    batch result once cancellation is observed after that call
    resolves."""

    def __init__(
        self,
        backend_id: BackendId,
        cancellation: ManualCancellation,
        vectors: Sequence[Vector],
    ) -> None:
        self._backend_id = backend_id
        self._cancellation = cancellation
        self._vectors = tuple(vectors)
        self.released: list[BackendSession] = []

    @property
    def backend_id(self) -> BackendId:
        return self._backend_id

    def supports(self, plan: ServingPlanLike) -> bool:
        return plan.backend == self._backend_id

    async def acquire(self, plan: ServingPlanLike) -> BackendSession:
        return BackendSession(backend_id=plan.backend, session_id="sess-cancel-before-complete")

    async def release(self, session: BackendSession) -> None:
        self.released.append(session)

    async def embed(self, session: BackendSession, inputs: Sequence[str]) -> Sequence[Vector]:
        self._cancellation.cancel()
        return self._vectors


class TestEmbeddingProviderCancellation:
    """Task 5.2: cooperative cancellation observed once the Backend's
    `embed()` resolves stops the batch result from being emitted, still
    releases the acquired session, and returns `CANCELLED` without
    raising."""

    def test_cancellation_after_embed_resolves_skips_emission_releases_and_returns_cancelled(
        self,
    ) -> None:
        cancellation = ManualCancellation()
        backend = _CancelBeforeCompleteBackend(
            _ONNXRUNTIME, cancellation, vectors=(Vector(values=(0.1,)),)
        )
        plan = _plan()
        provider = EmbeddingProvider(
            backends={_ONNXRUNTIME: backend},
            selection_policy=FakeModelSelectionPolicy(plan=plan),
        )
        channel = InMemoryExecutionChannel()
        context = FakeExecutionContext(
            execution_parameters=_embedding_execution_parameters(),
            dependencies=(plan.model,),
            channel=channel,
            cancellation=cancellation,
        )

        report = asyncio.run(provider.execute(context))

        chunks = [event for event in channel.emitted if isinstance(event, OutputChunk)]
        assert chunks == []
        assert len(backend.released) == 1
        assert report.phase == ExecutionPhase.CANCELLED


class TestEmbeddingProviderReleaseGuarantee:
    """Task 5.2: `release()` is called exactly once for every successful
    `acquire()`, including when `embed()` raises mid-execution;
    `release()` is never called when `acquire()` itself raises
    (`provider-backend-composition` spec: "Backend Session Release Is
    Guaranteed")."""

    def test_release_is_called_when_embed_raises(self) -> None:
        backend = FakeEmbeddingBackend(_ONNXRUNTIME, embed_raises=RuntimeError("boom"))
        plan = _plan()
        provider = EmbeddingProvider(
            backends={_ONNXRUNTIME: backend},
            selection_policy=FakeModelSelectionPolicy(plan=plan),
        )
        context = FakeExecutionContext(
            execution_parameters=_embedding_execution_parameters(),
            dependencies=(plan.model,),
        )

        async def scenario() -> None:
            await provider.execute(context)

        with pytest.raises(BackendExecutionError) as exc_info:
            asyncio.run(scenario())

        assert exc_info.value.stage == "execute"
        assert exc_info.value.__cause__ is not None
        assert len(backend.acquired) == 1
        assert backend.released == backend.acquired

    def test_release_is_never_called_when_acquire_raises(self) -> None:
        backend = FakeEmbeddingBackend(_ONNXRUNTIME, acquire_raises=RuntimeError("no residency"))
        plan = _plan()
        provider = EmbeddingProvider(
            backends={_ONNXRUNTIME: backend},
            selection_policy=FakeModelSelectionPolicy(plan=plan),
        )
        context = FakeExecutionContext(
            execution_parameters=_embedding_execution_parameters(),
            dependencies=(plan.model,),
        )

        async def scenario() -> None:
            await provider.execute(context)

        with pytest.raises(BackendExecutionError) as exc_info:
            asyncio.run(scenario())

        assert exc_info.value.stage == "acquire"
        assert backend.released == []


class TestEmbeddingProviderFailureOutcomes:
    """Task 5.2: an empty mapping fails as `NoBackendAvailableError`; a
    plan naming a `BackendId` absent from a non-empty mapping fails as
    `UnresolvableBackendError` and never falls back to the mapping's
    existing entry (`capability-providers` spec: "Wired Provider fails
    when mapping is empty / when plan names an absent backend")."""

    def test_empty_mapping_raises_no_backend_available_error(self) -> None:
        provider = EmbeddingProvider(
            backends={}, selection_policy=FakeModelSelectionPolicy(plan=_plan())
        )
        context = FakeExecutionContext(
            execution_parameters=_embedding_execution_parameters(),
            dependencies=(_model_ref(),),
        )

        async def scenario() -> None:
            await provider.execute(context)

        with pytest.raises(NoBackendAvailableError) as exc_info:
            asyncio.run(scenario())

        assert exc_info.value.capability == EMBEDDING_GENERATE_DESCRIPTOR.capability
        assert exc_info.value.provider == "EmbeddingProvider"

    def test_plan_naming_a_backend_absent_from_a_non_empty_mapping_raises_unresolvable(
        self,
    ) -> None:
        present_backend_id = BackendId("onnxruntime")
        plan = _plan(BackendId("other_backend"))
        provider = EmbeddingProvider(
            backends={present_backend_id: FakeEmbeddingBackend(present_backend_id)},
            selection_policy=FakeModelSelectionPolicy(plan=plan),
        )
        context = FakeExecutionContext(
            execution_parameters=_embedding_execution_parameters(),
            dependencies=(plan.model,),
        )

        async def scenario() -> None:
            await provider.execute(context)

        with pytest.raises(UnresolvableBackendError) as exc_info:
            asyncio.run(scenario())

        assert exc_info.value.backend == BackendId("other_backend")
        assert exc_info.value.available == ("onnxruntime",)


class TestEmbeddingProviderDispatchMechanicalConditionals:
    """Task 5.9: the only conditional native to `EmbeddingProvider.execute()`'s
    own body must be cooperative cancellation — never backend-selection
    logic (`provider-backend-composition` spec: "No Selection Logic Inside
    Wired Providers"; `capability-providers` spec: "Dispatch-mechanical
    conditionals in wired Providers are not routing violations").

    `resolve_model_ref`/`resolve_backend` (`dispatch.py`) already own the
    empty-mapping, absent-plan-backend, and dependency-count conditionals.
    Unlike `chat.py`, there is no per-delta codec filter — a batch result
    is either fully emitted or not at all — so cancellation is the one
    conditional genuinely native to this module's own body."""

    _ALLOWED_CONDITIONS = {"context.cancellation.is_cancelled"}

    def test_every_conditional_in_execute_is_the_allowed_cancellation_check(self) -> None:
        source = textwrap.dedent(inspect.getsource(EmbeddingProvider.execute))
        tree = ast.parse(source)
        found_conditions = [
            ast.unparse(node.test) for node in ast.walk(tree) if isinstance(node, ast.If)
        ]

        assert found_conditions, "expected exactly one conditional (cancellation)"
        for condition in found_conditions:
            assert condition in self._ALLOWED_CONDITIONS, (
                f"unexpected conditional {condition!r} in EmbeddingProvider.execute() — "
                "only cooperative cancellation is allowed; no backend/model/family/size/"
                "cost selection logic may live here"
            )

    def test_no_comparison_references_a_backend_family_or_model_literal(self) -> None:
        source = textwrap.dedent(inspect.getsource(EmbeddingProvider.execute))
        tree = ast.parse(source)

        banned_names = {"backend_id", "family", "model_name", "quantization"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                unparsed = ast.unparse(node)
                for banned in banned_names:
                    assert banned not in unparsed, (
                        f"found a comparison referencing {banned!r} in "
                        f"EmbeddingProvider.execute(): {unparsed!r} — this looks like "
                        "backend-selection logic, forbidden by the "
                        "provider-backend-composition spec"
                    )
