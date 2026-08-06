"""Tests for `tibios_ray.catalog.catalog.ModelCatalog` (`design.md` Key
Contracts, design decisions MC6/MC7).

Slice 2a covered construction (`_by_name`/`_by_family` indices),
`families()`, `models()`, `get()`, and the `DuplicateModelError`/
`FamilyMismatchError` construction invariants. Slice 2b adds
`TestConstructionInvariants.test_ambiguous_footprint_...` plus
`TestSupports`/`TestQuantizations`/`TestRequirements` — the
`_footprints` index, `AmbiguousFootprintError`, and
`supports()`/`quantizations()`/`requirements()` — per the documented
2a/2b fallback split (`design.md` Module/Slice Plan).

Tested against a fabricated three-entry fixture catalog, not real data —
query semantics and catalog data are independent concerns and must fail
independently. The fixture deliberately includes one model with two
tiers on one backend (`qwen` on `llama_cpp`) and one model absent from a
backend (`llama` has no `llama_cpp` row), so `supports`/`quantizations`/
`requirements` all have a real negative case.
"""

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import ModelFamily
from tibios_ray.catalog.catalog import ModelCatalog
from tibios_ray.catalog.errors import (
    AmbiguousFootprintError,
    DuplicateModelError,
    FamilyMismatchError,
    UnknownModelError,
    UnsupportedServingError,
)
from tibios_ray.catalog.model import BackendSupport, ModelDescriptor
from tibios_ray.catalog.names import PublishedModelName
from tibios_ray.selection.policy import Quantization

_LLAMA_CPP = BackendId("llama_cpp")
_VLLM = BackendId("vllm")
_Q4_K_M = Quantization(scheme="q4_k_m", bits=4)
_Q8_0 = Quantization(scheme="q8_0", bits=8)
_FP16 = Quantization(scheme="fp16", bits=16)
_AWQ = Quantization(scheme="awq", bits=4)
_GPTQ = Quantization(scheme="gptq", bits=4)

_QWEN_NAME = PublishedModelName("Qwen/Qwen3-8B")
_LLAMA_NAME = PublishedModelName("meta-llama/Llama-3.1-8B-Instruct")
_DEEPSEEK_NAME = PublishedModelName("deepseek-ai/DeepSeek-V3")


def _qwen_entry() -> ModelDescriptor:
    # Deliberately carries two tiers on one backend (llama_cpp) so query
    # tests in slice 2b have a real multi-tier-per-backend case (MC5).
    return ModelDescriptor(
        name=_QWEN_NAME,
        family=ModelFamily("qwen"),
        parameter_count=8_200_000_000,
        context_window=32_768,
        serving=frozenset(
            {
                BackendSupport(
                    backend=_LLAMA_CPP, quantizations=frozenset({_Q4_K_M}), min_vram_gb=5
                ),
                BackendSupport(
                    backend=_LLAMA_CPP, quantizations=frozenset({_Q8_0}), min_vram_gb=10
                ),
                BackendSupport(backend=_VLLM, quantizations=frozenset({_FP16}), min_vram_gb=20),
            }
        ),
    )


def _llama_entry() -> ModelDescriptor:
    # Deliberately absent from llama_cpp so `supports()` has a real
    # negative case in slice 2b.
    return ModelDescriptor(
        name=_LLAMA_NAME,
        family=ModelFamily("llama"),
        parameter_count=8_030_000_000,
        context_window=131_072,
        serving=frozenset(
            {
                BackendSupport(
                    backend=_VLLM, quantizations=frozenset({_AWQ, _GPTQ}), min_vram_gb=5
                )
            }
        ),
    )


def _deepseek_entry() -> ModelDescriptor:
    return ModelDescriptor(
        name=_DEEPSEEK_NAME,
        family=ModelFamily("deepseek"),
        parameter_count=671_000_000_000,
        context_window=163_840,
        serving=frozenset(
            {BackendSupport(backend=_VLLM, quantizations=frozenset({_FP16}), min_vram_gb=805)}
        ),
    )


def _catalog() -> ModelCatalog:
    return ModelCatalog([_qwen_entry(), _llama_entry(), _deepseek_entry()])


class TestFamilies:
    def test_lists_every_family_with_at_least_one_entry(self) -> None:
        catalog = _catalog()
        assert catalog.families() == {
            ModelFamily("qwen"),
            ModelFamily("llama"),
            ModelFamily("deepseek"),
        }


class TestModels:
    def test_returns_entries_for_a_known_family(self) -> None:
        catalog = _catalog()
        assert catalog.models(ModelFamily("qwen")) == (_qwen_entry(),)

    def test_returns_empty_tuple_for_an_unknown_family(self) -> None:
        catalog = _catalog()
        assert catalog.models(ModelFamily("nonexistent")) == ()

    def test_is_ordered_by_name_value(self) -> None:
        alpha = ModelDescriptor(
            name=PublishedModelName("Qwen/Qwen3-14B"),
            family=ModelFamily("qwen"),
            parameter_count=14_800_000_000,
            context_window=32_768,
            serving=frozenset(
                {BackendSupport(backend=_VLLM, quantizations=frozenset({_FP16}), min_vram_gb=36)}
            ),
        )
        catalog = ModelCatalog([_qwen_entry(), alpha])
        models = catalog.models(ModelFamily("qwen"))
        assert [m.name.value for m in models] == sorted(m.name.value for m in models)


class TestGet:
    def test_returns_the_matching_descriptor(self) -> None:
        catalog = _catalog()
        assert catalog.get(_QWEN_NAME) == _qwen_entry()

    def test_raises_unknown_model_error_for_an_unknown_name(self) -> None:
        catalog = _catalog()
        try:
            catalog.get(PublishedModelName("unknown/model"))
        except UnknownModelError as error:
            assert error.name == PublishedModelName("unknown/model")
        else:
            raise AssertionError("expected UnknownModelError")


class TestConstructionInvariants:
    def test_duplicate_name_raises_duplicate_model_error(self) -> None:
        try:
            ModelCatalog([_qwen_entry(), _qwen_entry()])
        except DuplicateModelError as error:
            assert error.name == _QWEN_NAME
        else:
            raise AssertionError("expected DuplicateModelError")

    def test_family_mismatch_raises_family_mismatch_error(self) -> None:
        mismatched = ModelDescriptor(
            name=_QWEN_NAME,
            family=ModelFamily("llama"),
            parameter_count=8_200_000_000,
            context_window=32_768,
            serving=frozenset(),
        )
        try:
            ModelCatalog([mismatched])
        except FamilyMismatchError as error:
            assert error.name == _QWEN_NAME
            assert error.stated == ModelFamily("llama")
            assert error.derived == ModelFamily("qwen")
        else:
            raise AssertionError("expected FamilyMismatchError")

    def test_ambiguous_footprint_raises_ambiguous_footprint_error(self) -> None:
        # Two BackendSupport rows sharing the same (backend, quantization)
        # pair — the ambiguity the `_footprints` index cannot represent.
        ambiguous = ModelDescriptor(
            name=_QWEN_NAME,
            family=ModelFamily("qwen"),
            parameter_count=8_200_000_000,
            context_window=32_768,
            serving=frozenset(
                {
                    BackendSupport(
                        backend=_VLLM, quantizations=frozenset({_FP16}), min_vram_gb=20
                    ),
                    BackendSupport(
                        backend=_VLLM, quantizations=frozenset({_FP16}), min_vram_gb=21
                    ),
                }
            ),
        )
        try:
            ModelCatalog([ambiguous])
        except AmbiguousFootprintError as error:
            assert error.name == _QWEN_NAME
            assert error.backend == _VLLM
            assert error.quantization == _FP16
        else:
            raise AssertionError("expected AmbiguousFootprintError")


class TestSupports:
    def test_true_for_a_backend_the_model_serves(self) -> None:
        catalog = _catalog()
        assert catalog.supports(_QWEN_NAME, _LLAMA_CPP) is True

    def test_false_for_a_known_model_on_an_unadvertised_backend(self) -> None:
        catalog = _catalog()
        assert catalog.supports(_LLAMA_NAME, _LLAMA_CPP) is False

    def test_raises_unknown_model_error_for_an_unknown_model(self) -> None:
        catalog = _catalog()
        try:
            catalog.supports(PublishedModelName("unknown/model"), _VLLM)
        except UnknownModelError:
            pass
        else:
            raise AssertionError("expected UnknownModelError")


class TestQuantizations:
    def test_unions_across_every_row_sharing_a_backend(self) -> None:
        # qwen carries two BackendSupport rows on llama_cpp (q4_k_m,
        # q8_0) — MC5's multi-tier-per-backend shape, exercised end to
        # end through the query surface.
        catalog = _catalog()
        assert catalog.quantizations(_QWEN_NAME, _LLAMA_CPP) == frozenset({_Q4_K_M, _Q8_0})

    def test_empty_when_supports_is_false(self) -> None:
        catalog = _catalog()
        assert catalog.quantizations(_LLAMA_NAME, _LLAMA_CPP) == frozenset()

    def test_raises_unknown_model_error_for_an_unknown_model(self) -> None:
        catalog = _catalog()
        try:
            catalog.quantizations(PublishedModelName("unknown/model"), _VLLM)
        except UnknownModelError:
            pass
        else:
            raise AssertionError("expected UnknownModelError")


class TestRequirements:
    def test_returns_min_vram_gb_for_the_exact_triple(self) -> None:
        catalog = _catalog()
        assert catalog.requirements(_QWEN_NAME, _LLAMA_CPP, _Q4_K_M) == 5
        assert catalog.requirements(_QWEN_NAME, _LLAMA_CPP, _Q8_0) == 10

    def test_raises_unsupported_serving_error_for_a_pair_not_in_the_serving_table(self) -> None:
        catalog = _catalog()
        try:
            catalog.requirements(_LLAMA_NAME, _LLAMA_CPP, _AWQ)
        except UnsupportedServingError as error:
            assert error.name == _LLAMA_NAME
            assert error.backend == _LLAMA_CPP
            assert error.quantization == _AWQ
        else:
            raise AssertionError("expected UnsupportedServingError")

    def test_raises_unknown_model_error_for_an_unknown_model(self) -> None:
        catalog = _catalog()
        try:
            catalog.requirements(PublishedModelName("unknown/model"), _VLLM, _FP16)
        except UnknownModelError:
            pass
        else:
            raise AssertionError("expected UnknownModelError")
