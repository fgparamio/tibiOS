# Delta for Runtime Worker

> `RayWorker` (`worker-grpc-client-adapter`) reuses `runtime-worker`'s existing private `adapters::grpc` tree instead of opening a new cross-crate privacy hole. This widens the crate's role from domain-language-plus-port-only to also hosting exactly one concrete implementation; the Purpose statement's "all outside `adapters/`" phrasing is reconciled at archive time.

## ADDED Requirements

### Requirement: runtime-worker May Host Exactly One Concrete WorkerService Implementation, Exposed Only Via Factory

`runtime-worker` MAY contain a concrete `WorkerService` implementation (`RayWorker`) inside its existing private `adapters::grpc` tree, provided it is reachable from outside the crate only through a factory function returning `impl WorkerService` (never the concrete type), and provided this addition introduces no new workspace-crate dependency and no external dependency outside the existing `{tonic, prost}` allowlist.

#### Scenario: RayWorker adds no new dependency

- GIVEN `crates/runtime-worker/Cargo.toml` before and after `RayWorker` is added
- WHEN its dependency list is diffed
- THEN it is unchanged

#### Scenario: RayWorker's concrete type stays unreachable outside the factory

- GIVEN `runtime-worker`'s public API after `RayWorker` is added
- WHEN it is inspected
- THEN `RayWorker` itself is not a public item — only a factory function returning `impl WorkerService` is
