# TibiOS Error Handling Guidelines

Version: 1.1

## Purpose

Errors are part of the public API. Error handling must be explicit, informative, and predictable. Recoverable failures must never terminate the process.

## Core Principles

Errors are expected. Panics are exceptional. Never hide failures. Never ignore failures. Every error should help the next engineer solve the problem.

## Result and Option

Recoverable operations return `Result<T, E>`. Never return sentinel values or invalid objects.

Use `Option` only when absence is expected (cache miss, optional configuration, missing parent node) — never for real errors (database failure, network timeout, permission denied).

## Panic

`panic!` represents a programming bug, not an error handling strategy.

Good uses: impossible states, broken invariants, internal logic errors.

Bad uses: file not found, network disconnected, invalid user input, configuration problems.

## unwrap() / expect()

`unwrap()` is forbidden in production code — allowed only in unit tests, examples, prototypes, and benchmarking code.

`expect()` is slightly better but still forbidden in production, except when failure is literally impossible.

Prefer `?` over manual `match` unless additional context is required.

## Error Context

Always add context: what failed, where, why.

In a library crate using `thiserror`, context is carried via enum variant fields or `#[source]`/`#[from]`, wrapping the lower-level error — not via `.context()`, which is an `anyhow`/`eyre` method and only applies at the application/binary layer where `anyhow` is permitted.

## Domain Errors

Each crate owns its own error type: `SchedulerError`, `StorageError`, `NetworkError`, `RuntimeError`. Avoid a single `ApplicationError` for everything.

Library crates use `thiserror` for typed errors:

```rust
#[derive(Debug, Error)]
pub enum StorageError {
    #[error("database connection failed")]
    ConnectionFailed,

    #[error("object not found")]
    NotFound,
}
```

Applications may use `anyhow`. Libraries should generally avoid exposing `anyhow::Error` — public APIs deserve typed errors.

## Error Messages

Error messages begin with lowercase, no punctuation: `connection refused`, `node not found`, `invalid cluster id` — not `Connection Refused!` or `Something went wrong.`

## Error Variants

Prefer meaningful variants: `InvalidNodeId`, `PermissionDenied`, `ConnectionTimeout`, `AuthenticationFailed` — avoid `Unknown`, `GeneralFailure`, `Error`.

## Preserve Context

Never discard useful information: `Err(StorageError::OpenFile(path))`, not `Err(StorageError::Failed)`.

## Logging

Log errors once. Never log and return repeatedly. Avoid duplicate logs.

## Retry

Retry only when appropriate: temporary network failures, transient storage failures, leader election.

Never retry: invalid input, authentication failures, corrupted data.

## Error Conversion

Use `From`/`Into` to simplify propagation. Avoid manual conversions everywhere.

## Error Hierarchy

Low-level crates expose detailed errors. High-level crates may aggregate them. Never lose information.

## Async Errors

Cancellation is not necessarily an error. Timeouts are different from cancellations — treat them separately.

## Distributed Systems

Every network operation can fail. Every node can disappear. Every connection can time out. Every message can arrive twice or late. Assume failure.

## Security

Never expose passwords, API keys, tokens, encryption keys, or internal secrets inside error messages.

## User vs Internal Errors

Users receive understandable messages. Logs receive detailed diagnostics. Separate both concerns.

## Testing

Every custom error type requires tests: formatting, conversion, propagation, and serialization if applicable.

## Documentation

Every public error should explain when it occurs, what it means, and how callers should react.

## Error Classification by Behavior, Not Only Domain

A domain error type (`StorageError`, `NetworkError`, ...) answers *what* failed. For distributed systems, the Runtime also needs to know *how to react* — and that classification is orthogonal to domain:

- **Transient** → retry (`Timeout`, `NetworkPartition`, `LeaderElection`)
- **Permanent** → return the error to the caller (`InvalidInput`, `PermissionDenied`, `UnsupportedVersion`)
- **Fatal** → isolate the node, alert, or begin recovery (`CorruptedStorage`, `BrokenInvariant`, `DataLoss`)

This is implemented as a small trait every domain error implements:

```rust
pub enum ErrorClass {
    Transient,
    Permanent,
    Fatal,
}

pub trait Classify {
    fn classify(&self) -> ErrorClass;
}

impl Classify for StorageError {
    fn classify(&self) -> ErrorClass {
        match self {
            StorageError::ConnectionFailed => ErrorClass::Transient,
            StorageError::NotFound => ErrorClass::Permanent,
            // ...
        }
    }
}
```

`ErrorClass` and the `Classify` trait live in `runtime-primitives` (per `02-project-structure.md`) — they are universal, domain-independent, and no domain "owns" a contract every other domain must implement.

## Anti-Patterns

Avoid: `unwrap()`, `expect()`, `panic!` for runtime failures, `String` as an error type, `bool` as an error indicator, swallowing errors, generic "Unknown error".

## Review Checklist

Before merging ask:

- Is every error recoverable when appropriate?
- Is context preserved?
- Is panic avoided?
- Is `unwrap` absent?
- Are secrets protected?
- Is the error actionable?
- Does the caller know what to do?
- Is it classified (`Transient`/`Permanent`/`Fatal`) where the Runtime needs to react automatically?

## TibiOS Rules

Every distributed operation must assume failure. Every storage operation must assume corruption is possible. Every network operation must assume partitions. Every scheduler operation must assume node loss.

Design errors first. Success is the easy path.

## Motto

A good error tells the truth. A great error tells you how to fix it.
