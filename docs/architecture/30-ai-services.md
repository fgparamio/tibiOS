# TibiOS AI Services

Version: 1.0

## Purpose

AI Services introduces no new architecture. It composes existing Runtime concepts: Service Objects (`13-object-model.md`), Long-running Service Workers (`18-worker-model.md`), AI Runtime specialization (`25-ai-runtime.md`), and the Runtime API (`26-runtime-api.md`), to expose reusable AI capabilities.

`25-ai-runtime.md` answered how the Runtime executes AI. This document answers a different question: **how is AI offered as a standing, consumable capability of the Runtime — something a consumer can call repeatedly, addressed by identity, rather than a single Workload submitted once?**

This document does not talk about models, Workers, GPU scheduling, replication, or object resolution again — those are closed (`13`–`29`). It does not talk about embeddings, agents, RAG, or tools as architectural concepts — per `25-ai-runtime.md`'s own discipline, those are Workload or Object types, not domains. An AI Service is not a model, not a Worker, and not a Runtime.

## Ownership

AI Services owns no crate of its own. Like `25-ai-runtime.md`, this document introduces no architectural language requiring an independent domain. It composes existing Runtime concepts:

- Service Objects (`13-object-model.md`)
- Long-running Service Workers (`18-worker-model.md`)
- AI Runtime specialization (`25-ai-runtime.md`)
- Runtime API operations (`26-runtime-api.md`)
- Deployment (`29-deployment.md`)

If a future AI Service pattern cannot be expressed through these five, that is evidence a genuinely new architectural question has appeared — and the answer is a new document, not logic quietly added here.

## Core Principles

- AI Services introduces no new architectural primitives.
- An AI Service is a Service Object (`13`) whose workload happens to perform AI inference, generation, classification, or similar tasks.
- An AI Service executes as a Long-running Service or Pipeline (`18`), never a new execution pattern.
- An AI Service is composed from existing Workloads. Composition is orchestration, never a new execution mechanism.
- AI Services defines reusable AI capabilities, never reusable AI infrastructure.
- If this document cannot be expressed as a composition of `13`, `18`, `25`, `26`, and `29`, the gap belongs in one of those documents — not here.

## Service Definition

An AI Service is not a distinct kind of Object. It is a Service Object (`13-object-model.md`) whose behavior happens to perform AI tasks — nothing about its identity, versioning, or lifecycle differs from any other Service Object. It has a `ServiceId`, an owner, a configuration (which Model Reference(s) it uses, which capability requirements it declares), and a set of interfaces it accepts requests through.

An AI Service's configuration references existing Objects — Model References, Prompt Templates, Conversation Context schemas (`13-object-model.md`'s AI Objects) — it never embeds them, for the same reason a Logical Object never embeds its Content Object (`13`). This keeps AI Services independent of model evolution — updating a Model Reference updates what the service resolves, never the service's own identity. An AI Service's declared dependencies are resolved through the Object Store (`23-object-store.md`) exactly like any other Object reference.

## Relationship with AI Runtime

`25-ai-runtime.md` established that AI execution is a specialization of the Runtime Pipeline with no new mechanism. An AI Service does not change this — it is an addressable Service Object that, when invoked, submits Workloads through the exact same pipeline `25` already described (Admission → Scheduling → Allocation → Execution Context → Worker → Execution Events → Execution Report). AI Services builds on the AI Runtime. It never extends or replaces it, and it never gives a Worker or a Model any capability `25` didn't already grant it.

## Relationship with Object Store

An AI Service is itself a Service Object, discovered and resolved through the Object Store (`23-object-store.md`) exactly like any other Object — by `ObjectId`, versioned like any Logical Object. Nothing about AI Services introduces a second resolution mechanism alongside the one `23` already defined. AI Services never maintains its own service registry. The Object Store already fulfills that role.

## Relationship with Runtime API

An AI Service is invoked through existing Runtime API operations. AI Services introduces no parallel API surface and no AI-specific transport.

## Composition

An AI Service may orchestrate more than one Workload — retrieval, then generation, then post-processing. Composition is orchestration of existing operations, never creation of new ones. A composed AI Service is a Pipeline (`18-worker-model.md`'s execution pattern), not a new architectural concept layered on top of one. The Pipeline execution pattern already models this orchestration. AI Services merely gives it a reusable identity.

An AI Service that composes other AI Services still composes at the level of Workloads and Objects — it never reaches into another AI Service's internal configuration. Composition happens between addressable Services, the same boundary the Runtime API already enforces between any two operations.

## Lifecycle

An AI Service follows the Object Lifecycle already defined in `13-object-model.md` (Created → Validated → Registered → Available → Referenced → Updated → Archived → Deleted) — never a second lifecycle invented for services specifically. "Updating" an AI Service is the same operation as updating any Logical Object: a new version, pointing to new configuration, the old version untouched. An AI Service's identity survives version changes; only its referenced configuration evolves.

## Observability

An AI Service is observed exactly like any other Service Object, Workload, and Worker execution — through the Object Store's Observability (`23-object-store.md`) for resolution, and through the Runtime API's per-operation metrics (`26-runtime-api.md`) for invocation. AI Services introduces no dedicated observability mechanism.

## Anti-Patterns

Avoid: a `runtime-ai-services` crate, an "AI Service" Object kind distinct from Service Object, an AI-specific Runtime API operation alongside the existing ones, an AI Service registry parallel to the Object Store, embedding a Model Reference's content inside a Service's configuration, a composition mechanism distinct from the Pipeline execution pattern.

## Review Checklist

Before adding to this document ask: can this be expressed as a Service Object, a Long-running Service or Pipeline, an AI Runtime specialization, or a Runtime API operation? If this requires a new crate, is that evidence a new architectural language has appeared instead of an extension to AI Services?

## Principles

- AI Services introduces no new architectural primitives.
- AI Services are Service Object specializations — the Runtime still does not know what AI is.
- An AI Service executes as a Long-running Service or Pipeline, never a new execution pattern.
- Composition is orchestration of existing operations, never creation of new ones.
- An AI Service's identity survives version changes; only its referenced configuration evolves.
- AI Services defines reusable AI capabilities, never reusable AI infrastructure.
- AI Services never maintains its own service registry. The Object Store already fulfills that role.

## Motto

No new architecture. Only reusable AI capabilities.
