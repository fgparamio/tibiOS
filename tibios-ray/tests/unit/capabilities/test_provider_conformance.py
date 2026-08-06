"""Shared conformance harness (design decision CP7) — one parametrized
suite that every concrete Capability Provider must satisfy, so each
per-Provider test file (`test_chat.py`, `test_embedding.py`, ...) only
needs to assert catalog data.

`_PROVIDERS` is a typed tuple, appended to by each later slice — it IS
the static conformance check: `CapabilityProvider` is a `typing.Protocol`,
not `runtime_checkable`, so no `isinstance` check against it is possible
(design.md, CP7).

No pytest-asyncio installed — `asyncio.run(...)` inside sync tests,
matching the existing suite (`tests/unit/runtime/test_worker_runtime.py`).
"""

import asyncio
import importlib
import re
from collections.abc import Callable

import pytest

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.chat import ChatProvider
from tibios_ray.capabilities.descriptor import ModelFamily
from tibios_ray.capabilities.errors import NoBackendAvailableError
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.capabilities.provider import CapabilityProvider
from tibios_ray.execution.context import ExecutionContext
from tibios_ray.execution.events import EndOfStream
from tibios_ray.execution.report import ExecutionPhase
from tibios_ray.runtime.registry import CapabilityRegistry
from tibios_ray.runtime.worker_runtime import WorkerRuntime
from tibios_ray.testing import FakeExecutionContext, InMemoryExecutionChannel, ManualCancellation

_PROVIDERS: tuple[CapabilityProvider, ...] = (ChatProvider(),)

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

    @pytest.mark.parametrize(
        "context_factory", [factory for _, factory in _CONTEXT_VARIANTS], ids=[
            name for name, _ in _CONTEXT_VARIANTS
        ]
    )
    def test_execute_always_raises_no_backend_available_error(
        self,
        provider: CapabilityProvider,
        context_factory: Callable[[str], ExecutionContext],
    ) -> None:
        context = context_factory(provider.descriptor.capability.value)

        async def scenario() -> None:
            await provider.execute(context)

        with pytest.raises(NoBackendAvailableError) as exc_info:
            asyncio.run(scenario())

        error = exc_info.value
        assert error.capability == provider.descriptor.capability
        assert error.provider == type(provider).__name__

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
