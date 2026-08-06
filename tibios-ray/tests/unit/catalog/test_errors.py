"""Tests for `tibios_ray.catalog.errors` — the six `CatalogError`
subclasses each carry typed payload, never a bare message (design
decisions MC6, MC7, MC9).
"""

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import ModelFamily
from tibios_ray.catalog.errors import (
    AmbiguousFootprintError,
    CatalogError,
    DuplicateModelError,
    FamilyDerivationError,
    FamilyMismatchError,
    UnknownModelError,
    UnsupportedServingError,
)
from tibios_ray.catalog.names import PublishedModelName
from tibios_ray.selection.policy import Quantization

_NAME = PublishedModelName("Qwen/Qwen3-8B")


class TestCatalogErrorIsTheSharedBase:
    def test_every_subclass_is_a_catalog_error(self) -> None:
        assert issubclass(FamilyDerivationError, CatalogError)
        assert issubclass(UnknownModelError, CatalogError)
        assert issubclass(UnsupportedServingError, CatalogError)
        assert issubclass(DuplicateModelError, CatalogError)
        assert issubclass(FamilyMismatchError, CatalogError)
        assert issubclass(AmbiguousFootprintError, CatalogError)

    def test_catalog_error_is_a_plain_exception(self) -> None:
        assert issubclass(CatalogError, Exception)


class TestFamilyDerivationError:
    def test_carries_name_and_reason(self) -> None:
        error = FamilyDerivationError(_NAME, reason="no lineage token survived")

        assert error.name == _NAME
        assert error.reason == "no lineage token survived"
        assert str(error) != ""


class TestUnknownModelError:
    def test_carries_name(self) -> None:
        error = UnknownModelError(_NAME)

        assert error.name == _NAME
        assert str(error) != ""


class TestUnsupportedServingError:
    def test_carries_name_backend_and_quantization(self) -> None:
        backend = BackendId("vllm")
        quantization = Quantization(scheme="fp16", bits=16)

        error = UnsupportedServingError(_NAME, backend=backend, quantization=quantization)

        assert error.name == _NAME
        assert error.backend == backend
        assert error.quantization == quantization
        assert str(error) != ""


class TestDuplicateModelError:
    def test_carries_name(self) -> None:
        error = DuplicateModelError(_NAME)

        assert error.name == _NAME
        assert str(error) != ""


class TestFamilyMismatchError:
    def test_carries_name_stated_and_derived_family(self) -> None:
        stated = ModelFamily("llama")
        derived = ModelFamily("qwen")

        error = FamilyMismatchError(_NAME, stated=stated, derived=derived)

        assert error.name == _NAME
        assert error.stated == stated
        assert error.derived == derived
        assert str(error) != ""


class TestAmbiguousFootprintError:
    def test_carries_name_backend_and_quantization(self) -> None:
        backend = BackendId("vllm")
        quantization = Quantization(scheme="fp16", bits=16)

        error = AmbiguousFootprintError(_NAME, backend=backend, quantization=quantization)

        assert error.name == _NAME
        assert error.backend == backend
        assert error.quantization == quantization
        assert str(error) != ""
