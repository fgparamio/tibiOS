//! The llama.cpp `TextGenerationEngine` implementation (design.md D7, D8,
//! D9, D10, D11) — the only file in the workspace naming `llama`,
//! `llama_cpp`, `ggml`, or `candle`
//! (`local-infer-llamacpp-engine/spec.md` — "The llama.cpp Name Stays
//! Inside The Engine Module").
//!
//! Model resolution: the engine reads its model path once per process from
//! the `TIBIOS_LOCAL_INFER_MODEL_PATH` environment variable — never from
//! `execution_parameters` (design.md D10). Missing, empty, or unloadable →
//! `EngineError::Rejected`, naming the environment variable in the reason
//! string. `TIBIOS_LOCAL_INFER_MODEL_PATH=/abs/path/model.gguf cargo test -p
//! runtime --features llamacpp -- --ignored` runs the four real-model Tier-3
//! tests in `local_infer/real_engine.rs` (design.md D12).
//!
//! Decoding is pull-based, greedy, CPU-only (design.md D9; proposal D6):
//! `generate()` calls `decode` once for the prompt, then once per generated
//! token, stopping as soon as `sink.accept` returns `SinkVerdict::Stop` —
//! there is no early-stop API to call, "stopping" is simply "not calling
//! `decode` again".

use std::ffi::OsString;
use std::path::PathBuf;

use llama_cpp_2::llama_backend::LlamaBackend;
use llama_cpp_2::llama_batch::LlamaBatch;
use llama_cpp_2::model::{AddBos, LlamaModel};
use llama_cpp_2::sampling::LlamaSampler;

use super::port::{
    EngineError, GenerationRequest, GenerationSummary, TextGenerationEngine, TokenSink,
};

/// Operator-supplied, out-of-band, resolved exactly once per process
/// (design.md D10). No registry, no download, no `WorkloadId`→artifact
/// mapping.
const MODEL_PATH_ENV: &str = "TIBIOS_LOCAL_INFER_MODEL_PATH";

/// Pure, injectable, FFI-free — so the resolution rules are unit-testable
/// without touching the process environment or loading a model (design.md
/// D10, D12). Unset, empty, non-existent, or not a file all reject; every
/// reason string names `MODEL_PATH_ENV` so a failure is self-diagnosing.
fn resolve_model_path(lookup: impl Fn(&str) -> Option<OsString>) -> Result<PathBuf, String> {
    let value = lookup(MODEL_PATH_ENV).ok_or_else(|| {
        format!("{MODEL_PATH_ENV} is not set; the llama.cpp engine has no model to load")
    })?;
    if value.is_empty() {
        return Err(format!("{MODEL_PATH_ENV} is set but empty"));
    }
    let path = PathBuf::from(value);
    if !path.is_file() {
        return Err(format!(
            "{MODEL_PATH_ENV} names {}, which does not exist or is not a file",
            path.display()
        ));
    }
    Ok(path)
}

/// The process-wide loaded model + backend (design.md D11). One per
/// process, never per-instance — see D11's "why a static".
///
/// `backend` is `ManuallyDrop`, deliberately: `LlamaBackend::drop` mutates a
/// process-wide `AtomicBool` under a single-owner invariant (only the value
/// returned by the one successful `LlamaBackend::init()` call in this
/// process may ever run that `Drop` safely). `load_model` below sometimes
/// constructs a second `LlamaBackend` value when `init()` reports
/// `BackendAlreadyInitialized` (a real, discovered test-ordering hazard —
/// see `load_model`'s doc comment); running that second value's `Drop`
/// would either free the still-live backend out from under the real owner
/// or panic on the crate's own `unreachable!()`. Never dropping matches the
/// intended production lifecycle anyway: the model stays loaded for the
/// life of the process (D11), and `static` values are never destructed at
/// normal process exit.
struct LoadedModel {
    #[allow(dead_code)] // kept alive so `model`'s FFI handles stay valid
    backend: std::mem::ManuallyDrop<LlamaBackend>,
    model: LlamaModel,
}

/// This engine is CPU-only, deliberately (proposal D6, spec.md Purpose): no
/// GPU/Metal/CUDA/ROCm offload path. `n_gpu_layers(0)` pins that regardless
/// of what the pinned crate's backend auto-detects on the host.
fn model_params() -> llama_cpp_2::model::params::LlamaModelParams {
    llama_cpp_2::model::params::LlamaModelParams::default().with_n_gpu_layers(0)
}

/// The context window used for every `generate()` call (design.md D9's
/// bounded prompt-length check reads this back via `LlamaContextParams::n_ctx`).
fn context_params() -> llama_cpp_2::context::params::LlamaContextParams {
    llama_cpp_2::context::params::LlamaContextParams::default()
}

/// Initialises the backend and loads the GGUF at `path`. Tolerates the
/// backend having already been initialised elsewhere in this process
/// (`LlamaBackend::init()`'s own doc comment: "This can generally be
/// ignored as initializing the backend is idempotent.") — `LlamaBackend` has
/// no fields, so constructing it directly in that case is exactly what the
/// already-initialised backend already looks like, structurally.
///
/// **Discovered test-ordering hazard, not in design.md:** in a single test
/// binary process, only the *first* caller across every test function ever
/// gets `Ok` from `LlamaBackend::init()`; every later caller — including
/// `the_native_backend_links_and_initialises`'s own direct call — gets
/// `Err(BackendAlreadyInitialized)`. Wrapping the returned value in
/// `ManuallyDrop` (see `LoadedModel`) before it is used even once means
/// neither branch's value is ever dropped through `load_model`, so this
/// function can never trigger the crate's single-owner `Drop` invariant
/// itself, regardless of call order.
fn load_model(path: &std::path::Path) -> Result<LoadedModel, String> {
    let backend = std::mem::ManuallyDrop::new(match LlamaBackend::init() {
        Ok(backend) => backend,
        Err(llama_cpp_2::LlamaCppError::BackendAlreadyInitialized) => LlamaBackend {},
        Err(error) => return Err(format!("failed to initialise the llama.cpp backend: {error}")),
    });
    let model = LlamaModel::load_from_file(&backend, path, &model_params())
        .map_err(|error| format!("failed to load {}: {error}", path.display()))?;
    Ok(LoadedModel { backend, model })
}

/// D11's verification gate — PR2's first task, before any decode logic.
/// `TextGenerationEngine: Send + Sync` and the `LOADED` `static` both demand
/// it. If this fails to compile, Fallback B (a dedicated owner thread +
/// bounded `mpsc`) replaces this file's design — it did not fail: the
/// pinned crate's `LlamaModel` is `unsafe impl Send + Sync` and
/// `LlamaBackend`/`LlamaCppEngine` are trivially auto-`Send + Sync`.
const fn assert_send_sync<T: Send + Sync>() {}
const _: () = {
    assert_send_sync::<LoadedModel>();
    assert_send_sync::<LlamaCppEngine>();
};

/// Process-wide, not per-instance (design.md D11 — "why a static"):
/// `cargo test` runs every test as a thread within one process, and the O1-O4
/// conformance harness builds a fresh `LocalInferWorker` — hence a fresh
/// `LlamaCppEngine` — per test. A per-instance cache would call
/// `LlamaBackend::init()` once per test and fail from the second test
/// onward; the exactly-once guarantee must be process-scoped because
/// llama.cpp's own requirement is process-scoped. `Result` is cached too: a
/// failed load is remembered so executions 2..N fail instantly with the
/// identical message instead of re-attempting a multi-gigabyte read.
static LOADED: std::sync::OnceLock<Result<LoadedModel, String>> = std::sync::OnceLock::new();

fn loaded_model() -> Result<&'static LoadedModel, EngineError> {
    LOADED
        .get_or_init(|| {
            // Not `resolve_model_path(std::env::var_os)` directly: passing a
            // generic fn item where `impl Fn(&str) -> Option<OsString>` is
            // expected fails HRTB inference ("implementation not general
            // enough") because the fn item's own lifetime parameter and the
            // trait bound's higher-ranked one don't unify without a closure
            // wrapper to re-derive it fresh at each call.
            let path = resolve_model_path(|key| std::env::var_os(key))?;
            load_model(&path)
        })
        .as_ref()
        .map_err(|reason| EngineError::Rejected(reason.clone()))
}

/// The llama.cpp-backed `TextGenerationEngine`. Zero-sized — all state lives
/// in the process-wide `LOADED` static (design.md D11).
pub(super) struct LlamaCppEngine;

impl LlamaCppEngine {
    /// Infallible by construction (design.md D8): `default_engine()`
    /// returns `Arc<dyn TextGenerationEngine>`, not `Result`, so all
    /// fallible work (backend init, model load) is deferred to the first
    /// `generate()` call.
    pub(super) fn new() -> Self {
        Self
    }
}

/// Maps any FFI-adjacent error into the port's one error shape.
fn reject<E: std::fmt::Display>(error: E) -> EngineError {
    EngineError::Rejected(error.to_string())
}

/// `token_to_bytes`, never `token_to_str` (design.md D9's "five details
/// that are decisions, not incidentals" — `OutputChunk.data` is `Vec<u8>`,
/// and `token_to_str` can fail on a token carrying a partial UTF-8
/// codepoint). The pinned crate deprecates `LlamaModel::token_to_bytes` and
/// `Special` in favour of `token_to_piece_bytes`; this reimplements the
/// deprecated wrapper's own retry-on-`InsufficientBufferSpace` logic
/// (`special: false` matches the old `Special::Plaintext`) without calling
/// the deprecated API, so `cargo clippy -D warnings` stays clean.
fn token_to_bytes(
    model: &LlamaModel,
    token: llama_cpp_2::token::LlamaToken,
) -> Result<Vec<u8>, EngineError> {
    use llama_cpp_2::TokenToStringError;
    match model.token_to_piece_bytes(token, 8, false, None) {
        Err(TokenToStringError::InsufficientBufferSpace(needed)) => model
            .token_to_piece_bytes(
                token,
                usize::try_from(-needed).map_err(reject)?,
                false,
                None,
            )
            .map_err(reject),
        other => other.map_err(reject),
    }
}

impl TextGenerationEngine for LlamaCppEngine {
    fn generate(
        &self,
        request: &GenerationRequest,
        sink: &mut dyn TokenSink,
    ) -> Result<GenerationSummary, EngineError> {
        let loaded = loaded_model()?;

        // Fresh context per call — the KV cache must never span two
        // executions (design.md D11).
        let mut ctx = loaded
            .model
            .new_context(&loaded.backend, context_params())
            .map_err(reject)?;
        let n_ctx = ctx.n_ctx() as usize;

        let prompt_tokens = loaded
            .model
            .str_to_token(&request.prompt, AddBos::Always)
            .map_err(reject)?;
        // Bounded prompt eval (design.md D9's disclosed caveat): a `Stop`
        // cannot be observed during the single prompt-eval `decode` call
        // below, because no token exists yet to `accept`. This bound turns
        // an unbounded worst case into a bounded one — an over-long prompt
        // is rejected before any FFI work happens.
        if prompt_tokens.len() >= n_ctx {
            return Err(EngineError::Rejected(format!(
                "prompt is {} tokens, which does not fit the {n_ctx}-token context window",
                prompt_tokens.len()
            )));
        }

        let mut batch = LlamaBatch::new(n_ctx, 1);
        batch.add_sequence(&prompt_tokens, 0, false).map_err(reject)?;
        ctx.decode(&mut batch).map_err(reject)?; // ① prompt eval — ONE bounded FFI call

        let mut sampler = LlamaSampler::greedy(); // greedy only (design.md D9)
        let prompt_len = i32::try_from(prompt_tokens.len()).map_err(reject)?;
        let mut tokens_produced = 0u64;
        let mut stopped_early = false;

        for sequence in 0..request.max_tokens {
            let next = sampler.sample(&ctx, batch.n_tokens() - 1);
            sampler.accept(next);
            if loaded.model.is_eog_token(next) {
                break; // ② natural end-of-generation — stopped_early stays false
            }

            let bytes = token_to_bytes(&loaded.model, next)?;
            tokens_produced += 1;
            if sink.accept(super::port::Token { sequence, bytes }) == super::port::SinkVerdict::Stop
            {
                stopped_early = true;
                break; // ③ THIS is how Stop halts llama.cpp — no more `decode` calls
            }

            let position = prompt_len + i32::try_from(sequence).map_err(reject)?;
            batch.clear();
            batch.add(next, position, &[0], true).map_err(reject)?;
            ctx.decode(&mut batch).map_err(reject)?; // ④ one bounded FFI call per token
        }

        Ok(GenerationSummary {
            tokens_produced,
            stopped_early,
        })
    }
}

#[cfg(test)]
mod tests {
    use llama_cpp_2::llama_backend::LlamaBackend;

    use super::super::port::{SinkVerdict, Token};
    use super::{
        load_model, resolve_model_path, EngineError, GenerationRequest, LlamaCppEngine,
        TextGenerationEngine, TokenSink, MODEL_PATH_ENV,
    };

    struct UnusedSink;

    impl TokenSink for UnusedSink {
        fn accept(&mut self, _token: Token) -> SinkVerdict {
            panic!("the PR1 stub must reject before producing any token")
        }
    }

    /// Spec scenario "An unset model path is rejected", the pure half
    /// (design.md D10, D12): no env access, no FFI, no static — the lookup
    /// closure simply reports "not set".
    #[test]
    fn an_unset_model_path_is_rejected_by_name() {
        let result = resolve_model_path(|_| None);

        let reason = result.expect_err("an absent lookup entry must be rejected");
        assert!(
            reason.contains(MODEL_PATH_ENV),
            "expected the rejection reason to name {MODEL_PATH_ENV}, got: {reason}"
        );
    }

    /// Same injectable helper, three cases: empty string, a path that does
    /// not exist, and a path that is a directory rather than a file.
    #[test]
    fn an_empty_or_nonexistent_model_path_is_rejected() {
        let empty = resolve_model_path(|_| Some(std::ffi::OsString::new()));
        let reason = empty.expect_err("an empty value must be rejected");
        assert!(reason.contains(MODEL_PATH_ENV));

        let missing = resolve_model_path(|_| {
            Some(std::ffi::OsString::from(
                "/nonexistent/path/does-not-exist.gguf",
            ))
        });
        let reason = missing.expect_err("a nonexistent path must be rejected");
        assert!(reason.contains(MODEL_PATH_ENV));

        let directory = std::env::temp_dir();
        let directory_result =
            resolve_model_path(move |_| Some(std::ffi::OsString::from(directory.clone())));
        let reason = directory_result.expect_err("a directory is not a valid model file");
        assert!(reason.contains(MODEL_PATH_ENV));
    }

    /// The load-bearing FFI-robustness claim (design.md D12): a file that
    /// exists but is not a valid GGUF must reject cleanly, never panic or
    /// abort the process.
    #[test]
    fn an_unloadable_model_file_is_rejected_not_panicked() {
        let mut path = std::env::temp_dir();
        path.push(format!(
            "tibios-llamacpp-garbage-{}.gguf",
            std::process::id()
        ));
        std::fs::write(&path, b"this is not a valid gguf file")
            .expect("writing the garbage fixture file must succeed");

        let result = load_model(&path);

        let _ = std::fs::remove_file(&path);
        assert!(
            result.is_err(),
            "a garbage-bytes file must be rejected, not accepted"
        );
    }

    /// Spec scenario "An unset model path is rejected", through the real
    /// engine (design.md D12): the single test that goes through the
    /// `LOADED` static. Supersedes PR1's
    /// `the_pr1_stub_rejects_every_request_without_producing_a_token`, whose
    /// "not implemented yet" assertion stopped being true once `generate()`
    /// gained a real first step (task 2.6/2.7).
    #[test]
    fn a_missing_model_yields_rejected_through_the_engine() {
        // This is the one test that goes through the real, process-wide
        // `LOADED` static and the real environment. Mutating process
        // environment (`std::env::set_var`/`remove_var`) is `unsafe` as of
        // edition 2024 (data races with concurrent reads from other
        // threads) — forbidden here by the workspace-wide `unsafe_code =
        // "deny"` lint, which this file's own spec requirement says must
        // never relax. So: read-only. If the ambient environment genuinely
        // has the variable set, this test cannot assert the unset case
        // meaningfully — skip rather than force a false result, mirroring
        // the precedented ambient-state skip in
        // `crates/runtime-worker/tests/proto_drift.rs`.
        if std::env::var_os(MODEL_PATH_ENV).is_some() {
            eprintln!(
                "skipping a_missing_model_yields_rejected_through_the_engine: \
                 {MODEL_PATH_ENV} is set in the ambient environment"
            );
            return;
        }

        let engine = LlamaCppEngine::new();
        let request = GenerationRequest {
            prompt: "hello".to_string(),
            max_tokens: 1,
            cpu_spin_iterations: 0,
        };
        let mut sink = UnusedSink;

        let outcome = engine.generate(&request, &mut sink);

        match outcome {
            Err(EngineError::Rejected(reason)) => {
                assert!(
                    reason.contains(MODEL_PATH_ENV),
                    "expected the rejection reason to name {MODEL_PATH_ENV}, got: {reason}"
                );
            }
            other => panic!("expected Err(EngineError::Rejected(_)), got: {other:?}"),
        }
        // `UnusedSink::accept` panics if ever called — reaching this line at
        // all proves zero tokens were delivered.
    }

    /// Discovered during PR2 (not in design.md): `LlamaBackend::init()` is
    /// process-wide idempotent-but-single-success — only the first caller in
    /// this test binary's process gets `Ok`; every later direct call, from
    /// any test function, gets `Err(BackendAlreadyInitialized)`. Test
    /// execution order across the crate is not guaranteed, and
    /// `an_unloadable_model_file_is_rejected_not_panicked` /
    /// `a_missing_model_yields_rejected_through_the_engine` also reach
    /// `LlamaBackend::init()` via `load_model`. Both outcomes prove the same
    /// thing this test is for (the toolchain links and the backend is
    /// usable), so both are accepted here — see `load_model`'s own
    /// `BackendAlreadyInitialized` handling for the production-code half of
    /// the same accommodation.
    #[test]
    fn the_native_backend_links_and_initialises() {
        let backend = LlamaBackend::init();
        assert!(
            matches!(
                backend,
                Ok(_) | Err(llama_cpp_2::LlamaCppError::BackendAlreadyInitialized)
            ),
            "expected the pinned llama-cpp-2 backend to initialise successfully (or report the process-wide idempotency error if another test already initialised it), got: {backend:?}"
        );
    }
}
