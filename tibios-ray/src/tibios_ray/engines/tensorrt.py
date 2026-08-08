"""The TensorRT-LLM text-generation Engine (`tensorrt-llm-text-backend`
spec) — the third concrete Backend Adapter for `chat.generate`,
executing against a **precompiled** engine artifact. `engines/tensorrt.py`
mirrors `engines/vllm.py` end to end (design.md "Technical Approach"):
module-local structural Protocols for the SDK surface, a lazy
`importlib` factory seam (LC11/VL8), and — starting in a later PR — one
shared lazily-constructed refcounted `_ModelRuntime` (VL2).

**This file's current state is PR 2 of the change's slice plan: the SDK
seam only** — the Protocols, the default engine/sampling-params
factories, and `UnknownSessionError` (added here ahead of its first use
so the residency seam PR 3 adds can reference it without touching this
file's imports again). Residency (`_ModelRuntime`, `backend_id`,
`supports`, `acquire`, `release`) lands in PR 3; `generate()`,
cancellation, and Composition Root wiring land in PR 4.

Two SDK-shape differences from `vllm.py`, both already structural in
this PR's contracts even though `generate()` itself is not implemented
yet: construction is **blocking** — `LLMLike.shutdown()`/the real
constructor are plain synchronous calls, so the default factory's body
is `await asyncio.to_thread(...)` (design decision D35) instead of
vLLM's on-loop `AsyncLLM.from_engine_args(...)` — and the incremental
token lives in a **separate field**, `CompletionOutputLike.text_diff`,
never the cumulative `.text` (design decision D37; encoded structurally
in the Protocol shape now, read at the actual call site in PR 4).

The Core Principle this Backend exists to make structural — "engine
compilation is an out-of-band operator/provisioning concern, never a
Worker responsibility" (Invariant 2 of the spec) — is enforced here by
`default_engine_factory`'s pre-flight artifact predicate (design
decision D39): the configured path must exist, be a directory, and
contain at least one compiled-engine file, checked entirely on the
filesystem, before `tensorrt_llm` is ever imported. A path that fails
this check raises `InvalidEngineArtifactError` — a module-local,
`ConfigError`-shaped failure (the real `tibios_ray.config.ConfigError`
cannot be imported here: the layering guard restricts `engines/*.py` to
importing only `tibios_ray.backends`) — instead of ever reaching a
constructor call that could otherwise start an implicit, unbounded
compilation step.
"""

import asyncio
import importlib
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

from tibios_ray.backends.adapter import BackendId
from tibios_ray.backends.text import TextRequest

TENSORRT_LLM_BACKEND_ID = BackendId("tensorrt_llm")

# D38/D39: the same env var name `config.py`'s `_TENSORRT_ENGINE_PATH`
# constant carries — duplicated here, not imported, per the layering
# guard's `engines -> backends` only rule. Naming it in the pre-flight
# failure message is what makes the failure attributable.
_ENGINE_PATH_ENV_VAR = "TIBIOS_RAY_TENSORRT_ENGINE_PATH"


class CompletionOutputLike(Protocol):
    """Structural shape of one `RequestOutput.outputs[N]` entry."""

    @property
    def text_diff(self) -> str: ...  # the DELTA (D37) — `.text` is CUMULATIVE, never read it


class RequestOutputLike(Protocol):
    """Structural shape of the handle `LLMLike.generate_async` returns —
    the handle IS the async iterator (D36), unlike vLLM's separate
    `AsyncIterator[RequestOutputLike]` return type."""

    @property
    def outputs(self) -> Sequence[CompletionOutputLike]: ...

    @property
    def finished(self) -> bool: ...  # authoritative terminator (VL10 inherited)

    def __aiter__(self) -> AsyncIterator["RequestOutputLike"]: ...

    async def abort(self) -> None: ...  # D36: handle-scoped, no engine-level abort(request_id)


class LLMLike(Protocol):
    """Structural shape of `tensorrt_llm.LLM` — the only SDK surface
    this module uses (design.md "Key Contracts")."""

    def generate_async(
        self, prompt: str, sampling_params: Any, streaming: bool
    ) -> RequestOutputLike: ...

    def shutdown(self) -> None: ...  # blocking → to_thread (D35)


type LLMFactory = Callable[[str], Awaitable[LLMLike]]  # VL7's signature, D35's body
type SamplingParamsFactory = Callable[[TextRequest], Any]  # VL8's quarantine, minus VL9's flag


class InvalidEngineArtifactError(Exception):
    """Raised by `default_engine_factory`'s D39 pre-flight predicate for
    a configured `engine_path` that does not exist, is not a directory,
    or contains no compiled-engine file. Deliberately module-local and
    shaped like `tibios_ray.config.ConfigError` (`variable`/`reason`,
    same `f"{variable!r}: {reason}"` message) rather than importing that
    class: `engines/*.py` may import only `tibios_ray.backends`, per the
    layering guard (`test_engines_layering.py`)."""

    def __init__(self, *, variable: str, reason: str) -> None:
        self.variable = variable
        self.reason = reason
        super().__init__(f"{variable!r}: {reason}")


def _check_engine_artifact(engine_path: str) -> None:
    """D39's pre-flight predicate — evaluated entirely on the
    filesystem, before `tensorrt_llm` is ever imported, so a
    misconfigured path never reaches a constructor call that could
    otherwise start an implicit, unbounded compilation step. Layout
    knowledge is deliberately shallow (design.md "Accepted, explicit
    limitations"): existence, directory-ness, and the presence of at
    least one `*.engine` file — nothing about its internal contents."""
    path = Path(engine_path)
    if not path.exists():
        raise InvalidEngineArtifactError(
            variable=_ENGINE_PATH_ENV_VAR,
            reason=f"path {engine_path!r} does not exist",
        )
    if not path.is_dir():
        raise InvalidEngineArtifactError(
            variable=_ENGINE_PATH_ENV_VAR,
            reason=f"path {engine_path!r} is not a directory",
        )
    if not any(path.glob("*.engine")):
        raise InvalidEngineArtifactError(
            variable=_ENGINE_PATH_ENV_VAR,
            reason=(
                f"directory {engine_path!r} contains no compiled engine artifact "
                "(*.engine) — point this at a precompiled TensorRT-LLM engine "
                "directory (see the Operational Model)"
            ),
        )


async def default_engine_factory(engine_path: str) -> LLMLike:
    """Constructs the real `tensorrt_llm.LLM`, importing the SDK lazily
    and only when this function runs (design decision LC11 inherited
    via VL8) — never at module import time.

    D39's pre-flight predicate runs first, entirely off the SDK. Only a
    path that passes it reaches the lazy import below.

    D35: the SDK constructor is a plain, synchronous call — unlike
    vLLM's `AsyncLLM`, it attaches no asyncio machinery to the
    constructing loop, so running it on-loop would stall the event loop
    (and therefore the gRPC transport serving every other capability)
    for the entire engine load. `asyncio.to_thread` confines that stall
    to a worker thread. Teardown is symmetric — see the `to_thread`
    call `vllm.py`'s `release()` already makes for `shutdown()`."""

    _check_engine_artifact(engine_path)
    try:
        tensorrt_llm = importlib.import_module("tensorrt_llm")
    except ModuleNotFoundError as error:
        raise ModuleNotFoundError(
            "tensorrt_llm is required to construct the default TensorRT-LLM "
            "engine but is not installed. It has no repo-wide package index "
            "(D32): install it with `uv add tibios-ray[tensorrt] --index "
            "<the NVIDIA wheel index named in pyproject.toml's tensorrt extra "
            "comment>`, or use a prebuilt NGC container image that already "
            "provides it. See the Operational Model for both channels."
        ) from error
    return await asyncio.to_thread(tensorrt_llm.LLM, model=engine_path)


def default_sampling_params_factory(request: TextRequest) -> Any:
    """Constructs the real `tensorrt_llm.SamplingParams`, importing the
    SDK lazily (LC11/VL8 inherited). Unlike vLLM's `SamplingParams`,
    no `output_kind`/DELTA flag exists to set (D37 — TensorRT-LLM solves
    cumulative-vs-delta with `CompletionOutputLike.text_diff`, a field,
    not a sampling parameter), so this factory carries only the fields
    `TextRequest` actually maps: `max_tokens`, `temperature`, `stop`,
    and `n=1` (the only index `generate()` reads)."""

    try:
        tensorrt_llm = importlib.import_module("tensorrt_llm")
    except ModuleNotFoundError as error:
        raise ModuleNotFoundError(
            "tensorrt_llm is required to construct the default TensorRT-LLM "
            "sampling params but is not installed. Install it with the "
            "optional extra: `uv add tibios-ray[tensorrt] --index <the NVIDIA "
            "wheel index named in pyproject.toml's tensorrt extra comment>` "
            "(or use a prebuilt NGC container image)."
        ) from error
    SamplingParams = tensorrt_llm.SamplingParams
    return SamplingParams(
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        stop=list(request.stop),
        n=1,  # TextRequest has no `n` field; generate() only reads outputs[0]
    )


class UnknownSessionError(LookupError):
    """Raised by `release()`/`generate()` (PR 3/PR 4) for a `session_id`
    absent from the residency side table — either never acquired on
    this adapter instance, or already released. Redefined module-locally
    rather than imported from `engines/vllm.py` (design.md "File
    Changes"): importing it would couple two engines through a module
    named after an unrelated SDK for a small win before the rule of
    three (the third engine to need this exact shape is the one that
    should extract it, per design.md's Open Questions)."""

    def __init__(self, session_id: str) -> None:
        super().__init__(f"unknown or already-released TensorRT-LLM session: {session_id!r}")
        self.session_id = session_id
