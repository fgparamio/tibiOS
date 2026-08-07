# 4. Capability Request Boundary

## Status

Accepted

## Context

`ExecutionContext` is fixed by the wire contract (`worker.proto`): one flat
message, no nested envelope, `execution_parameters` typed as
`map<string, string>` (`ExecutionContext`, field 7). That shape is owned by
the contract between `tibios-core` and `tibios-ray` — tibios-ray consumes it,
it does not redesign it from within a single Backend or Provider.

Different capabilities need structurally incompatible payloads from that
same flat map: `rerank.documents` needs a list of documents, `chat.generate`
needs a list of role/content messages — neither fits a
`Mapping[str, str]` value without some encoding. Nothing today owns that
encoding/decoding step, so nothing stops it from being invented ad hoc,
differently, at each call site.

Backends (`TextGenerationBackend.generate()`, `EmbeddingBackend.embed()`,
`RerankBackend.rerank()`) already accept typed parameters
(`TextRequest`, `Sequence[str]`, `Sequence[str]` for documents). They have
no reason to know the wire ever encoded those as JSON inside a string map,
and must not be given a reason to.

## Decision

- Each Capability defines its own typed Request (`ChatRequest`,
  `EmbeddingRequest`, `RerankRequest`, ...).
- Each Request implements a common structural `Protocol`,
  `CapabilityRequest`, whose only required member is a `parse` classmethod:
  `parse(cls, parameters: Mapping[str, str]) -> Self`. The Protocol exists
  for a shared *construction shape*, not shared fields — mirrors
  `CapabilityProvider`'s own no-base-class, structural style
  ([0001](0001-provider-backend-composition.md)).
- All decoding of `execution_parameters` — which keys exist, which are
  required, how a list or a document is encoded — lives exclusively inside
  the matching `*Request.parse()`. No other module reads
  `execution_parameters` directly.
- Providers work only with parsed, typed Requests. A Provider never touches
  `Mapping[str, str]` itself; it calls `SomeRequest.parse(context.
  execution_parameters)` and passes the result onward.
- Backends never receive, and never know about, `Mapping[str, str]`.
- `parse()` follows reject-don't-guess: a missing required key, or a value
  that fails to decode as the expected shape, raises immediately. No
  fallback formats, no best-effort coercion.
- Structured values are JSON-encoded within the string value (e.g.
  `documents = '["doc1","doc2"]'`) — the pragmatic encoding available
  under today's `map<string, string>` constraint, not a new wire format.

Normative invariant:

> No component below the Capability Request boundary may depend on the
> wire representation of request parameters.

## Consequences

Benefits:

- Backends are fully isolated from the wire format; they only ever see
  typed, validated data.
- All validation for one capability's input is centralized in one place
  (`*Request.parse()`) instead of scattered across call sites.
- "Reject, don't guess" is enforced structurally, not by convention.
- If `execution_parameters`'s encoding ever changes (`oneof`, typed
  messages, `google.protobuf.Struct`, or anything else), only the
  `CapabilityRequest` implementations change. Providers and Backends do
  not.

Trade-off:

- While the wire contract uses `map<string, string>`, every structured
  value must be serialized (currently JSON) to fit inside a string. This is
  a conscious limitation of the current wire contract, not a design choice
  made by tibios-ray, and is expected to be revisited if/when the contract
  gains richer typing.
