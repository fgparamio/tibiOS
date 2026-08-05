# TibiOS CLI

Version: 1.0

## Purpose

The CLI is the human interface to the Runtime. Where the SDK (`27-sdk.md`) projects the Runtime API (`26-runtime-api.md`) into a programming language, the CLI projects it into a human command language — the same contract, addressed to a person typing at a terminal instead of a program calling a function.

The CLI defines no capability the Runtime API does not already expose, and contains no domain logic: every decision it surfaces was already made by whichever Runtime domain owns it. It is not another API, and it is not a shortcut around the Runtime API's boundary.

## Ownership

The CLI is a projection pattern. Multiple CLI implementations may exist — different languages, different platforms, a minimal scriptable one alongside a fuller interactive one — none of them architecturally privileged over another.

The real dependency is:

```
CLI
 │
 ▼
Runtime API Capability Surface
 │
 ▼
Runtime Domains
```

A concrete CLI may implement this interaction through an SDK, through a purpose-built Runtime API client, or through an embedded in-process call. Commands invoke Runtime API capabilities, never Runtime domains directly. An SDK is one possible implementation of that interaction, not an architectural requirement.

This keeps the dependency graph a star, not a chain: the Runtime API is the one thing every consumer depends on, but no consumer depends on another.

```
             Runtime API
            /     |      \
           /      |       \
        SDK      CLI    Other Clients
```

`Runtime API → SDK → CLI` — the CLI being forced through the SDK — is exactly the unnecessarily strong dependency this graph avoids.

## Core Principles

- The CLI projects Runtime API capabilities into human commands. It never projects Runtime internals.
- The CLI is a projection pattern with multiple implementations, never a single canonical executable.
- Commands invoke Runtime API capabilities, never Runtime domains directly.
- The CLI introduces no capability the Runtime API does not already expose.
- Consumers compose around the Runtime API. They never depend on each other.

## Command Surface

Every leaf command corresponds to exactly one Runtime API capability, no more, no fewer — `tibi workload submit`, `tibi object get`, `tibi events watch`, `tibi execution status`, `tibi cluster inspect`, `tibi allocation manage`, projecting the same capabilities `26-runtime-api.md` already defined, expressed as terminal commands rather than function signatures. Higher-level command groups exist only for organization.

A command that performs "submit, then watch" is simply two capability invocations orchestrated by the CLI. It introduces no new Runtime capability.

## Relationship with the Runtime API

The CLI consumes Runtime API capabilities. It never communicates with Runtime domains, Inbound Ports, or transports directly. Every command's behavior is fully defined by the Runtime API capability it invokes — the CLI adds no behavior a capability didn't already define, only a human-addressable name for invoking it.

If a useful command cannot be expressed as an existing Runtime API capability, that is a gap in `26-runtime-api.md`, never a reason for the CLI to reach past it.

## Human Ergonomics

The CLI may add naming conventions, help text, shell autocompletion, interactive confirmations for destructive operations, and multiple output formats (human-readable, JSON, …) — all of this is presentation for a human operator, never a change to what a capability means or does. Output formatting translates representation, never meaning. Ergonomics remain presentation. Capabilities remain contract — the same rule `27-sdk.md` already established for a programming-language projection applies unchanged to a human-command projection.

A confirmation prompt before a destructive operation is a CLI-layer safeguard for a human operator; it is never a substitute for authorization, which is always evaluated by Trust before the underlying capability executes (`26-runtime-api.md`'s Authentication and Authorization at the Boundary) — the CLI cannot authorize an operation the Runtime API would otherwise reject.

## Streaming Model

Runtime API capabilities that stream (`Observe Events`, the in-flight half of `Query Execution`) are projected into whatever a terminal can render continuously — a live-updating table, a scrolling log, a progress indicator — without exposing the underlying transport (`22-networking.md`'s Runtime Streams remain entirely invisible here, exactly as `26-runtime-api.md` and `27-sdk.md` already require at their own layers).

A streaming command still carries only one capability's worth of meaning per rendered item — `tibi events watch` renders Runtime Events, never a mix of events and reports, never an auxiliary channel introducing information the capability did not declare. Interrupting a streaming command stops rendering; it never invokes a Runtime API capability the command did not explicitly request. There is no implicit `CancelExecution` unless such a capability exists.

## Error Model

A Runtime domain error surfaced by the Runtime API (`AdmissionRejected`, `AllocationDenied`, `ObjectNotFound`, …) is rendered to the terminal with the domain's own reason intact — never collapsed into a generic "command failed." A transport-level failure (connection lost, timeout) is rendered distinctly from a domain error, for the same reason `27-sdk.md` keeps them distinct: conflating "the request never reached Admission" with "Admission rejected the request" is a correctness bug in the CLI, not a Runtime API concern.

Exit codes translate Runtime outcomes into the command-line environment, never reinterpret them: a domain rejection and a transport failure are distinguishable by exit code, so scripts consuming the CLI can react to each correctly without parsing human-readable text.

## Technology Independence

The CLI's public behavior does not depend on whether the Runtime API is reached over gRPC, REST, or an embedded in-process call — a command's output is identical regardless of which adapter served it (`26-runtime-api.md`'s Technology Independence). Changing the underlying transport must never require changing a command's syntax, output, or exit code.

## Versioning & Compatibility

A CLI version tracks the Runtime API contract version it projects, never the Runtime's internal implementation — a new CLI release is required only when the Runtime API contract evolves (`26-runtime-api.md`'s Versioning & Stability), following it exactly as `27-sdk.md` already does.

A command's syntax and exit codes are part of the CLI's own contract with scripts and operators; breaking either is a breaking CLI change independent of whether the underlying Runtime API capability changed at all.

## Observability

The CLI may expose client-side observability (request latency as experienced by the operator, retry attempts, connection state) to help diagnose integration issues, without duplicating the Runtime API's own Observability (`26-runtime-api.md`) or the SDK's (`27-sdk.md`) — each layer observes only its own translation, never the layer beneath it.

## Anti-Patterns

Avoid: a command with no corresponding Runtime API capability, a command that changes the meaning of the capability it invokes, an implicit capability invocation behind a keystroke or signal, collapsing distinct domain errors into one generic failure message, a confirmation prompt substituting for authorization, a transport-specific detail leaking into command syntax or output, forcing the CLI through a specific SDK implementation.

## Review Checklist

Before adding a command ask: does a corresponding Runtime API capability already exist? Is it either a leaf command mapping to exactly one capability, or an explicit orchestration of existing capabilities? Does it distinguish domain errors from transport errors, with distinguishable exit codes? Does it hide the underlying transport completely? Does a confirmation prompt ever stand in for authorization?

## Principles

- The CLI projects Runtime API capabilities into human commands. It never projects Runtime internals.
- The CLI is a projection pattern with multiple implementations, never a single canonical executable.
- Commands invoke Runtime API capabilities, never Runtime domains directly.
- The CLI introduces no capability the Runtime API does not already expose.
- Every leaf command corresponds to exactly one Runtime API capability.
- Consumers compose around the Runtime API. They never depend on each other.
- Output formatting translates representation, never meaning. Exit codes translate outcomes, never reinterpret them.
- A confirmation prompt is a human safeguard, never a substitute for authorization.

## Motto

Project the contract. Speak the terminal. Change nothing in between.
