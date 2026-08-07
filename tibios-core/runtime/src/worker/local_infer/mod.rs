//! The Local-Infer `WorkerService` adapter (`worker-local-infer-adapter/spec.md`).
//!
//! This slice (design.md D13, S1/PR1) contains only the engine domain
//! (`engine/`): synchronous, `std`-only, and dependency-free.
//! `LocalInferWorker` — the adapter that drives `engine/` across the
//! `spawn_blocking` + `Handle::block_on` blocking boundary (design.md D8) —
//! lands in the next slice (S2/PR2). Until then this module is inert:
//! nothing outside `engine/`'s own test modules references it.

// Temporary: this slice alone leaves `engine/` wired to nothing, which
// clippy sees as dead code. S2 (`LocalInferWorker`) consumes it immediately
// and this allow disappears with it.
#![allow(dead_code)]

pub(super) mod engine;
