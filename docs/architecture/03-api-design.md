# TibiOS API Design Guidelines

Version: 1.1

## Purpose

This document defines how public APIs must be designed across all TibiOS crates.

Public APIs are long-term contracts. Implementation details may change. Public APIs should remain stable.

## Core Principles

A good API is simple, predictable, consistent, discoverable, and difficult to misuse.

The easiest way should also be the correct way.

## Stability

Public APIs should be treated as permanent. Adding methods is easy; removing methods is expensive. Avoid exposing implementation details.

## Minimal Surface Area

Expose the smallest possible API. Good APIs are intentionally small. Every public item has a maintenance cost.

## Explicitness

Avoid hidden behavior, implicit state, and surprising side effects. The caller should always understand what happens.

## Naming

Names should describe intent. Prefer verbs for functions.

Good: `cluster.connect()`, `node.start()`, `runtime.execute()`, `storage.persist()`

Avoid vague names: `do_it()`, `run()`, `handle()`, `process()`

## Constructors

Use `new()` only when there is a single obvious constructor. If multiple configurations exist, use descriptive constructors: `Cluster::local()`, `Cluster::remote()`, `Cluster::from_config(config)`.

## Builder Pattern

Use builders when there are many optional parameters.

```rust
let cluster = ClusterBuilder::new()
    .host(host)
    .port(port)
    .tls(true)
    .build()?;
```

Avoid constructors with many parameters.

## Parameter Count

Target 0–3 parameters. If more than four are needed, introduce a configuration struct.

## Ownership

APIs should make ownership obvious. Prefer borrowing whenever possible. Avoid forcing unnecessary clones.

## Return Types

Return concrete types whenever practical. Use trait objects only when dynamic dispatch is required. Avoid unnecessary boxing.

## Result and Option

Recoverable operations return `Result`. Never panic for expected failures.

```rust
pub fn connect(...) -> Result<Cluster>
```

Use `Option` only when absence is expected. Do not overload `Option` to hide errors — `Option<Node>` when the real reason is `NetworkError` is incorrect.

## Error Types

Every public error should explain what failed, why, and how to recover when possible. Prefer domain-specific errors.

## Generic Types

Use generics only when they improve usability. Avoid generic APIs created "just in case."

## Traits

Traits describe behavior and should be focused: `Persist`, `Load`, `Execute`. Avoid "God Traits" like `ClusterManagerEverything`.

## Async APIs

Async should be explicit: `async fn connect(...)`. Avoid hidden background work.

## Blocking APIs

Blocking APIs should clearly indicate blocking behavior: `read_blocking()`.

## Mutability

Prefer immutable APIs. Mutation should be intentional.

## State Machines

Model state with enums instead of booleans: `NodeState::Running`, not `is_running`/`is_started`/`is_ready`.

## Configuration

Configuration should be immutable after creation whenever possible. Use configuration structs. Avoid mutable global settings.

## Collections

Prefer slices over vectors: `&[Node]`. Avoid requiring ownership unnecessarily.

## Strings and Paths

Prefer `&str` over `String` when ownership is unnecessary. Prefer `impl AsRef<Path>` over `String` for paths.

## Documentation

Every public item must answer: what does it do, when should it be used, what errors can occur. Include examples whenever possible.

## Discoverability

Related methods belong together: `cluster.connect()`, `cluster.disconnect()`, `cluster.status()`, `cluster.nodes()`. Avoid scattering similar functionality.

## Side Effects

Functions should do exactly what their names imply. Avoid hidden network requests, disk writes, thread creation, or retries.

## Versioning

Breaking changes require strong justification. Deprecate before removing. Provide migration guidance.

## Testing

Every public API requires unit tests, integration tests, and documentation examples when useful.

## Never Expose Third-Party Dependencies

This applies beyond the specific "never expose Tokio types" rule below — no third-party dependency type may cross a public API boundary, in any TibiOS crate.

Avoid:

```rust
pub async fn start() -> tokio::task::JoinHandle<()>
```

Prefer:

```rust
pub async fn start() -> RuntimeHandle
```

Wrap the third-party type in a newtype owned by the crate before it crosses the public boundary. This is a general instance of "Ports belong to the language of the consumer, not the technology of the provider" (`02-project-structure.md`).

## TibiOS Rules

Public APIs must never expose Tokio types, internal scheduler types, internal networking implementation, internal storage engine details, or internal synchronization primitives.

The runtime may change. The public API should not.

## Anti-Patterns

Avoid: global mutable state, boolean parameter overload, hidden allocations, hidden threads, hidden networking, hidden retries, overly generic APIs, leaking implementation details, panicking on user input.

## API Review Checklist

Before exposing a public API ask:

- Is the name obvious?
- Is ownership clear?
- Is the API minimal?
- Is misuse difficult?
- Are errors descriptive?
- Is documentation complete?
- Can this evolve without breaking users?
- Does it hide implementation details, including third-party ones?

## Motto

Design APIs for the next ten years, not for today's implementation.
