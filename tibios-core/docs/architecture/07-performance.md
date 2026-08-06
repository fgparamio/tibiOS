# TibiOS Performance Guidelines

Version: 1.0

## Purpose

Performance is a feature, achieved through architecture, measurement, and simplicity. Never optimize blindly.

## Core Principles (in order)

Correctness → Safety → Simplicity → Performance. Never change this order.

## Measure First

Never optimize code that has not been measured. Every optimization should answer: what is slow, how slow, why, and how was improvement measured?

Use benchmarks — never trust intuition. Humans are poor performance profilers.

## Algorithm First

Algorithmic improvements are almost always more valuable than micro-optimizations. Prefer O(log n) over O(n), O(n) over O(n²).

## Architecture Beats Micro-Optimizations

A better architecture is worth more than faster code: reduce communication, synchronization, allocations, and copying.

## Zero-Cost Abstractions

Rust abstractions should disappear after compilation. Avoid runtime overhead created only for convenience.

## Allocation, Cloning, Borrowing, Copying

Heap allocation is expensive — allocate intentionally, avoid it inside hot paths. Clone is explicit, but not free: before cloning, ask if ownership can move, borrowing can solve it, or lifetimes can express the relationship. Prefer `&str` over `String`, `&[T]` over `Vec<T>`. Every copy should have a reason.

## Collections and Hashing

Choose the correct collection (`Vec`, `HashMap`, `BTreeMap`, `HashSet`, `BinaryHeap`) by measurement, not habit. Hashing is not free — avoid unnecessary hashing, cache when beneficial.

## Strings and Iterators

Avoid repeated allocations and repeated formatting; reuse buffers when practical. Prefer iterators — they are expressive and often optimize well. Avoid indexed loops unless they improve clarity or performance.

## Dynamic Dispatch / Monomorphization

Prefer static dispatch. Use trait objects only when runtime polymorphism is required. Generic code increases binary size — use generics intentionally and measure compile time impact.

## Async Performance

Avoid unnecessary task spawning and excessive context switching. Avoid tiny async tasks that immediately await each other.

## Synchronization

Locks reduce scalability. Prefer ownership, actors, channels. Synchronization is the exception.

## Cache Locality

Sequential memory access is generally faster. Group related data together. Avoid pointer-heavy structures without justification. Avoid multiple threads modifying nearby memory (false sharing).

## Branch Prediction / Hot Paths

Keep hot paths predictable — avoid deeply nested conditionals, logging, allocation, formatting, and unnecessary validation on them. Cold paths don't need optimization — readability wins there.

## Networking

Minimize round trips. Batch operations when appropriate. Compress only when measurements justify it.

## Serialization

Avoid serializing data repeatedly. Prefer binary formats for internal communication. Measure before introducing compression.

> This validates the protobuf/gRPC choice already made for the core↔ray contract — binary, not JSON.

## Disk I/O

Avoid synchronous disk access inside hot paths. Batch writes when safe. Prefer append-only patterns when appropriate.

## Distributed Systems

Network latency dominates CPU latency. Optimize communication before optimizing computation — reducing one network hop often provides greater benefit than micro-optimizing a function.

## Logging / Profiling

Logging belongs outside hot paths whenever possible; prefer structured logging; avoid string formatting when logging is disabled. Use profilers regularly — never optimize based on assumptions. Keep benchmark history.

## Compile Time / Memory Usage

Compile time matters — avoid unnecessary dependencies, macros, and deeply nested generic abstractions. Unused memory is waste; Rust is not exempt from memory discipline.

## Unsafe

Unsafe does not automatically improve performance. Use unsafe only when measurement proves its value — every unsafe optimization requires benchmarks.

> This directly applies to the `local-infer` crate's choice of `llama.cpp` bindings (unsafe FFI) over `candle` (pure Rust): the choice must eventually be validated with real benchmarks, not intuition alone, once code exists.

## Review Checklist

Before optimizing ask: was it measured? Is the algorithm appropriate? Can ownership reduce allocations? Can borrowing eliminate copies? Is synchronization necessary? Is networking the real bottleneck? Is readability preserved?

## Anti-Patterns

Avoid: premature optimization, unnecessary cloning/allocation, excessive locking, repeated serialization, unnecessary async tasks, optimizing cold code, benchmarking in debug mode.

## TibiOS Rules

The fastest message is the one never sent. The fastest allocation is the one never made. The fastest lock is the one never acquired. The fastest network request is the one never needed.

Architecture determines performance.

## Motto

Measure. Understand. Then optimize.
