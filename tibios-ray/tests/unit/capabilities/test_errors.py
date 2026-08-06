"""Tests for `tibios_ray.capabilities.errors` — `NoBackendAvailableError`
(design decision CP2: a plain `Exception` subclass, deliberately NOT a
`runtime.errors.DispatchError` subclass, since `runtime/errors.py`
already imports from `capabilities/names.py` and `capabilities/
provider.py` — subclassing `DispatchError` here would close a literal
import cycle. `WorkerRuntime._dispatch` catches bare `Exception` around
`provider.execute()`, so behavior is identical either way.)
"""

from tibios_ray.capabilities.errors import NoBackendAvailableError
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.runtime.errors import DispatchError


class TestNoBackendAvailableError:
    def test_carries_capability_and_provider(self) -> None:
        capability = CapabilityName("chat.generate")
        error = NoBackendAvailableError(capability=capability, provider="ChatProvider")

        assert error.capability == capability
        assert error.provider == "ChatProvider"

    def test_message_is_non_empty(self) -> None:
        error = NoBackendAvailableError(
            capability=CapabilityName("chat.generate"), provider="ChatProvider"
        )

        assert str(error) != ""

    def test_is_a_plain_exception(self) -> None:
        error = NoBackendAvailableError(
            capability=CapabilityName("chat.generate"), provider="ChatProvider"
        )

        assert isinstance(error, Exception)

    def test_is_not_a_dispatch_error(self) -> None:
        """CP2: subclassing `DispatchError` would close a literal import
        cycle (`runtime/errors.py` -> `capabilities/names.py` +
        `capabilities/provider.py`). Pinned here so future "tidying"
        cannot silently reintroduce the cycle."""
        error = NoBackendAvailableError(
            capability=CapabilityName("chat.generate"), provider="ChatProvider"
        )

        assert not isinstance(error, DispatchError)
