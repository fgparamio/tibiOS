//! `DeterministicEngine`: the sole reference implementation of
//! `TextGenerationEngine` (design.md D7).
//!
//! NOT an inference engine, and never will be. A placeholder that exists to
//! prove the blocking boundary end-to-end: it burns a bounded,
//! caller-chosen amount of CPU per token and emits a deterministic byte
//! sequence derived from the prompt and token index. A real generation
//! backend replaces this file wholesale; nothing outside `engine/` may ever
//! name this type (`worker-local-infer-adapter/spec.md` — "No engine-specific
//! name appears outside the engine module").

use super::port::{
    EngineError, GenerationRequest, GenerationSummary, SinkVerdict, TextGenerationEngine, Token,
    TokenSink,
};

/// FNV-1a's standard 64-bit offset basis (matches `in_process.rs`'s own
/// FNV-1a construction — design.md D7).
const FNV_OFFSET_BASIS: u64 = 0xcbf2_9ce4_8422_2325;
/// FNV-1a's standard 64-bit prime.
const FNV_PRIME: u64 = 0x0000_0100_0000_01b3;

/// Folds `bytes` into `hash` via one FNV-1a pass.
fn fnv1a_step(hash: u64, bytes: &[u8]) -> u64 {
    bytes.iter().fold(hash, |acc, &byte| {
        (acc ^ u64::from(byte)).wrapping_mul(FNV_PRIME)
    })
}

/// The token content for `prompt` at `index` — pure function of the request
/// and the index alone, deliberately independent of `cpu_spin_iterations` so
/// the spin count can burn CPU without ever affecting output (spec scenario
/// "The per-token spin cost is caller-configured, not hardcoded").
fn token_hash(prompt: &str, index: u64) -> u64 {
    let seeded = fnv1a_step(FNV_OFFSET_BASIS, prompt.as_bytes());
    fnv1a_step(seeded, &index.to_le_bytes())
}

/// Burns `iterations` rounds of genuine (non-optimized-away) computation
/// derived from `hash` and `index`, discarding the result. This is the
/// stand-in for a real engine's per-token CPU cost — a bounded spin loop,
/// never `std::thread::sleep` (forbidden by `05-async-concurrency.md:29`;
/// sleeping would prove a thread was parked, not that CPU-bound work left
/// the executor).
fn spin(hash: u64, index: u64, iterations: u32) -> u64 {
    let mut spun = hash;
    for _ in 0..iterations {
        spun = std::hint::black_box(fnv1a_step(spun, &index.to_le_bytes()));
    }
    spun
}

/// A deterministic, dependency-free reference implementation of
/// `TextGenerationEngine`. Never loads a model, never performs a GPU or FFI
/// call, and never sleeps.
pub struct DeterministicEngine;

impl DeterministicEngine {
    /// Builds a new `DeterministicEngine`. Stateless — every call to
    /// `generate` is a pure function of its `GenerationRequest`.
    #[must_use]
    pub fn new() -> Self {
        Self
    }
}

impl Default for DeterministicEngine {
    fn default() -> Self {
        Self::new()
    }
}

impl TextGenerationEngine for DeterministicEngine {
    fn generate(
        &self,
        request: &GenerationRequest,
        sink: &mut dyn TokenSink,
    ) -> Result<GenerationSummary, EngineError> {
        let mut tokens_produced = 0u64;
        let mut stopped_early = false;

        for index in 0..request.max_tokens {
            let hash = token_hash(&request.prompt, index);
            // Burn the caller-configured CPU cost; the result is discarded
            // and never influences the emitted token's bytes.
            let _burned = spin(hash, index, request.cpu_spin_iterations);

            let token = Token {
                sequence: index,
                bytes: hash.to_le_bytes().to_vec(),
            };
            tokens_produced += 1;

            if sink.accept(token) == SinkVerdict::Stop {
                stopped_early = true;
                break;
            }
        }

        Ok(GenerationSummary {
            tokens_produced,
            stopped_early,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::DeterministicEngine;
    use crate::worker::local_infer::engine::port::{
        GenerationRequest, SinkVerdict, TextGenerationEngine, Token, TokenSink,
    };

    struct CollectingSink {
        tokens: Vec<Token>,
    }

    impl CollectingSink {
        fn new() -> Self {
            Self { tokens: Vec::new() }
        }
    }

    impl TokenSink for CollectingSink {
        fn accept(&mut self, token: Token) -> SinkVerdict {
            self.tokens.push(token);
            SinkVerdict::Continue
        }
    }

    struct StopAfter {
        remaining: u32,
    }

    impl TokenSink for StopAfter {
        fn accept(&mut self, _token: Token) -> SinkVerdict {
            if self.remaining == 0 {
                return SinkVerdict::Stop;
            }
            self.remaining -= 1;
            SinkVerdict::Continue
        }
    }

    fn request(prompt: &str, max_tokens: u64, cpu_spin_iterations: u32) -> GenerationRequest {
        GenerationRequest {
            prompt: prompt.to_string(),
            max_tokens,
            cpu_spin_iterations,
        }
    }

    /// Spec scenario "The reference engine produces an identical output
    /// sequence across repeated runs".
    #[test]
    fn same_request_produces_an_identical_token_sequence_across_two_runs() {
        let engine = DeterministicEngine::new();
        let req = request("a stable prompt", 5, 3);

        let mut first_run = CollectingSink::new();
        engine
            .generate(&req, &mut first_run)
            .expect("deterministic engine never rejects");

        let mut second_run = CollectingSink::new();
        engine
            .generate(&req, &mut second_run)
            .expect("deterministic engine never rejects");

        assert_eq!(first_run.tokens, second_run.tokens);
        assert_eq!(first_run.tokens.len(), 5);
    }

    /// Spec scenario "The per-token spin cost is caller-configured, not
    /// hardcoded": two requests differing only in `cpu_spin_iterations`
    /// must produce identical token content.
    #[test]
    fn spin_iteration_count_does_not_affect_token_content() {
        let engine = DeterministicEngine::new();
        let low_spin = request("same prompt, different cost", 4, 0);
        let high_spin = request("same prompt, different cost", 4, 10_000);

        let mut low_sink = CollectingSink::new();
        engine
            .generate(&low_spin, &mut low_sink)
            .expect("deterministic engine never rejects");

        let mut high_sink = CollectingSink::new();
        engine
            .generate(&high_spin, &mut high_sink)
            .expect("deterministic engine never rejects");

        assert_eq!(low_sink.tokens, high_sink.tokens);
    }

    /// Spec scenario "The engine stops immediately when the sink signals
    /// stop": with tokens remaining before the natural `max_tokens` limit.
    #[test]
    fn stops_immediately_on_sink_verdict_stop() {
        let engine = DeterministicEngine::new();
        let req = request("plenty of tokens left", 100, 1);
        let mut sink = StopAfter { remaining: 2 };

        let summary = engine
            .generate(&req, &mut sink)
            .expect("deterministic engine never rejects");

        assert!(summary.stopped_early);
        assert_eq!(summary.tokens_produced, 3);
    }

    /// Spec scenario "The reference engine performs no real inference and
    /// never sleeps": a source-inspection proxy test. Comment/doc lines are
    /// skipped first so the module's own "never llama.cpp" doc comment
    /// (which names the forbidden terms in prose) does not trip the check.
    #[test]
    fn source_names_no_real_inference_backend_and_never_sleeps() {
        let source = include_str!("reference.rs");
        // Scan only the production code above the test module — the test
        // module itself necessarily names these forbidden terms (this very
        // function's name included) to describe what it is checking for.
        let production_source = source
            .split_once("#[cfg(test)]")
            .map_or(source, |(production, _tests)| production);
        let forbidden = ["llama", "llama_cpp", "ggml", "candle", "sleep"];

        for line in production_source.lines() {
            let trimmed = line.trim_start();
            if trimmed.starts_with("//") {
                continue;
            }
            let lowercase = line.to_lowercase();
            for term in forbidden {
                assert!(
                    !lowercase.contains(term),
                    "reference engine source line must not mention `{term}` outside comments: {line:?}"
                );
            }
        }
    }
}
