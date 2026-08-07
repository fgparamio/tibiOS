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
// `DeterministicEngine` is unreferenced by production code once the real
// engine is selected under the `llamacpp` feature (D5 keeps the file and
// its own tests either way) — a targeted allow, not a deletion. Lint
// attributes on a `mod` item apply to its contents (design.md D8).
#[cfg_attr(feature = "llamacpp", allow(dead_code))]
mod reference;
#[cfg(feature = "llamacpp")]
mod llamacpp;

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

/// The sole way anything outside `engine/` obtains a `TextGenerationEngine`
/// — returned type-erased so no concrete engine type is ever named beyond
/// this file, including in `local_infer/mod.rs` itself
/// (`worker-local-infer-adapter/spec.md` — "No engine-specific name appears
/// outside the engine module"). Selection is compile-time and total,
/// gated solely by the `llamacpp` Cargo feature — no runtime condition, no
/// silent fallback (design.md D8).
#[cfg(not(feature = "llamacpp"))]
pub(super) fn default_engine() -> std::sync::Arc<dyn TextGenerationEngine> {
    use reference::DeterministicEngine;
    std::sync::Arc::new(DeterministicEngine::new())
}

/// See the `#[cfg(not(feature = "llamacpp"))]` sibling above — this is the
/// same sole exit point, selected when the feature is enabled.
#[cfg(feature = "llamacpp")]
pub(super) fn default_engine() -> std::sync::Arc<dyn TextGenerationEngine> {
    use llamacpp::LlamaCppEngine;
    std::sync::Arc::new(LlamaCppEngine::new())
}

/// Test-only seam: the deterministic reference engine, unconditionally,
/// regardless of the `llamacpp` feature. `local_infer/mod.rs`'s own tests
/// (worker/channel/cancellation conformance) exercise the `WorkerService`
/// contract, not any specific engine's inference behavior, so they must not
/// pick up whichever engine `default_engine()` selects — that would make
/// `cargo test --features llamacpp` exercise real inference wiring in tests
/// that were written to assert protocol behavior against a known-shape
/// engine. Concentrated here, alongside `default_engine()`, so no
/// engine-specific name leaks outside this module either way
/// (`worker-local-infer-adapter/spec.md`).
#[cfg(test)]
pub(super) fn deterministic_engine_for_tests() -> std::sync::Arc<dyn TextGenerationEngine> {
    use reference::DeterministicEngine;
    std::sync::Arc::new(DeterministicEngine::new())
}
