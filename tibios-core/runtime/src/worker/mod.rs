//! The Composition Root's own concrete Worker wiring — owned exclusively by
//! `runtime`, never `runtime-worker` (`runtime-worker/spec.md` forbids any
//! `tokio::` path there). This module tree is where `runtime`'s sole
//! `tokio` dependency is actually used.

mod channel;

// `#[allow(unused_imports)]`: not yet used from `main.rs` — wiring lands in
// PR 3 of this change (`design.md` D9). Remove this allow there.
#[allow(unused_imports)]
pub use channel::MpscExecutionChannel;
