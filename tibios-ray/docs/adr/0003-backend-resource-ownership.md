# 3. Backend Resource Ownership and Concurrency Strategy

## Status

Accepted — amends [0001](0001-provider-backend-composition.md)

## Context

Implementing [ADR-0001](0001-provider-backend-composition.md) surfaced a case
where the codebase satisfies its letter while contradicting its intent.
`LlamaCppTextBackend.acquire()` (`engines/llamacpp.py`) constructs a new
`Llama` — full GGUF load, "seconds-to-minutes of blocking I/O" per its own
comment (`LC3`) — on every call, not once at startup. This is not an
oversight: `LC3`/`LC4` document why — each session gets its own `Llama` and
its own `asyncio.Lock`, so `generate()` for two different sessions never
blocks on each other. A single shared `Llama` behind one process-wide lock
would remove that per-request construction cost but serialize every chat
request through this backend — exactly the defect `engines/vllm.py`'s own
docstring already names for a different engine: *"Sessions are coupled: one
shared engine means head-of-line blocking."*

Meanwhile `OnnxEmbeddingBackend`/`OnnxRerankBackend` (`engines/onnxrt.py`)
already do the opposite, and correctly: **one shared `InferenceSession`,
constructed once, reused across all requests with no lock at all**, because
ONNX Runtime documents `Run()` on a shared session as thread-safe (`OR2`/
`OR3`). Two working engines in this codebase already use two different
concurrency strategies for the same underlying resource-reuse goal — proof
that a single strategy mandated for every Backend would be wrong for at
least one of them.

## Decision

- A Backend owns all heavyweight inference resources required to serve
  requests (model weights, KV cache, execution sessions/contexts, thread
  pools, engine handles, etc.).
- Those resources are created during Backend initialization, at Composition
  Root boot — never during a request's `acquire()`/`release()` cycle.
- The **concurrency strategy** for those resources — one shared instance, a
  pool of N pre-warmed instances, engine-native streams/scheduling, or
  anything else — is a Backend-internal implementation decision, scoped to
  that Backend, not fixed by this ADR or by ADR-0001. Different engines are
  expected to choose differently, exactly as ONNX Runtime and llama.cpp
  already do.
- For `LlamaCppTextBackend` specifically: `acquire()`/`release()` change from
  constructing/closing a `Llama` per call to checking out/returning an
  instance from a pool of N pre-warmed `Llama` instances, all built once at
  startup. N is configurable (e.g. `TIBIOS_RAY_LLAMACPP_POOL_SIZE`);
  `acquire()` never constructs an (N+1)th instance. Exhaustion behavior
  (wait vs. reject) is a `provider-backend-composition` design decision, not
  an ADR-level one.
- A Backend SHOULD validate at startup whether its configured resource
  strategy is physically viable (e.g. pool size × per-instance memory
  footprint against available RAM/VRAM) and fail fast rather than degrade
  or OOM later at request time. The validation mechanism itself is
  implementation detail, deferred to design.

## Consequences

- Each engine keeps the freedom to implement whatever concurrency model
  fits its SDK — already true today (ONNX Runtime: shared/unlocked;
  llama.cpp: to become pooled) — instead of every Backend being forced into
  one uniform residency shape.
- llama.cpp requests are no longer head-of-line blocked behind one global
  lock, without paying today's per-request reconstruction cost.
- Startup memory footprint becomes an explicit, configurable knob (pool
  size) instead of an implicit consequence of request volume.
- Pool sizing is a new operational parameter every deployment must tune
  (RAM vs. concurrency trade-off) — no longer "works the same at any N."
- Backends now legitimately vary in internal shape (single instance vs.
  pool vs. scheduler); a reader can no longer assume one uniform residency
  model applies across every engine, only that whichever model is chosen,
  resources are never built per-request.
