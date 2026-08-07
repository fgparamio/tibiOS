"""Per-capability request payloads (`design.md` D22, ADR-0004).

ADR-0004 fixes that all decoding of `ExecutionContext.execution_parameters`
lives exclusively here, never in a Provider or a Backend. `CapabilityRequest`
is a `typing.Protocol` (design decision D1's structural-typing idiom, reused
across this codebase) with one classmethod, `parse`, implemented once per
capability: `ChatRequest`, `EmbeddingRequest`, `RerankRequest`.

Validation is `parse()`'s alone: unknown keys are ignored (an additive,
backward-compatible producer-side key must not break `tibios-core`);
malformed *known* keys are rejected — reject-don't-guess, never a
fabricated default for a value that was present but invalid. One shared
`RequestParseError(capability=..., parameter=..., reason=...)` — *which*
capability/parameter/reason failed is data, mirroring
`NoBackendAvailableError`'s own `capability=` kwarg (CP4), not a reason
to define three near-identical exception subclasses.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, Self

from tibios_ray.capabilities.errors import RequestParseError
from tibios_ray.capabilities.names import CapabilityName

_CHAT_CAPABILITY = CapabilityName("chat.generate")
_EMBEDDING_CAPABILITY = CapabilityName("embedding.generate")
_RERANK_CAPABILITY = CapabilityName("rerank.documents")


class CapabilityRequest(Protocol):
    """A typed decoding of `ExecutionContext.execution_parameters` for
    one capability. `parse()` is the only place that inspects raw
    parameter strings (ADR-0004)."""

    @classmethod
    def parse(cls, parameters: Mapping[str, str]) -> Self: ...


def _require_nonempty_str(
    parameters: Mapping[str, str], *, capability: CapabilityName, parameter: str
) -> str:
    if parameter not in parameters:
        raise RequestParseError(capability=capability, parameter=parameter, reason="missing")
    value = parameters[parameter]
    if not value.strip():
        raise RequestParseError(
            capability=capability, parameter=parameter, reason="empty after strip"
        )
    return value


def _require_positive_int(
    parameters: Mapping[str, str], *, capability: CapabilityName, parameter: str
) -> int:
    if parameter not in parameters:
        raise RequestParseError(capability=capability, parameter=parameter, reason="missing")
    raw = parameters[parameter]
    try:
        value = int(raw)
    except ValueError as error:
        raise RequestParseError(
            capability=capability, parameter=parameter, reason="not an integer"
        ) from error
    if value <= 0:
        raise RequestParseError(
            capability=capability, parameter=parameter, reason="must be > 0"
        )
    return value


def _optional_nonnegative_float(
    parameters: Mapping[str, str],
    *,
    capability: CapabilityName,
    parameter: str,
    default: float,
) -> float:
    if parameter not in parameters:
        return default
    raw = parameters[parameter]
    try:
        value = float(raw)
    except ValueError as error:
        raise RequestParseError(
            capability=capability, parameter=parameter, reason="not a float"
        ) from error
    if value < 0:
        raise RequestParseError(
            capability=capability, parameter=parameter, reason="must be >= 0"
        )
    return value


def _parse_json_string_tuple(
    parameters: Mapping[str, str],
    *,
    capability: CapabilityName,
    parameter: str,
    required: bool,
    allow_empty: bool,
) -> tuple[str, ...]:
    if parameter not in parameters:
        if required:
            raise RequestParseError(
                capability=capability, parameter=parameter, reason="missing"
            )
        return ()
    raw = parameters[parameter]
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RequestParseError(
            capability=capability, parameter=parameter, reason="invalid JSON"
        ) from error
    if not isinstance(decoded, list):
        raise RequestParseError(
            capability=capability, parameter=parameter, reason="not a JSON array"
        )
    if not decoded and not allow_empty:
        raise RequestParseError(capability=capability, parameter=parameter, reason="empty")
    for element in decoded:
        if not isinstance(element, str):
            raise RequestParseError(
                capability=capability, parameter=parameter, reason="non-string element"
            )
    return tuple(decoded)


@dataclass(frozen=True, slots=True, kw_only=True)
class ChatRequest:
    """`chat.generate`'s request. `prompt`, not `messages` — nothing
    below the Provider can apply a chat template (design.md D22); the
    caller is responsible for producing a final prompt string."""

    prompt: str
    max_tokens: int
    temperature: float = 1.0
    stop: tuple[str, ...] = ()

    @classmethod
    def parse(cls, parameters: Mapping[str, str]) -> Self:
        prompt = _require_nonempty_str(
            parameters, capability=_CHAT_CAPABILITY, parameter="prompt"
        )
        max_tokens = _require_positive_int(
            parameters, capability=_CHAT_CAPABILITY, parameter="max_tokens"
        )
        temperature = _optional_nonnegative_float(
            parameters, capability=_CHAT_CAPABILITY, parameter="temperature", default=1.0
        )
        stop = _parse_json_string_tuple(
            parameters,
            capability=_CHAT_CAPABILITY,
            parameter="stop",
            required=False,
            allow_empty=True,
        )
        return cls(prompt=prompt, max_tokens=max_tokens, temperature=temperature, stop=stop)


@dataclass(frozen=True, slots=True, kw_only=True)
class EmbeddingRequest:
    """`embedding.generate`'s request."""

    inputs: tuple[str, ...]

    @classmethod
    def parse(cls, parameters: Mapping[str, str]) -> Self:
        inputs = _parse_json_string_tuple(
            parameters,
            capability=_EMBEDDING_CAPABILITY,
            parameter="inputs",
            required=True,
            allow_empty=False,
        )
        return cls(inputs=inputs)


@dataclass(frozen=True, slots=True, kw_only=True)
class RerankRequest:
    """`rerank.documents`'s request."""

    query: str
    documents: tuple[str, ...]

    @classmethod
    def parse(cls, parameters: Mapping[str, str]) -> Self:
        query = _require_nonempty_str(
            parameters, capability=_RERANK_CAPABILITY, parameter="query"
        )
        documents = _parse_json_string_tuple(
            parameters,
            capability=_RERANK_CAPABILITY,
            parameter="documents",
            required=True,
            allow_empty=False,
        )
        return cls(query=query, documents=documents)
