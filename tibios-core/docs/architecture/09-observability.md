# TibiOS Observability Guidelines

Version: 1.0

## Purpose

A distributed system that cannot be observed cannot be trusted. Observability is a first-class architectural concern — every subsystem must expose enough information to understand its behavior without modifying the code.

## Core Principles

Measure everything that matters. Log only what is useful. Trace requests across the entire system. Every important event should be observable.

## The Three Pillars

Metrics, Logs, and Traces. These complement each other — none replaces the others.

**Metrics** answer "what is happening?" — numeric, cheap, continuous, aggregatable. Examples: CPU usage, memory usage, task latency, queue depth, active nodes, scheduler utilization, network throughput.

**Logs** answer "what happened?" — events, not metrics, not traces. Every log should have operational value.

**Traces** answer "why did this request behave this way?" — following work across runtime, scheduler, networking, storage, AI execution.

## Recommended Stack

`tracing` (maintained by the Tokio team, propagates context natively across `.await` points) for structured logs and spans, plus `tracing-opentelemetry` for exporting traces.

## Structured Logging

Never log plain text only — prefer structured fields:

```
event=node_connected node_id=node-17 cluster=production latency_ms=12
```

## Log Levels

`ERROR` — system cannot complete requested work. `WARN` — unexpected but recoverable. `INFO` — important operational events. `DEBUG` — useful during development. `TRACE` — very detailed execution information.

## Logging Rules

Log decisions, not implementation details. Avoid repetitive logs and logging inside hot loops.

## Correlation IDs

Every distributed request receives a correlation identifier, propagated across RPC, queues, actors, workers, and storage operations — enabling complete trace reconstruction.

> This correlation ID must cross the gRPC boundary between tibios-core and tibios-ray (via metadata, W3C traceparent style) — otherwise observability is lost exactly at the Rust↔Python crossing, which is likely where it is needed most.

## Metrics Design

Metrics should have stable names, stable units, and clear ownership. Use explicit units (milliseconds, bytes, seconds, requests, tasks) — never ambiguous values.

## Cardinality

Avoid high-cardinality metrics as labels (`user_id`, `session_id`, `request_uuid`). Prefer `node_type`, `scheduler`, `operation`, `region`.

## Health Checks

Every major component exposes health information: alive, ready, degraded. Health is not binary.

## Resource Monitoring

Every node should expose CPU, memory, disk, network, task count, and queue depth. Operators should never guess system health.

## Domain-Specific Metrics

**Scheduler**: pending/running/completed/failed tasks, average scheduling latency, worker utilization.

**Storage**: reads, writes, latency, cache hit ratio, replication status, available capacity.

**Networking**: packets, bytes, retries, dropped messages, connection failures, latency distribution.

**AI**: inference latency, tokens generated, model load time, GPU utilization, memory usage, request queue depth.

## Tracing

Every distributed operation creates spans — scheduling, networking, storage, execution, serialization. Nested spans should reflect ownership.

## Error Observability

Errors should include correlation ID, operation, component, and timestamp. Avoid anonymous failures.

## Dashboards

Dashboards answer operational questions — they should not mirror implementation. Organize around cluster health, scheduler, storage, networking, AI runtime.

## Alerts

Alert on symptoms, not individual events: queue growing continuously, latency increasing, node unavailable, replication behind. Avoid alert fatigue.

## Performance Impact

Observability must be lightweight — monitoring should never dominate execution time. Measure observability overhead.

## Privacy

Never emit secrets, credentials, personal information, or encryption keys. Observability must respect security rules.

## Testing

Observability is tested: metrics emitted, traces linked, logs formatted, correlation propagation. Broken observability is a production issue.

## Documentation

Every subsystem documents its exposed metrics, log events, trace spans, and alert recommendations. Operators should not reverse-engineer telemetry.

## Anti-Patterns

Avoid: logging everything, logging nothing, high-cardinality metrics, inconsistent names, missing correlation IDs, dashboards without purpose, alerts for every warning.

## Review Checklist

Before merging ask: can operators diagnose failures? Are metrics meaningful? Are logs actionable? Are traces complete? Are names consistent? Is overhead acceptable? Are secrets protected?

## TibiOS Rules

Every task is observable. Every message is traceable. Every node reports health. Every scheduler decision can be explained. Every production incident must leave enough evidence to reconstruct what happened.

Observability is part of the runtime, not an optional feature.

## Motto

If you cannot observe it, you cannot operate it.
