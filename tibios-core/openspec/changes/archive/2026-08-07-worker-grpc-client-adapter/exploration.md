# Exploration: `worker-grpc-client-adapter`

## Current State

`tibios-core` is the gRPC **client**, `tibios-ray` is the **server** (`worker-grpc-adapter/design.md:67`, `proposal.md:18` — `build_server(false)`). That change compiled the frozen `.proto` behind a private `crates/runtime-worker/src/adapters/grpc/` tree and wrote every conversion `TryFrom`/`From` impl `convert.rs` needs — but explicitly deferred "Channel/Tokio Wiring in Composition Root — gRPC client instantiation and lifecycle" (`worker-grpc-adapter/archive-report.md:115`). `worker-inbound-port` then built the domain language and Inbound Port (`WorkerService`), and `worker-inprocess-adapter`/`worker-local-infer-adapter` proved the port with two in-process implementations, both wired into `runtime` behind an `AnyWorker` enum. No network-backed `WorkerService` exists yet — this change is that missing third implementation.

Today `runtime/src/worker/mod.rs`'s `WorkerKind` has two variants (`InProcess`, `LocalInfer`) and `any_worker(kind)` matches on them to build `AnyWorker::InProcess(..)` / `AnyWorker::LocalInfer(..)`. `AnyWorker`'s own doc precedent (`ports/worker_service.rs`'s module doc) already sketches the target shape literally:

```text
enum AnyWorker {
    Local(LocalInferWorker),
    Ray(RayWorker),
}
```

— i.e. the codebase itself already names the concrete type `RayWorker` and treats "forwarding to the remote process's own bookkeeping" as a conforming way to satisfy O1-O4 (`ports/worker_service.rs`'s `execute` doc comment).

## Affected Areas

- `crates/runtime-worker/src/adapters/grpc/convert.rs` — `ResponseFrame` (`Event`/`Report`) and `TryFrom<worker_proto::ExecutionResponse> for ResponseFrame` already exist, currently `#[allow(dead_code)]` — built in anticipation of exactly this client, unused until now.
- `crates/runtime-worker/src/adapters/grpc/convert.rs` — **missing** conversions this change needs to add:
  - Domain `ExecutionContext` → wire `worker_proto::ExecutionContext` (only the reverse, wire→domain, exists today — built for a server tibios-core never implements). Needed to build the `SubmitJob` request.
  - Wire `worker_proto::CancelAck` → domain `CancelAck` (no conversion exists either direction; wire message is empty, domain is a unit struct — trivial once written).
  - `CancelRequest`/`PulseRequest` construction is *not* a `TryFrom` gap — both wire messages are a single `WorkloadId` field, and `From<runtime_primitives::WorkloadId> for identity_proto::WorkloadId` already exists.
- `crates/runtime-worker/src/error.rs` — `WorkerError` has exactly three variants (`UnknownWorkload`, `DuplicateWorkload`, `ChannelClosed`), none of which fit a transport-level failure (connection refused, deadline exceeded, a `tonic::Status` unrelated to correlation). A new variant is needed, with its own `Classify` mapping — most `tonic::Status` codes are plausibly `Transient` (network hiccup), but `Status::invalid_argument`-shaped failures are `Permanent`; this needs a real design decision, not a guess here.
- `runtime/src/worker/mod.rs` — `WorkerKind` needs a third variant (`Ray`, per the existing doc precedent) and `any_worker` needs a new match arm; whatever configuration a `RayWorker` needs (endpoint address, at minimum) has to come from somewhere — `main.rs` currently hard-codes nothing configurable.
- `runtime/tests/architecture_guard.rs` — depending on where `RayWorker` ends up living (see Approaches), the `EXTERNAL_ALLOWED` table and/or a new containment scan may need updating.
- `runtime/src/worker/conformance.rs` — the shared O1-O4 harness (`worker_conformance_suite!`) must be invoked against `RayWorker` and against `AnyWorker::Ray(..)`, per `worker-inbound-port/spec.md`'s "invoked at least three times... none of them skipped" — now at least five invocations total. This is the crux open question (see below).

## The Open Question: O1-O4 Against a Real Network Call

The shared conformance harness asserts real registration/dedup/cancel/pulse behavior end-to-end, including a 0-duration allocation contract that must produce `Failed` and a duplicate `execute` that must be rejected without starting a second run. A `RayWorker` that purely forwards to `tibios-ray` cannot honestly pass this harness in `cargo test` without something answering on the other end of the connection — CI has no running `tibios-ray` process, mirroring the exact problem `worker-local-infer-adapter` solved for `--features llamacpp` (real model unavailable in CI) via a deterministic test-only engine seam.

Two live sub-questions this exploration surfaces but does not resolve:

1. **Does `RayWorker` keep any local bookkeeping (a `WorkloadId`-keyed map), or does it trust the server entirely** — i.e. is O1 registration "the RPC call was issued" or "the server acknowledged receipt"? The `WorkerService` doc comment permits either ("an actor, a `Mutex`-guarded map, or — for `tibios-ray` — forwarding to the remote process's own bookkeeping are all conforming implementations"), but the two choices have different failure modes if the connection drops mid-call.
2. **How does the harness get something to talk to.** The precedent (deterministic engine seam) doesn't transplant directly — there's no in-process engine to swap in, because the entire point of `RayWorker` is the network hop. The realistic option is an in-process fake `tonic` server (bound to a loopback socket or an in-memory duplex transport) implementing just enough of `WorkerExecution` to uphold O1-O4 semantics, that the harness's `RayWorker` instance connects to.

## Approaches

1. **`RayWorker` lives inside `runtime-worker`, using the existing private `adapters::grpc` tree, exposed via a new `pub fn ray_worker(endpoint) -> impl WorkerService`**
   - `tonic` (default features, includes `transport`) is already an allowed `runtime-worker` external dependency (`EXTERNAL_ALLOWED`) — no guard-table change needed there. `tonic`'s async client methods don't require the *calling* crate to depend on `tokio` directly (the executor is supplied by whoever polls the future — `runtime`), so this doesn't need to punch a hole in "Runtime Is The Sole Crate Permitted An Async Runtime Dependency".
   - Reuses `adapters::grpc`'s existing privacy boundary — `WorkerExecutionClient` and every wire type never have to become reachable from `runtime`, because the factory function is defined in the same crate that already owns them.
   - Pros: no new cross-crate privacy hole, no new `EXTERNAL_ALLOWED` row, mirrors `worker-inprocess-adapter`'s own "factory returning `impl WorkerService`, concrete type never named outside" shape but one crate over.
   - Cons: breaks the pattern set by `worker-inprocess-adapter`/`worker-local-infer-adapter`, where every concrete Worker so far lives inside `runtime` itself, not `runtime-worker` — `runtime-worker`'s spec has been strictly "domain language + port", never a concrete implementation. Needs a spec-level decision (does `runtime-worker`'s Purpose section widen to allow this, or is that a contract violation).
   - Effort: Medium.

2. **`RayWorker` lives inside `runtime`, in a new `runtime/src/worker/ray/` module (matching `local_infer/`'s and `in_process`'s placement), and `runtime-worker`'s `adapters::grpc` module gains a narrow, guard-enforced `pub` surface for exactly the types the client wiring needs**
   - Consistent with the established pattern: every concrete `WorkerService` implementation lives in `runtime`, `runtime-worker` stays domain-plus-port-only.
   - Requires deliberately opening `adapters::grpc`'s privacy (today `mod grpc;`, no `pub` anywhere in that tree) for at least `WorkerExecutionClient` and the wire message types `convert.rs` already converts to/from — the exact tension `worker-grpc-adapter/design.md` mentions resolving via `build_server(false)` in the first place ("removes the sharpest edge of the 'no public traits' tension before privacy has to do any work" — this change re-introduces a version of that tension for the client side).
   - Needs a new architecture-guard containment scan (or an `EXTERNAL_ALLOWED`-style table) proving the newly-`pub` wire types stay unreachable from outside `runtime`+`runtime-worker`, similar to the local-infer engine's source-token scans.
   - Pros: consistent placement with existing precedent; keeps `runtime` as the sole place that assembles a concrete `WorkerService`.
   - Cons: more moving parts (new guard scan, new `pub` surface with real containment risk) for a placement question Approach 1 sidesteps entirely.
   - Effort: Medium-High.

## Recommendation

Approach 1. It reuses privacy that already exists instead of deliberately widening it, needs no new architecture-guard scan, and the "factory hides the concrete type" shape `worker-inprocess-adapter`'s spec already establishes transfers directly — only the owning crate changes. The placement tension (a concrete Worker in `runtime-worker` rather than `runtime`) is real but is a one-line spec-scope decision, not new engineering risk; the alternative buys back placement consistency at the cost of a genuinely new privacy hole and a genuinely new guard scan.

The O1-O4-against-a-fake-server question, whichever approach wins, is the change's real design work and should be settled in `sdd-design`, not guessed here.

## Risks

- **`WorkerError`'s transport-failure classification is a real design decision, not a mechanical addition** — get `Transient` vs `Permanent` wrong for the wrong `tonic::Status` code and a Runtime built on top of this Worker could retry-loop a request the server will never accept, or give up on one a retry would have fixed.
- **The in-process fake server, if that's the path taken, is itself nontrivial `tonic` server code** (even `build_server(false)` means `runtime-worker` has never compiled a server trait) — likely needs its own narrow, test-only server implementation, adding real surface area for a test harness only.
- **Endpoint configuration is currently unspecified** — `main.rs` hard-codes nothing today; this change needs to decide where a `tibios-ray` address comes from (env var, CLI flag, config file) even for a minimal wiring, and that's a Composition-Root-shaped decision the proposal should scope explicitly in or out.

## Ready for Proposal

Yes — the placement approach, the missing conversions, the `WorkerError` gap, and the O1-O4 harness question are all concrete enough to write a proposal against. The O1-O4-against-a-fake-server mechanism itself should be pinned down in `sdd-design`, not the proposal.
