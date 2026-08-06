"""Tests for `tibios_ray.catalog.catalog.ModelCatalog` (`design.md` Key
Contracts, design decisions MC6/MC7).

Slice 2a covers: construction (`_by_name`/`_by_family` indices only),
`families()`, `models()`, `get()`, and the two construction invariants
that do not require the `_footprints` index (`DuplicateModelError`,
`FamilyMismatchError`). `supports()`/`quantizations()`/`requirements()`
and `AmbiguousFootprintError` land in slice 2b, per the documented 2a/2b
fallback split (`design.md` Module/Slice Plan).

Tested against a fabricated three-entry fixture catalog, not real data —
query semantics and catalog data are independent concerns and must fail
independently.
"""

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import ModelFamily
from tibios_ray.catalog.catalog import ModelCatalog
from tibios_ray.catalog.errors import DuplicateModelError, FamilyMismatchError, UnknownModelError
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
                    backend=_LLAMA_CPP, quantizations=frozenset({_Q4_K_M}), min_vram_bytes=5
                ),
                BackendSupport(
                    backend=_LLAMA_CPP, quantizations=frozenset({_Q8_0}), min_vram_bytes=10
                ),
                BackendSupport(backend=_VLLM, quantizations=frozenset({_FP16}), min_vram_bytes=20),
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
                    backend=_VLLM, quantizations=frozenset({_AWQ, _GPTQ}), min_vram_bytes=5
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
            {BackendSupport(backend=_VLLM, quantizations=frozenset({_FP16}), min_vram_bytes=805)}
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
                {BackendSupport(backend=_VLLM, quantizations=frozenset({_FP16}), min_vram_bytes=36)}
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
