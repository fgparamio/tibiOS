# TibiOS Rust Style Guide

Version: 1.1

## Purpose

This document defines the mandatory Rust coding style for every crate in TibiOS.

Consistency is more important than personal preference.

Always follow official Rust conventions unless this guide explicitly overrides them.

## Formatting

**Principle**: code must have a uniform, automatic format. Formatting is never discussed in code reviews — never manually align code.

**Current toolchain**: `rustfmt` / `cargo fmt`.

> This split is deliberate: if the formatter or its configuration changes in the future, only the toolchain line needs updating — the principle above it does not.

## Clippy

Every Pull Request must pass:

```bash
cargo clippy -- -D warnings
```

Warnings are treated as errors. If a lint is disabled, the reason must be documented.

## Naming

### Crates

Use `snake_case`.

Good: `tibios_runtime`, `tibios_scheduler`, `tibios_storage`

Bad: `TibiOSRuntime`, `Runtime`, `runtime_lib`

### Modules

Use `snake_case`: `scheduler.rs`, `cluster.rs`, `network.rs`

### Functions

Use `snake_case`: `create_cluster()`, `send_message()`, `allocate_memory()`

### Variables

Use descriptive names: `worker_id`, `message_queue`, `connection_timeout`

Avoid abbreviations (`wid`, `msg`, `conn`) — exception: very common mathematical names (`x`, `y`, `i`, `j`).

### Constants

Use `SCREAMING_SNAKE_CASE`: `MAX_CONNECTIONS`, `DEFAULT_TIMEOUT`, `BUFFER_SIZE`

### Types

Use `PascalCase`: `Cluster`, `Scheduler`, `NodeManager`, `ObjectStore`

### Traits

Traits should describe capabilities: `Serialize`, `Schedule`, `Persist`, `Execute`

Avoid `I` prefixes (`IScheduler`, `IStorage`).

### Enums

Prefer descriptive variants:

```rust
enum NodeState {
    Starting,
    Running,
    Stopping,
    Offline,
}
```

Avoid `State1`, `State2`.

## File Organization

Preferred order: module documentation, imports, constants, type aliases, structs, enums, traits, implementations, tests.

## Imports

Always group imports:

```rust
use std::sync::Arc;

use tokio::sync::Mutex;

use crate::cluster::Node;
```

Avoid long import lists.

## Functions

Prefer short functions. Target: 20–40 lines. Functions over 80 lines should usually be split.

## Parameters

Prefer small parameter lists. If more than four parameters are required, introduce a configuration struct.

Good: `ClusterConfig`. Instead of `create_cluster(host, port, timeout, retries, secure, compression)`.

## Match

Prefer exhaustive match statements. Never use `_` if explicit variants improve readability.

## Option and Result

Never ignore errors.

Good: `let config = load_config()?;`

Bad: `let _ = load_config();`

## unwrap()

Forbidden in production code. Allowed: tests, examples, prototypes.

Prefer `?`, `ok_or()`, `map_err()`.

## panic!

Avoid panic. Recover whenever possible. Panics should indicate programming errors, not runtime failures.

## Comments

Good code should explain itself. Comments explain WHY, not WHAT.

Good: `// We retry because nodes may still be joining the cluster.`

Bad: `// Increment i` / `i += 1;`

## Documentation

Every public API must have Rustdoc:

```rust
/// Starts the distributed scheduler.
///
/// Returns an error if the cluster
/// configuration is invalid.
```

## Traits

Prefer small traits: `Persist`, `Load`, `Execute`. Avoid huge traits.

## Structs

Prefer immutable structs. Expose behavior. Avoid exposing fields unless necessary.

## Visibility

Everything is private by default. Only expose APIs intentionally. Prefer `pub(crate)` over `pub` whenever possible.

## Modules

Large files should become modules. Rule of thumb: 500 lines maximum, 1000 lines is unacceptable.

## Nesting

Avoid deep nesting. Prefer early returns.

Good:

```rust
if !is_valid {
    return Err(Error::InvalidInput);
}

process();
```

## Allocation

Avoid unnecessary allocations. Prefer borrowing. Prefer iterators. Avoid cloning by default.

## Async

Do not block inside async functions. Avoid `std::thread::sleep()` — use `tokio::time::sleep()`.

## Testing

Tests belong near the code they test. Integration tests belong inside `tests/`.

## Magic Numbers

Avoid magic numbers. Prefer constants: `const DEFAULT_PORT: u16 = 5000;`

## TODO vs FIXME

TibiOS distinguishes two categories of in-code annotation, each with a different lifecycle — adapted from, not copied from, the `rustc` development guide.

**`TODO(issue)`** represents short-term planned work. It must be tied to a context or issue reference, and is expected to be resolved before that part of the code is considered stable.

**`FIXME(issue)`** represents a known limitation or deliberately accepted technical debt. It is not expected to disappear before merge — it documents a conscious tradeoff that is being carried forward on purpose.

Good:

```rust
// TODO(#142): Replace temporary scheduler after distributed version is complete.

// FIXME(#187): Allocation retry has no backoff cap yet; acceptable for MVP scheduling load.
```

Neither annotation is a substitute for tracking real work in an issue — the reference is mandatory, not optional.

## Commit & PR Hygiene

These are engineering rules, not Git mechanics — adapted from the `rustc` development guide, and complementary to the `work-unit-commits` convention.

- Separate refactoring from behavioral changes. Never mix a rename/move with a logic change in the same commit.
- Prefer small, coherent commits over large ones — easier to review, easier to revert, easier to understand.
- Never mix mechanical changes (formatting, renames) with behavioral changes in the same commit.
- Each commit should leave the crate in a valid, compilable state whenever practical.
- Prefer `rebase` to keep a linear history; avoid merge commits within a feature branch.

## Code Review Checklist

Before committing: `cargo fmt`, `cargo clippy`, `cargo test`.

Ask yourself:

- Is ownership obvious?
- Is cloning necessary?
- Can this function be smaller?
- Can names be clearer?
- Is the API minimal?
- Are errors handled?
- Is documentation complete?

## Motto

Readable Rust is fast Rust.

Consistent Rust is maintainable Rust.
