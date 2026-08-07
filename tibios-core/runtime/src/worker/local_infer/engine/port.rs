//! The engine port (`worker-local-infer-adapter/spec.md` — "The Engine Port
//! Is Wholly Synchronous, Std-Only..."; design.md D6): a plain synchronous
//! trait, `std`-only, dyn-compatible, that knows nothing about
//! `runtime-worker` types. All policy (cancellation, deadlines, channel
//! closure) lives in the adapter's `TokenSink` implementation, reached
//! solely through `SinkVerdict` — the engine only ever asks "keep going?"
//! and stops the instant the answer is no.

/// One request to generate tokens from `prompt`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GenerationRequest {
    /// The text prompt driving generation.
    pub prompt: String,
    /// The maximum number of tokens to produce before stopping naturally.
    pub max_tokens: u64,
    /// Caller-supplied per-token CPU cost (spin-loop iteration count).
    /// Governs how much work a reference/placeholder engine burns per
    /// token; a real engine is free to ignore it.
    pub cpu_spin_iterations: u32,
}

/// One generated token: its position in the sequence and its raw content.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Token {
    /// Zero-based position of this token within the generation.
    pub sequence: u64,
    /// The token's raw byte content.
    pub bytes: Vec<u8>,
}

/// What a completed (or early-stopped) generation produced.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GenerationSummary {
    /// How many tokens were actually produced.
    pub tokens_produced: u64,
    /// Whether generation stopped before `max_tokens` because the sink
    /// returned `SinkVerdict::Stop`.
    pub stopped_early: bool,
}

/// Every failure a `TextGenerationEngine::generate` call can return.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum EngineError {
    /// The engine rejected the request outright (never started
    /// generating). Carries a human-readable reason. `DeterministicEngine`
    /// never returns this variant; it exists for a real engine (e.g. a
    /// model that fails to load) and is already handled by the adapter side
    /// (`local_infer/mod.rs`).
    #[allow(dead_code)]
    Rejected(String),
}

impl core::fmt::Display for EngineError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            Self::Rejected(reason) => write!(f, "engine rejected the request: {reason}"),
        }
    }
}

/// The adapter's answer to "keep going?" after each token — the *only*
/// channel through which cancellation, deadlines, and channel closure ever
/// reach the engine (design.md D6).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SinkVerdict {
    /// Keep generating.
    Continue,
    /// Stop immediately; produce no further token.
    Stop,
}

/// Receives tokens as the engine produces them and decides whether
/// generation should continue. All cancellation, deadline, and
/// channel-closure policy lives here, in the adapter — never in the engine
/// itself.
pub trait TokenSink {
    /// Accepts one freshly produced token and returns whether the engine
    /// should keep generating.
    fn accept(&mut self, token: Token) -> SinkVerdict;
}

/// A synchronous text-generation engine. The sole generation method is an
/// ordinary function — not `async fn`, and it returns no `Future` — so it
/// is callable from a plain thread with no async runtime present
/// (`worker-local-infer-adapter/spec.md`).
///
/// `&mut dyn TokenSink` (rather than a generic parameter) keeps this trait
/// dyn-compatible, so an adapter can hold `Arc<dyn TextGenerationEngine>`
/// (design.md D6).
pub trait TextGenerationEngine: Send + Sync {
    /// Generates tokens for `request`, handing each one to `sink` and
    /// stopping the instant `sink` returns `SinkVerdict::Stop` (or
    /// `request.max_tokens` is reached, whichever comes first).
    fn generate(
        &self,
        request: &GenerationRequest,
        sink: &mut dyn TokenSink,
    ) -> Result<GenerationSummary, EngineError>;
}

#[cfg(test)]
mod tests {
    use super::{
        EngineError, GenerationRequest, GenerationSummary, SinkVerdict, TextGenerationEngine,
        Token, TokenSink,
    };

    /// A trivial `TextGenerationEngine` that emits `max_tokens` tokens
    /// carrying their own index, stopping early if the sink says so. Exists
    /// only to prove the port's *shape* (sync, dyn-compatible, callable with
    /// no runtime) — `DeterministicEngine` (Phase 1.2) is the real reference
    /// implementation.
    struct EchoEngine;

    impl TextGenerationEngine for EchoEngine {
        fn generate(
            &self,
            request: &GenerationRequest,
            sink: &mut dyn TokenSink,
        ) -> Result<GenerationSummary, EngineError> {
            for index in 0..request.max_tokens {
                let token = Token {
                    sequence: index,
                    bytes: vec![index as u8],
                };
                if sink.accept(token) == SinkVerdict::Stop {
                    return Ok(GenerationSummary {
                        tokens_produced: index + 1,
                        stopped_early: true,
                    });
                }
            }
            Ok(GenerationSummary {
                tokens_produced: request.max_tokens,
                stopped_early: false,
            })
        }
    }

    struct CollectingSink {
        tokens: Vec<Token>,
    }

    impl TokenSink for CollectingSink {
        fn accept(&mut self, token: Token) -> SinkVerdict {
            self.tokens.push(token);
            SinkVerdict::Continue
        }
    }

    /// Spec scenario "The engine port is callable with no async runtime
    /// present": a plain `#[test]` (no `#[tokio::test]`) drives the engine
    /// to completion directly.
    #[test]
    fn generate_is_callable_with_no_async_runtime_present() {
        let engine = EchoEngine;
        let request = GenerationRequest {
            prompt: "hello".to_string(),
            max_tokens: 3,
            cpu_spin_iterations: 0,
        };
        let mut sink = CollectingSink { tokens: Vec::new() };

        let summary = engine
            .generate(&request, &mut sink)
            .expect("EchoEngine never rejects a request");

        assert_eq!(summary.tokens_produced, 3);
        assert!(!summary.stopped_early);
        assert_eq!(sink.tokens.len(), 3);
        assert_eq!(sink.tokens[0].sequence, 0);
        assert_eq!(sink.tokens[2].sequence, 2);
    }

    /// Spec scenario "The engine port's generation method is not async and
    /// returns no Future": binding the call's result directly to a
    /// concrete, non-`Future` type is a compile-shape assertion — if
    /// `generate` were `async fn`, this line would fail to type-check
    /// without a `.await`, which no runtime here could drive anyway.
    #[test]
    fn generate_returns_a_result_directly_not_a_future() {
        fn assert_is_a_result<T, E>(_value: &Result<T, E>) {}

        let engine = EchoEngine;
        let request = GenerationRequest {
            prompt: "x".to_string(),
            max_tokens: 1,
            cpu_spin_iterations: 0,
        };
        let mut sink = CollectingSink { tokens: Vec::new() };

        let outcome = engine.generate(&request, &mut sink);
        assert_is_a_result(&outcome);
        assert!(outcome.is_ok());
    }
}
