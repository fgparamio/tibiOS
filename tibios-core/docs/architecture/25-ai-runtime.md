# TibiOS AI Runtime

Version: 1.0

## Purpose

The AI Runtime is not a second Runtime. It answers exactly one architectural question: **how does AI workload execution use TibiOS's general infrastructure without creating parallel mechanisms?**

The AI Runtime introduces no new architectural primitives. It composes the Runtime's existing primitives — Object (`13-object-model.md`), Resource (`14-resource-model.md`), Scheduling (`16-scheduling-engine.md`), Allocation (`15-allocation-model.md`), Worker (`18-worker-model.md`), Object Store (`23-object-store.md`), Replication (`24-replication.md`) — to execute AI workloads. Every question this document answers has already been answered generically; this document only shows where AI concepts map onto that existing answer.

This document does not explain LLMs, GPUs, or inference algorithms. It explains how inference, training, and multi-model execution are ordinary consequences of the Runtime core, not new subsystems.

## Ownership

The AI Runtime currently owns no crate of its own, because it introduces no architectural language distinct from the Runtime domains it composes. Should such a language emerge in the future, it would justify its own domain under the same architectural principles as every other Runtime crate (`02-project-structure.md`'s Architecture Review Checklist) — this is not an exception carved out for AI, it is the same rule applied to it.

- AI Object types (`Model`, `Tokenizer`, `Embedding`, `Prompt`, `Conversation Context`, `Tensor`, `Inference Result`) belong to `runtime-object` (`13-object-model.md`).
- AI-specific capability (CUDA/Metal/ROCm, VRAM, Tensor Cache) belongs to `runtime-scheduler` (`14-resource-model.md`).
- AI Worker implementations (`local-infer`, `tibios-ray`) belong to `runtime-worker` (`18-worker-model.md`).

There is no routing component that "decides" between `local-infer` and `tibios-ray` for a given inference request — that decision is already made, generically, by Scheduling's Capability Filter (`16-scheduling-engine.md`) matching required capability against available capability. The AI Runtime does not add a new decision point; it relies on one that already exists.

## Core Principles

- The AI Runtime introduces no new architectural primitives. It composes the Runtime's existing primitives to execute AI workloads.
- The AI Runtime is an orchestration domain, not an infrastructure domain. It specializes existing Runtime capabilities; it introduces no parallel infrastructure.
- `local-infer` and `tibios-ray` implement the same Worker contract. The Runtime does not distinguish between them.
- Any AI concept that cannot be expressed as an Object, a Resource, a Worker, or a Workload does not belong in this document.

## AI Objects (specialization of the Object Model)

The AI Runtime introduces no new object semantics. `Model`, `Tokenizer`, `Embedding`, `Prompt`, `Conversation Context`, Tensor artifacts, and Inference Results are ordinary Objects as already defined in `13-object-model.md`'s AI Objects section.

The Object Model already resolves every AI-specific identity question. A Model Artifact is a Content Object (immutable, hash-addressed — a rollout is a new hash, never a mutation); a Model Reference is a Logical Object (mutable, versioned — a rollout is a new `ObjectVersion` pointing to the new hash). This is exactly `13-object-model.md`'s existing Model Reference example, not a new one invented for this document.

A Conversation Context is a Logical Object like any other — it evolves (new turns) through new versions or through its own Object Lifecycle Log entries, never through in-place mutation, exactly as `13-object-model.md`'s Object Lifecycle already requires. Its persistence strategy is therefore identical to any other Logical Object and requires no AI-specific storage mechanism.

## AI Workers (specialization of the Worker Model)

`local-infer` and `tibios-ray` implement the same Worker contract (`18-worker-model.md`). The Runtime distinguishes only capabilities, never implementations — it knows CUDA, Metal, and ROCm as typed capability (`14-resource-model.md`); it does not know, and never needs to know, llama.cpp, Ray, vLLM, or TensorRT.

`local-infer` runs in-process, CPU-bound, on a dedicated blocking thread pool (`18-worker-model.md`, `05-async-concurrency.md`). `tibios-ray` runs as an external process, reached over the existing gRPC contract. Neither fact is visible above the Worker abstraction. Choosing between them is not an AI Runtime decision — it is whichever Worker implementation is registered and capability-matched on the Node that Scheduling selects (`16-scheduling-engine.md`).

A multi-gigabyte model resident in a Worker's memory is a cache of the canonical Model Object (`13-object-model.md`'s Caching), never Worker-owned state — this is the existing resolution that already lets a Worker remain "stateless" despite holding a loaded model; the AI Runtime does not need a new one.

## AI Execution Models

TibiOS's four generic execution patterns (`18-worker-model.md`: Batch, Streaming, Long-running Service, Pipeline) already cover every AI execution shape without extension:

- A single-shot completion is **Batch** — one Execution Report, no intermediate events beyond the final `OutputChunk`.
- Token-by-token generation is **Streaming** — a sequence of `OutputChunk` Execution Events over the existing Execution Channel, exactly the mechanism already defined for any streaming Worker.
- A resident inference server accepting many requests is a **Long-running Service** — the same pattern already used for any always-on Worker.
- A multi-stage pipeline (retrieval → generation → post-processing) is **Pipeline** — intermediate results followed by a final one, already modeled generically.

Inference does not introduce a fifth execution model; it is merely another specialization of the existing four. No new execution pattern is required. Any AI workload that appears not to fit one of these four should be treated as a signal to re-examine the workload, not as a reason to add a fifth pattern.

## Model Resolution

Resolving a Model Reference to its executable bytes is Object Resolution (`23-object-store.md`) with no AI-specific step in between:

```
ModelReference (ObjectId + ObjectVersion)
        │
        ▼
   Object Store
        │
        ▼
ContentHash of current Model Artifact
        │
        ▼
   Object Store: does a Physical Replica exist locally?
```

The Object Store answers this exactly as it would for any other Logical Object → Content Object resolution. Nothing about "this is a Model" changes the mechanism.

## Model Distribution

If no local Physical Replica exists, resolution falls through to Replication (`24-replication.md`), unchanged: Pull the Content Object from any node that holds it, authorized by Trust if crossing a trust island.

This is where Replication Policy earns its keep for AI specifically: a `CapabilityAffinity(GPU)` or `PopularityWeighted` policy can pre-position a frequently used Model Artifact near GPU-capable nodes before any Worker asks for it — exactly the example already anticipated in `24-replication.md`. Without such a policy, Pull alone still guarantees correctness; a cold node simply pays the first-fetch latency once. Model distribution is therefore a property of Content Objects, not of AI itself.

## Inference Pipeline

An inference request produces no new pipeline. It is the Runtime Pipeline (`11-runtime.md`) with AI-shaped Objects flowing through it:

```
Client → Admission → Scheduling → Allocation → Execution Context → Worker → Execution Events → Execution Report
```

- **Admission** admits an Inference Workload exactly as it would any other Workload — no AI-specific eligibility rule exists at this layer.
- **Scheduling**'s Capability Filter matches the Workload's declared capability requirement (e.g. "needs 12GB CUDA") against Cluster Snapshot Resources (`14-resource-model.md`, `16-scheduling-engine.md`) — this is the entire "GPU scheduling" story; nothing else is required.
- **Allocation** commits capacity exactly as for any Workload (`15-allocation-model.md`).
- The **Execution Context** carries a resolved Model reference (already a Content Object, already pulled if needed — knowledge plane) and an Allocation Contract (work plane), per `24-replication.md`'s knowledge/work plane distinction.
- The **Worker** (`local-infer` or `tibios-ray`) executes, streaming `OutputChunk` events, then produces an Execution Report.

No stage of this pipeline required modification to serve inference. Inference is therefore a specialization of the Runtime Pipeline, not a parallel pipeline.

## Training Pipeline (future)

Training follows the same pipeline shape as inference — Admission, Scheduling, Allocation, Worker execution, Execution Report — with two observable differences: longer-running execution (Long-running Service or Pipeline pattern) and Checkpoint-producing Execution Events (`18-worker-model.md`'s Checkpointing, already modeled as a Worker capability). This document does not elaborate further; Phase 1 does not require it, and nothing here suggests the Runtime Pipeline would need to change when it does.

## Multi-Model Execution

Running multiple models concurrently — for routing, ensembles, or agentic tool use — is multiple independent Workloads, each independently admitted, scheduled, allocated, and executed. There is no "multi-model" primitive: it is simply what already happens when more than one Workload happens to reference AI Objects at the same time. The Runtime never reasons about "models"; it reasons about Workloads and Objects. Multi-model execution emerges naturally when multiple Workloads happen to consume AI Objects concurrently. Coordinating their results (e.g. an ensemble combining outputs) is Pipeline-pattern composition (`18-worker-model.md`), not a new Runtime mechanism.

## Relationship with Resource Model

Every AI capability requirement — GPU presence, CUDA vs Metal vs ROCm, VRAM size, Tensor Cache pressure — is expressed entirely through `14-resource-model.md`'s existing Capability vs Capacity model. There is no AI-specific resource type. A 24GB VRAM requirement for a large model and a 4-core CPU requirement for a batch job are the same kind of fact to the Scheduler: typed capability plus scalar capacity, filtered then scored (`16-scheduling-engine.md`). This is the entire "GPU scheduling" story — Resource Model and Capability Filter, nothing else.

## Relationship with Worker

`local-infer` and `tibios-ray` are Worker implementations exactly as defined in `18-worker-model.md` — nothing about this document changes what a Worker is, what an Execution Context contains, or how Execution Events and Execution Reports flow. The AI Runtime relies entirely on the Worker abstraction already being general enough to host an inference engine; it does not extend that abstraction. Any future AI execution engine participates in the Runtime by implementing the Worker contract, never by introducing a parallel execution abstraction.

## Observability

Execution Events and Execution Reports may carry AI-specific metrics such as tokens/second, time-to-first-token, or context window utilization. These extend the payload, not the observability mechanism.

## Anti-Patterns

Avoid: an "AI Scheduler" distinct from the Scheduling Engine, an "AI Storage" or "Model Registry" distinct from the Object Store, a fifth execution pattern for inference, a routing component choosing between Worker implementations, treating a Model as anything other than an ordinary Object, treating GPU capability as anything other than an ordinary Resource capability, introducing a `runtime-ai` crate before an architectural language justifies it.

## Review Checklist

Before adding AI-specific behavior ask: can this be expressed as an Object, a Resource, a Worker, or a Workload? Does it require a new execution pattern, or does it fit Batch/Streaming/Long-running Service/Pipeline? Does it require a new decision point, or does Scheduling's Capability Filter already answer it? Would the Runtime architecture remain complete if this AI-specific abstraction disappeared?

## Principles

- The AI Runtime introduces no new architectural primitives. It composes the Runtime's existing primitives to execute AI workloads.
- AI is a workload specialization, not a Runtime specialization.
- The Runtime distinguishes only capabilities, never implementations.
- Model distribution is a property of Content Objects, not of AI itself.
- Inference is a specialization of the Runtime Pipeline, not a parallel pipeline.
- The Runtime never reasons about "models"; it reasons about Workloads and Objects.

## Motto

No new architecture. Only new Workloads.
