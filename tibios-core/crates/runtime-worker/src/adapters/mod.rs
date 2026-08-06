//! Private adapter layer. Nothing in this module tree is re-exported —
//! see `runtime/tests/architecture_guard.rs` for the guard that enforces
//! this. Design: `openspec/changes/worker-grpc-adapter/design.md` D7.

#[allow(missing_docs, clippy::all, clippy::pedantic)]
mod grpc;
