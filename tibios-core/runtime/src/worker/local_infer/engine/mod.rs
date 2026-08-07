//! The Local-Infer engine port and its deterministic reference
//! implementation.
//!
//! Everything in this subtree is `std`-only: no `async`, no `.await`, and no
//! `tokio::` path anywhere under `local_infer/engine/`
//! (`worker-local-infer-adapter/spec.md` — "The Engine Port Is Wholly
//! Synchronous, Std-Only, And Knows Nothing About The Worker Domain"). Two
//! architecture-guard scans (`local_infer_engine_names_no_async_runtime`,
//! `local_infer_engine_declares_no_async_surface`,
//! `runtime/tests/architecture_guard.rs`) enforce this mechanically on every
//! `cargo test` run, not just by convention.
//!
//! This rule exists so the engine subtree stays trivially extractable: a
//! future real inference backend (e.g. llama.cpp bindings) plugs in here
//! without ever depending on an async runtime (design.md D4, D6). The
//! adapter side of the blocking boundary (`local_infer/mod.rs`) is the only
//! tokio-aware file in the `local_infer` module tree.
//!
//! Dead code is expected and correct for this slice alone: nothing outside
//! this subtree's own test modules references it yet — `LocalInferWorker`,
//! the first real call site, lands in design.md D13's next slice (S2/PR2).
//! This matches the rollback notes' own description of a
//! reverted-but-compiling subtree as "dead but green"; the `allow` below is
//! expected to become unnecessary the moment PR2 wires `LocalInferWorker`
//! in.

mod port;
mod reference;

// See the module doc comment above: this slice alone leaves these
// re-exports unconsumed outside the subtree's own tests.
#[allow(unused_imports)]
pub(super) use port::{
    EngineError, GenerationRequest, SinkVerdict, TextGenerationEngine, Token, TokenSink,
};
// Only named by this module's own tests today (production code destructures
// `Ok(summary)` without spelling out the type) — re-exported anyway since it
// is half of `TextGenerationEngine::generate`'s public return type.
#[allow(unused_imports)]
pub(super) use port::GenerationSummary;
use reference::DeterministicEngine;

/// The sole way anything outside `engine/` obtains a `TextGenerationEngine`
/// — returned type-erased so `DeterministicEngine` is never named beyond
/// this file, including in `local_infer/mod.rs` itself
/// (`worker-local-infer-adapter/spec.md` — "No engine-specific name appears
/// outside the engine module").
pub(super) fn default_engine() -> std::sync::Arc<dyn TextGenerationEngine> {
    std::sync::Arc::new(DeterministicEngine::new())
}
