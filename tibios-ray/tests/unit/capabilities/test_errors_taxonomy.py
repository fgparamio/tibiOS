"""Tests for the `ProviderExecutionError` failure taxonomy
(`capabilities.errors`, design decision D21).

One base, five subclasses; `NoBackendAvailableError` is re-parented
under `ProviderExecutionError` with its signature unchanged, so every
pre-existing `pytest.raises(NoBackendAvailableError)` still holds.
"""

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.errors import (
    BackendExecutionError,
    MissingModelDependencyError,
    NoBackendAvailableError,
    ProviderExecutionError,
    RequestParseError,
    UnresolvableBackendError,
)
from tibios_ray.capabilities.names import CapabilityName


class TestProviderExecutionErrorBase:
    def test_is_a_plain_exception(self) -> None:
        assert issubclass(ProviderExecutionError, Exception)


class TestNoBackendAvailableError:
    def test_is_reparented_under_provider_execution_error(self) -> None:
        assert issubclass(NoBackendAvailableError, ProviderExecutionError)

    def test_signature_is_unchanged(self) -> None:
        error = NoBackendAvailableError(
            capability=CapabilityName("chat.generate"), provider="ChatProvider"
        )

        assert error.capability == CapabilityName("chat.generate")
        assert error.provider == "ChatProvider"
        assert isinstance(error, Exception)


class TestUnresolvableBackendError:
    def test_is_a_provider_execution_error(self) -> None:
        assert issubclass(UnresolvableBackendError, ProviderExecutionError)

    def test_carries_capability_backend_and_available(self) -> None:
        error = UnresolvableBackendError(
            capability=CapabilityName("chat.generate"),
            backend=BackendId("vllm"),
            available=("llama_cpp", "onnxruntime"),
        )

        assert error.capability == CapabilityName("chat.generate")
        assert error.backend == BackendId("vllm")
        assert error.available == ("llama_cpp", "onnxruntime")
        assert str(error) != ""


class TestBackendExecutionError:
    def test_is_a_provider_execution_error(self) -> None:
        assert issubclass(BackendExecutionError, ProviderExecutionError)

    def test_wraps_the_backend_exception_with_cause(self) -> None:
        original = ValueError("backend blew up")

        try:
            try:
                raise original
            except ValueError as caught:
                raise BackendExecutionError(
                    backend=BackendId("llama_cpp"), stage="acquire", error=caught
                ) from caught
        except BackendExecutionError as error:
            assert error.__cause__ is original
            assert error.stage == "acquire"
            assert error.backend == BackendId("llama_cpp")

    def test_stage_distinguishes_acquire_execute_release(self) -> None:
        for stage in ("acquire", "execute", "release"):
            error = BackendExecutionError(
                backend=BackendId("vllm"), stage=stage, error=RuntimeError("boom")
            )
            assert error.stage == stage


class TestMissingModelDependencyError:
    def test_is_a_provider_execution_error(self) -> None:
        assert issubclass(MissingModelDependencyError, ProviderExecutionError)

    def test_message_is_non_empty(self) -> None:
        error = MissingModelDependencyError(capability=CapabilityName("chat.generate"))

        assert str(error) != ""
        assert error.capability == CapabilityName("chat.generate")


class TestRequestParseError:
    def test_is_a_provider_execution_error(self) -> None:
        assert issubclass(RequestParseError, ProviderExecutionError)

    def test_carries_capability_parameter_and_reason(self) -> None:
        error = RequestParseError(
            capability=CapabilityName("chat.generate"),
            parameter="max_tokens",
            reason="not an integer",
        )

        assert error.capability == CapabilityName("chat.generate")
        assert error.parameter == "max_tokens"
        assert error.reason == "not an integer"
        assert "max_tokens" in str(error)
