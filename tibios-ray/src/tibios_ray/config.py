"""Per-engine configuration surface for the Composition Root
(`worker-configuration` spec) — design decision D19.

`WorkerConfig.from_env()` is the *only* sanctioned way process
configuration reaches `worker.py::build_runtime()`. Every field is
`None`-able: `None` means "this engine is not configured", never a
guessed or hardcoded default (`worker-configuration` spec, "Absent
configuration is represented as absent, not guessed"). Present-but-
malformed configuration raises `ConfigError` instead of silently
skipping the value or substituting a default ("Reject-Don't-Guess
Configuration Parsing").

Configuration source is environment variables (D19, Q7) — this repo's
existing deployment surface (`server.py`'s `os.environ.get(...)`
precedent), not a structured file. The `env: Mapping[str, str] | None`
parameter is the repo's standard factory seam (mirrors `LlamaFactory`,
`SessionFactory`, `TokenizerFactory`): tests pass a plain `dict`, no
`monkeypatch` needed.

Per `worker-configuration` spec's "Composition Root Is the
Configuration Surface's Sole Consumer": only `worker.py::build_runtime()`
may read from this module or from `os.environ` for per-engine artifact
configuration — enforced by `tests/unit/config/test_config_isolation.py`.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Self

# D19/D27: a pre-warmed pool of `Llama` instances (slice 6) needs a size
# even when the operator supplies no explicit
# `TIBIOS_RAY_LLAMACPP_POOL_SIZE` — absence of a sizing knob is not
# absence of the engine's artifact configuration
# (`worker-configuration` spec, "Absent pool-size configuration falls
# back to a documented default pool size"). `1` is a judgment call, not
# a measurement — the same honesty `engines/llamacpp.py`'s
# `_QUEUE_MAXSIZE`/`_PUT_POLL_SECONDS` are documented with: the most
# conservative value that still lets a single-artifact deployment serve
# requests, leaving any wider concurrency to an operator's explicit
# opt-in.
DEFAULT_LLAMACPP_POOL_SIZE = 1

_LLAMACPP_GGUF = "TIBIOS_RAY_LLAMACPP_GGUF"
_LLAMACPP_POOL_SIZE = "TIBIOS_RAY_LLAMACPP_POOL_SIZE"
_VLLM_MODEL = "TIBIOS_RAY_VLLM_MODEL"
_TENSORRT_ENGINE_PATH = "TIBIOS_RAY_TENSORRT_ENGINE_PATH"


class ConfigError(Exception):
    """Raised by `WorkerConfig.from_env()` for configuration that is
    present but malformed or incomplete — never for merely absent
    configuration, which is represented as `None` (`worker-configuration`
    spec, "Reject-Don't-Guess Configuration Parsing").

    Carries the offending `variable` name and a human-readable `reason`
    so the failure is explicit and attributable, not a bare traceback
    from whatever parsing step happened to raise first."""

    def __init__(self, *, variable: str, reason: str) -> None:
        self.variable = variable
        self.reason = reason
        super().__init__(f"{variable!r}: {reason}")


@dataclass(frozen=True, slots=True, kw_only=True)
class LlamaCppConfig:
    """`TIBIOS_RAY_LLAMACPP_GGUF` + `TIBIOS_RAY_LLAMACPP_POOL_SIZE`
    (D19). Field names mirror `engines.llamacpp.LlamaCppTextBackend`'s
    constructor keywords (`model_path`) so the Composition Root can
    forward this object's fields by name without renaming."""

    model_path: str
    pool_size: int = DEFAULT_LLAMACPP_POOL_SIZE


@dataclass(frozen=True, slots=True, kw_only=True)
class VllmConfig:
    """`TIBIOS_RAY_VLLM_MODEL` (D19). `model` mirrors
    `engines.vllm.VllmTextBackend`'s constructor keyword."""

    model: str


@dataclass(frozen=True, slots=True, kw_only=True)
class TensorrtLlmConfig:
    """`TIBIOS_RAY_TENSORRT_ENGINE_PATH` (D38). `engine_path` mirrors
    `engines.tensorrt.TensorrtLlmTextBackend`'s constructor keyword —
    deliberately not named `model`, since the value is a path to a
    precompiled engine artifact, never an HF checkpoint (D38)."""

    engine_path: str


@dataclass(frozen=True, slots=True, kw_only=True)
class OnnxConfig:
    """One ONNX artifact triple — used independently for
    `TIBIOS_RAY_ONNX_EMBEDDING_*` and `TIBIOS_RAY_ONNX_RERANK_*` (D19).
    Field names mirror `engines.onnxrt._OnnxBackendBase`'s constructor
    keywords (`model_path`, `tokenizer_path`, `output_name`)."""

    model_path: str
    tokenizer_path: str
    output_name: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkerConfig:
    """Every field `None`-able: `None` means "this engine is not
    configured" (D19). Aggregates all four engine slots the Composition
    Root can wire — `llamacpp`/`vllm`/`tensorrt_llm` for `text`,
    `onnx_embedding` for `embedding`, `onnx_rerank` for `rerank`."""

    llamacpp: LlamaCppConfig | None
    vllm: VllmConfig | None
    onnx_embedding: OnnxConfig | None
    onnx_rerank: OnnxConfig | None
    tensorrt_llm: TensorrtLlmConfig | None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Self:
        """Reads process configuration and constructs a `WorkerConfig`.
        Defaults to `os.environ` — the sole call site in the codebase
        permitted to do so outside this module (`worker.py`'s own
        `env or os.environ`-style default is the same pattern, one
        layer up)."""

        source = env if env is not None else os.environ
        return cls(
            llamacpp=_llamacpp_config(source),
            vllm=_vllm_config(source),
            onnx_embedding=_onnx_config(source, prefix="TIBIOS_RAY_ONNX_EMBEDDING"),
            onnx_rerank=_onnx_config(source, prefix="TIBIOS_RAY_ONNX_RERANK"),
            tensorrt_llm=_tensorrt_config(source),
        )


def _parse_pool_size(raw: str, *, variable: str) -> int:
    try:
        value = int(raw)
    except ValueError as error:
        raise ConfigError(
            variable=variable, reason=f"must be a positive integer, got {raw!r}"
        ) from error
    if value <= 0:
        raise ConfigError(
            variable=variable, reason=f"must be a positive integer, got {raw!r}"
        )
    return value


def _llamacpp_config(env: Mapping[str, str]) -> LlamaCppConfig | None:
    model_path = env.get(_LLAMACPP_GGUF)
    if model_path is None:
        # Engine unconfigured: any stray `TIBIOS_RAY_LLAMACPP_POOL_SIZE`
        # is ignored rather than validated — there is no engine for it
        # to size.
        return None

    raw_pool_size = env.get(_LLAMACPP_POOL_SIZE)
    if raw_pool_size is None:
        pool_size = DEFAULT_LLAMACPP_POOL_SIZE
    else:
        pool_size = _parse_pool_size(raw_pool_size, variable=_LLAMACPP_POOL_SIZE)

    return LlamaCppConfig(model_path=model_path, pool_size=pool_size)


def _vllm_config(env: Mapping[str, str]) -> VllmConfig | None:
    model = env.get(_VLLM_MODEL)
    if model is None:
        return None
    return VllmConfig(model=model)


def _tensorrt_config(env: Mapping[str, str]) -> TensorrtLlmConfig | None:
    engine_path = env.get(_TENSORRT_ENGINE_PATH)
    if engine_path is None:
        return None
    return TensorrtLlmConfig(engine_path=engine_path)


def _onnx_config(env: Mapping[str, str], *, prefix: str) -> OnnxConfig | None:
    model_variable = f"{prefix}_MODEL"
    tokenizer_variable = f"{prefix}_TOKENIZER"
    output_name_variable = f"{prefix}_OUTPUT_NAME"

    model_path = env.get(model_variable)
    tokenizer_path = env.get(tokenizer_variable)

    if model_path is None and tokenizer_path is None:
        return None
    if model_path is None:
        raise ConfigError(
            variable=model_variable,
            reason=f"required because {tokenizer_variable!r} is set, but is absent",
        )
    if tokenizer_path is None:
        raise ConfigError(
            variable=tokenizer_variable,
            reason=f"required because {model_variable!r} is set, but is absent",
        )

    return OnnxConfig(
        model_path=model_path,
        tokenizer_path=tokenizer_path,
        output_name=env.get(output_name_variable),
    )
