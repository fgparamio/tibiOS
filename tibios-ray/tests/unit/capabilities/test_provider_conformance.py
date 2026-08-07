"""Shared conformance harness (design decision CP7) — one parametrized
suite that every concrete Capability Provider must satisfy, so each
per-Provider test file (`test_chat.py`, `test_embedding.py`, ...) only
needs to assert catalog data.

`_PROVIDERS` is a typed tuple, appended to by each later slice — it IS
the static conformance check: `CapabilityProvider` is a `typing.Protocol`,
not `runtime_checkable`, so no `isinstance` check against it is possible
(design.md, CP7).

`_WIRED_PROVIDER_TYPES` (currently just `ChatProvider`; `EmbeddingProvider`
and `RerankProvider` join in Slice 5) is the split point this slice
introduces: a wired Provider declares two injected fields instead of
zero (D18) and no longer raises `NoBackendAvailableError`
unconditionally (`capability-providers` spec: "No-Backend Execution
Failure Is Wiring-Scoped") — every test that assumed a uniform,
zero-field, always-raising Provider across `_PROVIDERS` now branches on
this split, or is carried by a dedicated wired-only test instead
(Test Impact table, row 2).

No pytest-asyncio installed — `asyncio.run(...)` inside sync tests,
matching the existing suite (`tests/unit/runtime/test_worker_runtime.py`).
"""

import asyncio
import dataclasses
import importlib
import re
from collections.abc import Callable

import pytest

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.chat import CHAT_GENERATE_DESCRIPTOR, ChatProvider
from tibios_ray.capabilities.descriptor import ModelFamily
from tibios_ray.capabilities.embedding import EmbeddingProvider
from tibios_ray.capabilities.errors import NoBackendAvailableError
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.capabilities.ocr import OcrProvider
from tibios_ray.capabilities.provider import CapabilityProvider
from tibios_ray.capabilities.rerank import RerankProvider
from tibios_ray.capabilities.speech import SpeechSynthesisProvider, SpeechTranscriptionProvider
from tibios_ray.capabilities.vision import VisionProvider
from tibios_ray.execution.context import ExecutionContext, ResolvedModelRef
from tibios_ray.execution.events import EndOfStream
from tibios_ray.execution.ids import ContentHash, ObjectId, ObjectVersion
from tibios_ray.execution.report import ExecutionPhase
from tibios_ray.runtime.registry import CapabilityRegistry
from tibios_ray.runtime.worker_runtime import WorkerRuntime
from tibios_ray.selection.policy import Quantization, ServingPlan
from tibios_ray.testing import (
    FakeExecutionContext,
    FakeModelSelectionPolicy,
    FakeTextBackend,
    InMemoryExecutionChannel,
    ManualCancellation,
)

_WIRED_PROVIDER_TYPES: tuple[type[CapabilityProvider], ...] = (ChatProvider,)


def _model_ref(suffix: str = "1") -> ResolvedModelRef:
    return ResolvedModelRef(
        object_id=ObjectId(f"model-{suffix}"),
        version=ObjectVersion(1),
        content_hash=ContentHash(f"hash-{suffix}"),
    )


# Never actually consulted: every use of this policy is in a test that
# only cares about catalog data or field shape, not dispatch behavior.
_UNRESOLVED_POLICY = FakeModelSelectionPolicy(
    raises=AssertionError("policy should not be consulted by a catalog-only conformance test")
)

_PROVIDERS: tuple[CapabilityProvider, ...] = (
    ChatProvider(backends={}, selection_policy=_UNRESOLVED_POLICY),
    EmbeddingProvider(),
    RerankProvider(),
    VisionProvider(),
    SpeechTranscriptionProvider(),
    SpeechSynthesisProvider(),
    OcrProvider(),
)

# Family Label Convention (FLC, design.md CP5): lowercase, `_`-separated,
# no dots/hyphens/slashes.
_FLC_SHAPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

# Tokens FLC forbids surviving into a family label: version/size/quant/
# precision/tuning-stage tokens (design.md's banned-token regex; `e5`
# deliberately passes).
_BANNED_TOKEN_PATTERN = re.compile(
    r"^(v?\d+(\.\d+)*|\d+[bmk]|q\d.*|fp\d+|bf\d+|awq|gptq|gguf|instruct|"
    r"chat|base|it|sft|dpo|small|medium|large|mini|xl)$"
)


def _descriptor_constant_name(capability: CapabilityName) -> str:
    """Descriptor constant = capability uppercased, `.` -> `_`, suffixed
    `_DESCRIPTOR` (design.md "Naming rules"): `chat.generate` ->
    `CHAT_GENERATE_DESCRIPTOR`."""
    return capability.value.upper().replace(".", "_") + "_DESCRIPTOR"


def _cancelled_token() -> ManualCancellation:
    token = ManualCancellation()
    token.cancel()
    return token


_CONTEXT_VARIANTS: tuple[tuple[str, Callable[[str], ExecutionContext]], ...] = (
    ("default", lambda capability: FakeExecutionContext(capability=capability)),
    (
        "mismatched_capability",
        lambda capability: FakeExecutionContext(capability="unrelated.capability"),
    ),
    (
        "already_cancelled",
        lambda capability: FakeExecutionContext(
            capability=capability, cancellation=_cancelled_token()
        ),
    ),
)


@pytest.mark.parametrize("provider", _PROVIDERS, ids=lambda p: type(p).__name__)
class TestProviderConformance:
    def test_descriptor_is_identity_stable_and_hashable(
        self, provider: CapabilityProvider
    ) -> None:
        first = provider.descriptor
        second = provider.descriptor

        assert first is second
        assert hash(first) == hash(second)

    def test_descriptor_constant_name_is_derived_and_identical(
        self, provider: CapabilityProvider
    ) -> None:
        module = importlib.import_module(type(provider).__module__)
        expected_name = _descriptor_constant_name(provider.descriptor.capability)

        assert hasattr(module, expected_name), f"{module.__name__} missing {expected_name}"
        assert getattr(module, expected_name) is provider.descriptor

    def test_descriptor_catalog_is_non_empty(self, provider: CapabilityProvider) -> None:
        descriptor = provider.descriptor

        assert descriptor.families
        assert descriptor.backends

    def test_descriptor_elements_are_typed_not_bare_strings(
        self, provider: CapabilityProvider
    ) -> None:
        descriptor = provider.descriptor

        assert all(isinstance(family, ModelFamily) for family in descriptor.families)
        assert all(isinstance(backend, BackendId) for backend in descriptor.backends)

    def test_family_labels_satisfy_the_family_label_convention(
        self, provider: CapabilityProvider
    ) -> None:
        for family in provider.descriptor.families:
            assert _FLC_SHAPE_PATTERN.fullmatch(family.value), family.value
            for token in family.value.split("_"):
                assert not _BANNED_TOKEN_PATTERN.fullmatch(token), (
                    f"family {family.value!r} contains banned token {token!r}"
                )

    def test_backend_ids_have_valid_shape(self, provider: CapabilityProvider) -> None:
        for backend in provider.descriptor.backends:
            assert _FLC_SHAPE_PATTERN.fullmatch(backend.value), backend.value

    def test_provider_declares_no_fields(self, provider: CapabilityProvider) -> None:
        """Unwired Providers hold no backend reference (design.md CP1): a
        zero-field dataclass shape, not just zero *instance* attributes.
        `slots=True` alone doesn't guard this — it only restricts instance
        attributes, not declared dataclass fields. A *wired* Provider
        (`ChatProvider` so far, D18) instead declares exactly its two
        injected fields — `backends` and `selection_policy` — nothing
        else (`provider-backend-composition` spec: "A wired Provider
        holds exactly its two injected fields")."""
        # `CapabilityProvider` is a structural Protocol, not itself a
        # dataclass, so pyright can't statically confirm every conformer
        # satisfies `DataclassInstance` — true by construction (CP1/D18:
        # every Provider IS a `@dataclass`), asserted dynamically here.
        declared_fields = dataclasses.fields(type(provider))  # type: ignore[arg-type]
        field_names = {field.name for field in declared_fields}

        if isinstance(provider, _WIRED_PROVIDER_TYPES):
            assert field_names == {"backends", "selection_policy"}, (
                f"{type(provider).__name__} declares field(s) {sorted(field_names)!r}, "
                "but a wired Provider must declare exactly `backends` and "
                "`selection_policy` (design.md D18) — nothing else"
            )
        else:
            assert declared_fields == (), (
                f"{type(provider).__name__} declares field(s) "
                f"{[f.name for f in declared_fields]!r}, but an unwired Provider must "
                "hold no backend reference (design.md CP1) — remove the field(s) or "
                "route the backend reference through execute()'s ExecutionContext instead"
            )

    def test_end_to_end_through_worker_runtime_yields_failed_report(
        self, provider: CapabilityProvider
    ) -> None:
        channel = InMemoryExecutionChannel()
        registry = CapabilityRegistry([provider])
        runtime = WorkerRuntime(registry)
        context = FakeExecutionContext(
            capability=provider.descriptor.capability.value, channel=channel
        )

        report = asyncio.run(runtime.execute(context))

        assert report.phase == ExecutionPhase.FAILED
        assert report.failure is not None
        assert channel.emitted == [EndOfStream(reason=report.failure)]


_UNWIRED_PROVIDERS: tuple[CapabilityProvider, ...] = tuple(
    provider for provider in _PROVIDERS if not isinstance(provider, _WIRED_PROVIDER_TYPES)
)


@pytest.mark.parametrize("provider", _UNWIRED_PROVIDERS, ids=lambda p: type(p).__name__)
@pytest.mark.parametrize(
    "context_factory",
    [factory for _, factory in _CONTEXT_VARIANTS],
    ids=[name for name, _ in _CONTEXT_VARIANTS],
)
def test_unwired_provider_execute_always_raises_no_backend_available_error(
    provider: CapabilityProvider,
    context_factory: Callable[[str], ExecutionContext],
) -> None:
    """Unwired Providers (Vision, Speech-transcribe, Speech-synthesize,
    OCR) still raise `NoBackendAvailableError` unconditionally, regardless
    of context shape — unchanged from before this slice. Split out of
    `TestProviderConformance` (Test Impact table, row 2) because a wired
    Provider's `execute()` no longer raises unconditionally, so one
    shared parametrization can no longer cover both groups."""
    context = context_factory(provider.descriptor.capability.value)

    async def scenario() -> None:
        await provider.execute(context)

    with pytest.raises(NoBackendAvailableError) as exc_info:
        asyncio.run(scenario())

    error = exc_info.value
    assert error.capability == provider.descriptor.capability
    assert error.provider == type(provider).__name__


class TestChatProviderDispatchSplit:
    """`ChatProvider`'s half of the
    `test_execute_always_raises_no_backend_available_error` split (Test
    Impact table, row 2; task 4.9): unlike an unwired Provider, a wired
    Provider raises `NoBackendAvailableError` only when its injected
    mapping is empty — a non-empty mapping with a resolving policy
    dispatches instead (`capability-providers` spec: "Wired Provider
    dispatches instead of raising when its mapping and policy resolve a
    backend"). Full dispatch behavior (release guarantee, cancellation,
    the chat codec) is `test_chat.py`'s job — this only proves the raise
    is no longer unconditional."""

    @staticmethod
    def _chat_context() -> ExecutionContext:
        return FakeExecutionContext(
            capability=CHAT_GENERATE_DESCRIPTOR.capability.value,
            execution_parameters={"prompt": "hello", "max_tokens": "8"},
            dependencies=(_model_ref(),),
        )

    def test_empty_mapping_still_raises_no_backend_available_error(self) -> None:
        provider = ChatProvider(backends={}, selection_policy=_UNRESOLVED_POLICY)
        context = self._chat_context()

        async def scenario() -> None:
            await provider.execute(context)

        with pytest.raises(NoBackendAvailableError) as exc_info:
            asyncio.run(scenario())

        error = exc_info.value
        assert error.capability == provider.descriptor.capability
        assert error.provider == "ChatProvider"

    def test_non_empty_resolving_mapping_dispatches_instead_of_raising(self) -> None:
        backend_id = BackendId("llama_cpp")
        backend = FakeTextBackend(backend_id)
        plan = ServingPlan(
            model=_model_ref(),
            backend=backend_id,
            quantization=Quantization(scheme="artifact-defined", bits=0),
        )
        provider = ChatProvider(
            backends={backend_id: backend},
            selection_policy=FakeModelSelectionPolicy(plan=plan),
        )
        context = self._chat_context()

        report = asyncio.run(provider.execute(context))

        assert report.phase == ExecutionPhase.COMPLETED


class TestChatProviderInjectedFieldImmutability:
    """`ChatProvider`'s two injected fields are immutable after
    construction (design.md D18; `provider-backend-composition` spec:
    "The injected mapping is immutable after construction") — task 4.2."""

    def test_reassigning_the_backends_field_raises(self) -> None:
        provider = ChatProvider(backends={}, selection_policy=_UNRESOLVED_POLICY)

        with pytest.raises(dataclasses.FrozenInstanceError):
            provider.backends = {}  # type: ignore[misc]

    def test_mutating_the_backends_mapping_in_place_raises(self) -> None:
        backend_id = BackendId("llama_cpp")
        provider = ChatProvider(
            backends={backend_id: FakeTextBackend(backend_id)},
            selection_policy=_UNRESOLVED_POLICY,
        )

        with pytest.raises(TypeError):
            provider.backends[BackendId("vllm")] = FakeTextBackend(  # type: ignore[index]
                BackendId("vllm")
            )

    def test_mutating_the_source_mapping_after_construction_does_not_leak_in(self) -> None:
        backend_id = BackendId("llama_cpp")
        source = {backend_id: FakeTextBackend(backend_id)}
        provider = ChatProvider(backends=source, selection_policy=_UNRESOLVED_POLICY)

        source[BackendId("vllm")] = FakeTextBackend(BackendId("vllm"))

        assert set(provider.backends) == {backend_id}
