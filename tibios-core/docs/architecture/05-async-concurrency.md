# TibiOS Async & Concurrency Guidelines

Version: 1.0

## Purpose

This document defines how asynchronous programming and concurrency must be implemented across TibiOS.

Concurrency is a design problem. Async is an implementation detail.

## Core Principles

Prefer ownership. Prefer message passing. Prefer immutable data. Avoid shared mutable state. Synchronization is the last resort.

## Runtime

Tokio is the default asynchronous runtime. Its use is an implementation detail — public APIs must never expose Tokio types (see `03-api-design.md`).

## Async Philosophy

Not every function should be async. Use async only when waiting for external resources: network, disk, timers, RPC, database.

CPU-bound work should not be async.

## Blocking Code

Never block inside an async task.

Forbidden: `std::thread::sleep(...)` → use `tokio::time::sleep(...)`.

Forbidden: `std::fs::read(...)` → prefer `tokio::fs::read(...)`.

## CPU Intensive Work

Move heavy computation away from async executors. Use `tokio::task::spawn_blocking(...)` only when necessary; long term, prefer dedicated worker pools.

> This is a hard requirement for `local-infer`: llama.cpp inference is CPU-bound and must never run directly on a Tokio task. It runs on a dedicated blocking thread pool. The Runtime-facing boundary is asynchronous. Internal implementations may be synchronous provided they never block the Runtime executor.

## Ownership

Async tasks own their data. Avoid unnecessary `Arc`. Avoid unnecessary cloning. Ownership should remain obvious.

## Shared State

Avoid shared mutable state. Preferred order: immutable data → message passing → actor ownership → `RwLock` → `Mutex`.

`Arc` is not free — use only when ownership must be shared. Avoid `Arc<Mutex<T>>` as the default design.

## Mutex / RwLock

`Mutex` indicates shared mutable state. Before introducing one, ask: can ownership eliminate this? Can a channel solve this? Can an actor own this?

`RwLock` only when reads greatly outnumber writes. Never replace good architecture with locks.

## Channels

Prefer channels over locks. Ownership becomes explicit; communication becomes observable.

## Actors

Actors own their state. Messages change state. External code never mutates actor state directly. Actors communicate through messages.

> This is the supervision pattern used for tibios-ray: tibios-core spawns and supervises tibios-ray as a subprocess (start/health-check/restart), the same ownership model as any other actor-owned task.

## Tasks

Tasks should be independent. Avoid implicit dependencies. Tasks should be cancellable and clean up after cancellation.

## Cancellation

Cancellation is normal. Every async task must tolerate cancellation. Avoid leaking resources.

## Timeouts

Every network operation requires a timeout. Never wait forever. Timeout duration belongs in configuration — never hardcoded.

## Retries

Retries require limits, exponential backoff, and jitter. Never retry forever.

## Select / Join

`tokio::select!` should remain readable — if it grows too large, split responsibilities. Use `join` only when operations are truly independent.

## Spawning

Spawn only when ownership is clear. Avoid uncontrolled background tasks. Every spawned task should have an owner who created it, who stops it, and who monitors it.

## Backpressure

Every queue requires limits. Unbounded queues are forbidden unless explicitly justified. Dropped messages must be intentional.

> The Execution Channel (`18-worker-model.md`) is implemented as a bounded `tokio::sync::mpsc` for exactly this reason — an unbounded channel between a fast producer (e.g. token generation) and a slow consumer would leak memory.

## Deadlocks and Starvation

Design to eliminate deadlocks; do not rely on lock ordering — reduce locking instead. Long-running tasks must periodically yield; schedulers should remain responsive.

## Fairness

Avoid designs where one task can monopolize execution. Small tasks scale better.

## Async Traits

Prefer `async_trait` only when necessary. Monitor compiler evolution; native async traits are preferred when stable and suitable.

## Streams

Use streams for unbounded asynchronous data. Avoid collecting everything into memory — process incrementally.

## Networking / Distributed Systems

Every network request must assume timeout, retry, cancellation, duplicate delivery, and out-of-order delivery. Nodes disappear, messages are delayed/duplicated, networks partition, clocks drift. Design accordingly.

## Testing

Concurrency requires stress tests: cancellation, retries, races, shutdown, backpressure, node loss.

## Observability

Every async subsystem should expose metrics, tracing, task lifecycle, queue depth, and latency. Never debug distributed systems blindly.

## Anti-Patterns

Avoid: `Arc<Mutex<T>>` everywhere, fire-and-forget tasks, infinite retries, infinite queues, hidden background threads, blocking async executors, global mutable state, uncontrolled spawning.

## Review Checklist

Before merging ask:

- Can ownership replace synchronization?
- Can channels replace locks?
- Is cancellation safe?
- Are retries bounded?
- Are queues bounded?
- Are tasks observable?
- Can shutdown complete cleanly?
- Are timeouts configurable?

## TibiOS Rules

The scheduler owns scheduling. Workers own execution. Actors own state. Messages own communication.

Ownership is the architecture. Synchronization is the exception.

## Motto

Move ownership. Not locks.
