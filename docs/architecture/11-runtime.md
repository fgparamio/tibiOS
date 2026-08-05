# TibiOS Runtime Architecture

Version: 1.0

## Purpose

The Runtime is the heart of TibiOS. Everything executes through the Runtime. Applications never execute work directly — applications describe work, and the Runtime decides how, where, and when it executes.

## Vision

The Runtime transforms a collection of independent machines into a single logical computer. Applications should perceive one computer, not a cluster.

## Responsibilities

The Runtime is responsible for workload execution, scheduling, resource allocation, lifecycle management, communication, fault recovery, and observability.

The Runtime is not responsible for business logic.

## Core Abstraction: Workload

The fundamental execution unit is the Workload. There are no processes, jobs, or tasks in the public API — everything is a Workload. Examples: Rust function, AI inference, Actor, Service, Pipeline, Workflow, background task. The Runtime treats them uniformly.

## Runtime Goals

Maximize locality. Minimize communication. Isolate failures. Recover automatically. Remain observable. Scale horizontally.

## Resource Model

Resources are first-class objects (CPU, Memory, GPU, Disk, Network, Accelerators). The Runtime schedules Workloads according to resource availability (see `14-resource-model.md`).

## Ownership

Every Workload has one owner. Ownership determines scheduling, cancellation, recovery, and accounting.

## Lifecycle

```
Created
    ↓
Scheduled
    ↓
Running
    ↓
Completed  or  Failed
    ↓
Recovered (if applicable)
```

The lifecycle is explicit. Hidden states are forbidden.

> Note: this `WorkloadState` (Runtime-wide view) is distinct from the finer-grained "Execution Phase" a Worker tracks locally during its own execution (`Received → Prepared → Running → Completed/Failed`, see `18-worker-model.md`). They share the word "Running" but are two different state machines at two different layers — model them as two separate enums, not one.

## Scheduling

Scheduling is delegated: the Runtime requests scheduling, the Scheduler decides placement, the Runtime executes the decision.

## Communication

The Runtime communicates only through messages. Direct shared mutable state across nodes is forbidden.

## Fault Handling

Failure is part of execution. The Runtime detects crashed nodes, lost messages, stalled workloads, and unavailable resources. Recovery begins immediately.

## Observability

Every Workload has an identifier, owner, trace, metrics, lifecycle, and logs. Nothing executes invisibly.

## Security

The Runtime authenticates nodes, workloads, and messages. Execution is never anonymous.

## Extensibility

The Runtime is extensible through well-defined interfaces. Internal implementation details remain private.

## Public API

Applications interact with the Runtime through stable abstractions. The Runtime implementation may evolve without breaking applications.

## Anti-Patterns

Avoid exposing scheduler internals, Tokio, networking, storage engines, or synchronization primitives. The Runtime is an abstraction, not an implementation.

## Review Checklist

Before introducing a Runtime feature ask: does it simplify execution? Does it improve locality? Does it reduce communication? Does it preserve ownership? Does it improve observability? Does it scale? Can it recover automatically?

## Relationship

```
Runtime
      │
creates
      ▼
Execution Context
      │
contains
      ▼
Execution Channel
      │
assigned to
      ▼
Worker
      │
      ├──────────────┐
      ▼              ▼
Execution      Execution
 Events          Report
      │              │
      └──────┬───────┘
             ▼
          Runtime
```

## TibiOS Philosophy

Applications express intent. The Runtime owns execution. The Scheduler owns placement. Workers own computation. Storage owns persistence. Networking owns transport. Every component owns exactly one responsibility.

A Workload of kind `Inference` is delegated to a Worker — either `local-infer` (llama.cpp, in-process, lightweight path) or tibios-ray (the external AI Runtime, via the gRPC contract, heavy path). From the Runtime's perspective both are interchangeable Workers; the Runtime does not know or care whether a Worker is a local thread or a remote process across a socket.

## Engineering Motto

The Runtime is the operating system. Everything else is a workload.
