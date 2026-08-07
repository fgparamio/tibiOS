//! Private adapter layer. No adapter module or adapter type is ever
//! re-exported; the sole exception is a small set of opaque Composition-Root
//! factory functions (`impl <public port>`, no transport type in their
//! signature) — see `runtime/tests/architecture_guard.rs` for the guard
//! that enforces this. Design: `openspec/changes/worker-grpc-adapter/design.md`
//! D7; `openspec/changes/worker-grpc-client-adapter/design.md` D1 for the
//! factory exception.

#[allow(missing_docs, clippy::all, clippy::pedantic)]
mod grpc;

pub use grpc::new_ray_worker;
