"""Hand-written `InferenceSessionLike`/`TokenizerLike` doubles — "the
stub is the entire SDK" (design.md "Testing Strategy"), `stub_llama.py`/
`stub_async_llm.py`'s precedent applied to the ONNX Runtime engine
seam. Unit tests under `tests/unit/engines/` never import `onnxruntime`,
`transformers`, or `numpy`; these classes satisfy `InferenceSessionLike`/
`TokenizerLike` structurally in their place.

Not a test file itself (no `test_` prefix) — pytest does not collect
it, mirroring `stub_llama.py`/`stub_async_llm.py`.

PR 1 only exercises construction-counting, declared input names, and
the `providers` tuple reaching the factory (residency round trip,
`test_onnxrt_residency.py`/`test_onnxrt_artifacts.py`). PR 2 extends
`run()`/`__call__()` recording for `_infer()`'s extraction, filtering,
and shape tests — plain nested lists, never numpy, doubling as proof
that OR9's extraction is duck-typed (design.md "Testing Strategy").
"""

from collections.abc import Mapping, Sequence
from typing import Any


class StubNodeArg:
    """Satisfies `NodeArgLike` structurally."""

    def __init__(self, name: str) -> None:
        self.name = name


class StubInferenceSession:
    """Satisfies `InferenceSessionLike` structurally. `providers` is not
    part of the Protocol — set by `make_stub_session_factory` below so a
    test can inspect which `providers` tuple reached construction (OR10),
    the same bookkeeping style as `StubLlama.create_completion_calls`."""

    def __init__(
        self,
        *,
        input_names: Sequence[str] = (),
        outputs: Sequence[Any] = (),
    ) -> None:
        self.input_names = tuple(input_names)
        self.outputs = outputs
        self.providers: tuple[str, ...] = ()
        self.model_path: str = ""
        self.run_calls: list[dict[str, Any]] = []

    def get_inputs(self) -> Sequence[StubNodeArg]:
        return [StubNodeArg(name) for name in self.input_names]

    def run(
        self, output_names: Sequence[str] | None, input_feed: Mapping[str, Any]
    ) -> Sequence[Any]:
        self.run_calls.append({"output_names": output_names, "input_feed": input_feed})
        return self.outputs


class StubTokenizer:
    """Satisfies `TokenizerLike` structurally."""

    def __init__(self, *, encoded: Mapping[str, Any] | None = None) -> None:
        self.encoded: Mapping[str, Any] = encoded if encoded is not None else {}
        self.call_args: list[dict[str, Any]] = []

    def __call__(
        self,
        text: Sequence[str],
        text_pair: Sequence[str] | None = None,
        *,
        padding: bool = True,
        truncation: bool = True,
        return_tensors: str = "np",
    ) -> Mapping[str, Any]:
        self.call_args.append(
            {
                "text": text,
                "text_pair": text_pair,
                "padding": padding,
                "truncation": truncation,
                "return_tensors": return_tensors,
            }
        )
        return self.encoded


def make_stub_session_factory(
    *,
    made: list[StubInferenceSession] | None = None,
    input_names: Sequence[str] = (),
    outputs: Sequence[Any] = (),
):
    """Recording session factory (`stub_llama.py`'s `_backend_with_stubs`
    precedent): each call constructs and records a fresh
    `StubInferenceSession`, so a test can assert exactly how many
    sessions were built and with which `model_path`/`providers`."""
    sessions: list[StubInferenceSession] = made if made is not None else []

    def factory(model_path: str, providers: Sequence[str]) -> StubInferenceSession:
        session = StubInferenceSession(input_names=input_names, outputs=outputs)
        session.model_path = model_path
        session.providers = tuple(providers)
        sessions.append(session)
        return session

    return factory, sessions


def make_stub_tokenizer_factory(
    *,
    made: list[StubTokenizer] | None = None,
    encoded: Mapping[str, Any] | None = None,
):
    """Recording tokenizer factory — `make_stub_session_factory`'s
    precedent applied to the second injected seam (OR6)."""
    tokenizers: list[StubTokenizer] = made if made is not None else []

    def factory(tokenizer_path: str) -> StubTokenizer:
        tokenizer = StubTokenizer(encoded=encoded)
        tokenizers.append(tokenizer)
        return tokenizer

    return factory, tokenizers
