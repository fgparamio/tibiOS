"""Tests for `tibios_ray.capabilities.chat` — the Chat Capability Provider
(`capability-providers` spec: "Descriptor Catalog Correctness and
Stability", "Chat advertises realistic flags"; `provider-backend-
composition` spec: "Per-Request Dispatch Flow", "Backend Session Release
Is Guaranteed").

Catalog data (descriptor, flags) is asserted first — one full descriptor
equality plus flag values. Structural/behavioral conformance shared with
every other Provider (identity stability, element typing, FLC shape) is
covered generically by `test_provider_conformance.py` (design decision
CP7); the two injected fields' shape and immutability (D18) is covered
there too (tasks 4.1/4.2). This module covers what is unique to
`ChatProvider`: successful dispatch, the D24 chat codec, cooperative
cancellation, the release guarantee, and the dispatch-mechanical-only
conditional shape of `execute()` (tasks 4.3-4.7, 4.10).

No pytest-asyncio installed — `asyncio.run(...)` inside sync tests,
matching the rest of `tests/unit/capabilities/`.
"""

import ast
import asyncio
import inspect
import textwrap
from collections.abc import AsyncIterator

import pytest

from tibios_ray.backends.adapter import BackendId, BackendSession, ServingPlanLike
from tibios_ray.backends.text import TextChunk, TextRequest
from tibios_ray.capabilities.chat import CHAT_GENERATE_DESCRIPTOR, ChatProvider
from tibios_ray.capabilities.descriptor import CapabilityDescriptor, CapabilityFlags, ModelFamily
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
    FakeExecutionContext,
    FakeModelSelectionPolicy,
    FakeTextBackend,
    InMemoryExecutionChannel,
    ManualCancellation,
)

_LLAMA_CPP = BackendId("llama_cpp")

# Never actually consulted: only used to satisfy ChatProvider's required
# `selection_policy` field in tests that don't exercise dispatch.
_UNRESOLVED_POLICY = FakeModelSelectionPolicy(
    raises=AssertionError("policy should not be consulted by a catalog-only test")
)


def _model_ref(suffix: str = "1") -> ResolvedModelRef:
    return ResolvedModelRef(
        object_id=ObjectId(f"model-{suffix}"),
        version=ObjectVersion(1),
        content_hash=ContentHash(f"hash-{suffix}"),
    )


def _plan(backend_id: BackendId = _LLAMA_CPP) -> ServingPlan:
    return ServingPlan(
        model=_model_ref(),
        backend=backend_id,
        quantization=Quantization(scheme="artifact-defined", bits=0),
    )


def _chat_execution_parameters(**overrides: str) -> dict[str, str]:
    parameters = {"prompt": "Hello there", "max_tokens": "16"}
    parameters.update(overrides)
    return parameters


class TestChatProvider:
    def test_descriptor_matches_the_spec_table_exactly(self) -> None:
        provider = ChatProvider(backends={}, selection_policy=_UNRESOLVED_POLICY)

        assert provider.descriptor == CapabilityDescriptor(
            capability=CapabilityName("chat.generate"),
            families=frozenset(
                {
                    ModelFamily("qwen"),
                    ModelFamily("llama"),
                    ModelFamily("deepseek"),
                    ModelFamily("gemma"),
                    ModelFamily("mistral"),
                    ModelFamily("kimi"),
                }
            ),
            backends=frozenset(
                {
                    BackendId("llama_cpp"),
                    BackendId("tensorrt_llm"),
                    BackendId("vllm"),
                }
            ),
            flags=CapabilityFlags(streaming=True, tools=True, json=True, reasoning=True),
        )

    def test_descriptor_is_the_module_level_constant(self) -> None:
        provider = ChatProvider(backends={}, selection_policy=_UNRESOLVED_POLICY)

        assert provider.descriptor is CHAT_GENERATE_DESCRIPTOR

    def test_flags_are_all_true(self) -> None:
        flags = ChatProvider(backends={}, selection_policy=_UNRESOLVED_POLICY).descriptor.flags

        assert flags.streaming is True
        assert flags.tools is True
        assert flags.json is True
        assert flags.reasoning is True


class TestChatProviderDispatch:
    """Task 4.3: successful dispatch acquires with the resolved plan,
    drives `generate()`, releases the session, streams one or more
    `OutputChunk`s, and returns `COMPLETED` — a direct `execute()` call
    emits no `EndOfStream` (D25: that is `WorkerRuntime`'s job alone)."""

    def test_successful_dispatch_streams_output_and_completes(self) -> None:
        backend = FakeTextBackend(
            _LLAMA_CPP,
            chunks=(
                TextChunk(text="Hel"),
                TextChunk(text="lo"),
                TextChunk(text="", finished=True),
            ),
        )
        plan = _plan()
        provider = ChatProvider(
            backends={_LLAMA_CPP: backend},
            selection_policy=FakeModelSelectionPolicy(plan=plan),
        )
        channel = InMemoryExecutionChannel()
        context = FakeExecutionContext(
            execution_parameters=_chat_execution_parameters(),
            dependencies=(plan.model,),
            channel=channel,
        )

        report = asyncio.run(provider.execute(context))

        assert len(backend.acquired) == 1
        acquired_session = backend.acquired[0]
        assert backend.generate_calls[0][0] is acquired_session
        assert backend.released == [acquired_session]
        assert report.phase == ExecutionPhase.COMPLETED

        chunks = [event for event in channel.emitted if isinstance(event, OutputChunk)]
        assert len(chunks) >= 1
        assert not any(isinstance(event, EndOfStream) for event in channel.emitted)

    def test_generate_is_called_with_the_parsed_chat_request(self) -> None:
        backend = FakeTextBackend(_LLAMA_CPP, chunks=(TextChunk(text="", finished=True),))
        plan = _plan()
        provider = ChatProvider(
            backends={_LLAMA_CPP: backend},
            selection_policy=FakeModelSelectionPolicy(plan=plan),
        )
        context = FakeExecutionContext(
            execution_parameters=_chat_execution_parameters(temperature="0.5", stop='["\\n"]'),
            dependencies=(plan.model,),
        )

        asyncio.run(provider.execute(context))

        _, request = backend.generate_calls[0]
        assert request.prompt == "Hello there"
        assert request.max_tokens == 16
        assert request.temperature == 0.5
        assert request.stop == ("\n",)


class TestChatCodec:
    """Task 4.4: the D24 chat codec — N non-empty `TextChunk` deltas
    produce N `OutputChunk`s, `sequence` 0..N-1, `data == text.encode()`;
    the terminal empty/`finished=True` delta emits nothing."""

    def test_n_non_empty_deltas_emit_n_output_chunks_in_order(self) -> None:
        backend = FakeTextBackend(
            _LLAMA_CPP,
            chunks=(
                TextChunk(text="a"),
                TextChunk(text="b"),
                TextChunk(text="c"),
                TextChunk(text="", finished=True),
            ),
        )
        plan = _plan()
        provider = ChatProvider(
            backends={_LLAMA_CPP: backend},
            selection_policy=FakeModelSelectionPolicy(plan=plan),
        )
        channel = InMemoryExecutionChannel()
        context = FakeExecutionContext(
            execution_parameters=_chat_execution_parameters(),
            dependencies=(plan.model,),
            channel=channel,
        )

        asyncio.run(provider.execute(context))

        chunks = [event for event in channel.emitted if isinstance(event, OutputChunk)]
        assert [chunk.sequence for chunk in chunks] == [0, 1, 2]
        assert [chunk.data for chunk in chunks] == [b"a", b"b", b"c"]

    def test_terminal_empty_finished_delta_emits_no_chunk(self) -> None:
        backend = FakeTextBackend(
            _LLAMA_CPP, chunks=(TextChunk(text="only"), TextChunk(text="", finished=True))
        )
        plan = _plan()
        provider = ChatProvider(
            backends={_LLAMA_CPP: backend},
            selection_policy=FakeModelSelectionPolicy(plan=plan),
        )
        channel = InMemoryExecutionChannel()
        context = FakeExecutionContext(
            execution_parameters=_chat_execution_parameters(),
            dependencies=(plan.model,),
            channel=channel,
        )

        asyncio.run(provider.execute(context))

        chunks = [event for event in channel.emitted if isinstance(event, OutputChunk)]
        assert len(chunks) == 1
        assert chunks[0].data == b"only"


class _CancelMidStreamBackend:
    """Local fake conforming to `TextGenerationBackend`: yields one real
    chunk, cancels the caller-supplied token, then yields a second chunk
    a correctly cooperating Provider must never emit (`provider-backend-
    composition` spec: "Cooperative cancellation is observed mid-
    execution")."""

    def __init__(self, backend_id: BackendId, cancellation: ManualCancellation) -> None:
        self._backend_id = backend_id
        self._cancellation = cancellation
        self.released: list[BackendSession] = []

    @property
    def backend_id(self) -> BackendId:
        return self._backend_id

    def supports(self, plan: ServingPlanLike) -> bool:
        return plan.backend == self._backend_id

    async def acquire(self, plan: ServingPlanLike) -> BackendSession:
        return BackendSession(backend_id=plan.backend, session_id="sess-cancel-mid-stream")

    async def release(self, session: BackendSession) -> None:
        self.released.append(session)

    async def generate(
        self, session: BackendSession, request: TextRequest
    ) -> AsyncIterator[TextChunk]:
        yield TextChunk(text="before-cancel")
        self._cancellation.cancel()
        yield TextChunk(text="after-cancel-should-not-appear")
        yield TextChunk(text="", finished=True)


class TestChatProviderCancellation:
    """Task 4.5: cooperative cancellation observed mid-stream stops
    driving further output, still releases the acquired session, and
    returns `CANCELLED` without raising."""

    def test_cancellation_mid_stream_stops_output_releases_and_returns_cancelled(self) -> None:
        cancellation = ManualCancellation()
        backend = _CancelMidStreamBackend(_LLAMA_CPP, cancellation)
        plan = _plan()
        provider = ChatProvider(
            backends={_LLAMA_CPP: backend},
            selection_policy=FakeModelSelectionPolicy(plan=plan),
        )
        channel = InMemoryExecutionChannel()
        context = FakeExecutionContext(
            execution_parameters=_chat_execution_parameters(),
            dependencies=(plan.model,),
            channel=channel,
            cancellation=cancellation,
        )

        report = asyncio.run(provider.execute(context))

        chunks = [event for event in channel.emitted if isinstance(event, OutputChunk)]
        assert [chunk.data for chunk in chunks] == [b"before-cancel"]
        assert len(backend.released) == 1
        assert report.phase == ExecutionPhase.CANCELLED


class TestChatProviderReleaseGuarantee:
    """Task 4.6: `release()` is called exactly once for every successful
    `acquire()`, including when the Backend's capability method raises
    mid-execution; `release()` is never called when `acquire()` itself
    raises (`provider-backend-composition` spec: "Backend Session Release
    Is Guaranteed")."""

    def test_release_is_called_when_generate_raises_mid_stream(self) -> None:
        backend = FakeTextBackend(
            _LLAMA_CPP,
            chunks=(TextChunk(text="partial"),),
            generate_raises=RuntimeError("boom"),
        )
        plan = _plan()
        provider = ChatProvider(
            backends={_LLAMA_CPP: backend},
            selection_policy=FakeModelSelectionPolicy(plan=plan),
        )
        context = FakeExecutionContext(
            execution_parameters=_chat_execution_parameters(),
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
        backend = FakeTextBackend(_LLAMA_CPP, acquire_raises=RuntimeError("no residency"))
        plan = _plan()
        provider = ChatProvider(
            backends={_LLAMA_CPP: backend},
            selection_policy=FakeModelSelectionPolicy(plan=plan),
        )
        context = FakeExecutionContext(
            execution_parameters=_chat_execution_parameters(),
            dependencies=(plan.model,),
        )

        async def scenario() -> None:
            await provider.execute(context)

        with pytest.raises(BackendExecutionError) as exc_info:
            asyncio.run(scenario())

        assert exc_info.value.stage == "acquire"
        assert backend.released == []


class TestChatProviderFailureOutcomes:
    """Task 4.7: an empty mapping fails as `NoBackendAvailableError`; a
    plan naming a `BackendId` absent from a non-empty mapping fails as
    `UnresolvableBackendError` and never falls back to the mapping's
    existing entry (`capability-providers` spec: "Wired Provider fails
    when mapping is empty / when plan names an absent backend")."""

    def test_empty_mapping_raises_no_backend_available_error(self) -> None:
        provider = ChatProvider(
            backends={}, selection_policy=FakeModelSelectionPolicy(plan=_plan())
        )
        context = FakeExecutionContext(
            execution_parameters=_chat_execution_parameters(),
            dependencies=(_model_ref(),),
        )

        async def scenario() -> None:
            await provider.execute(context)

        with pytest.raises(NoBackendAvailableError) as exc_info:
            asyncio.run(scenario())

        assert exc_info.value.capability == CHAT_GENERATE_DESCRIPTOR.capability
        assert exc_info.value.provider == "ChatProvider"

    def test_plan_naming_a_backend_absent_from_a_non_empty_mapping_raises_unresolvable(
        self,
    ) -> None:
        present_backend_id = BackendId("llama_cpp")
        plan = _plan(BackendId("vllm"))  # the policy resolves to a backend not in the mapping
        provider = ChatProvider(
            backends={present_backend_id: FakeTextBackend(present_backend_id)},
            selection_policy=FakeModelSelectionPolicy(plan=plan),
        )
        context = FakeExecutionContext(
            execution_parameters=_chat_execution_parameters(),
            dependencies=(plan.model,),
        )

        async def scenario() -> None:
            await provider.execute(context)

        with pytest.raises(UnresolvableBackendError) as exc_info:
            asyncio.run(scenario())

        assert exc_info.value.backend == BackendId("vllm")
        assert exc_info.value.available == ("llama_cpp",)


class TestChatProviderDispatchMechanicalConditionals:
    """Task 4.10: every conditional native to `ChatProvider.execute()`'s
    own body must be dispatch-mechanical or the D24 chat codec — never
    backend-selection logic (`provider-backend-composition` spec: "No
    Selection Logic Inside Wired Providers" — "SHALL NOT implement
    backend selection logic — no branching, scoring, or capability-
    matching"; `capability-providers` spec: "Dispatch-mechanical
    conditionals in wired Providers are not routing violations").

    `resolve_model_ref`/`resolve_backend` (`dispatch.py`) already own the
    empty-mapping, absent-plan-backend, and dependency-count conditionals
    — D18's own rationale is that helpers exist precisely so "the three
    execute() bodies keep only the conditionals the spec allows". The two
    conditionals genuinely native to `chat.py`'s own body are cooperative
    cancellation and D24's terminal/empty-chunk filter (a streaming
    codec's own bookkeeping, not a choice among backends) — neither
    chooses a backend, so neither is "backend selection logic" under the
    requirement's own qualifying phrase."""

    _ALLOWED_CONDITIONS = {
        "context.cancellation.is_cancelled",
        "chunk.text",
    }

    def test_every_conditional_in_execute_is_an_allowed_dispatch_or_codec_check(self) -> None:
        source = textwrap.dedent(inspect.getsource(ChatProvider.execute))
        tree = ast.parse(source)
        found_conditions = [
            ast.unparse(node.test) for node in ast.walk(tree) if isinstance(node, ast.If)
        ]

        assert found_conditions, "expected at least one conditional (cancellation, chat codec)"
        for condition in found_conditions:
            assert condition in self._ALLOWED_CONDITIONS, (
                f"unexpected conditional {condition!r} in ChatProvider.execute() — only "
                "cooperative cancellation and the D24 chat-codec empty/terminal-chunk "
                "filter are allowed; no backend/model/family/size/cost selection logic "
                "may live here"
            )

    def test_no_comparison_references_a_backend_family_or_model_literal(self) -> None:
        source = textwrap.dedent(inspect.getsource(ChatProvider.execute))
        tree = ast.parse(source)

        banned_names = {"backend_id", "family", "model_name", "quantization"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                unparsed = ast.unparse(node)
                for banned in banned_names:
                    assert banned not in unparsed, (
                        f"found a comparison referencing {banned!r} in "
                        f"ChatProvider.execute(): {unparsed!r} — this looks like "
                        "backend-selection logic, forbidden by the "
                        "provider-backend-composition spec"
                    )
