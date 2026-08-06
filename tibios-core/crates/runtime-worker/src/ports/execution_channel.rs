//! `ExecutionChannel`: the Inbound Port parameter a Worker uses to publish
//! `ExecutionEvent`s while performing one execution (`18-worker-model.md:88`;
//! `worker-inbound-port` capability).

use crate::execution::event::ExecutionEvent;

/// Publishes `ExecutionEvent`s produced by one execution, one at a time.
///
/// `Send + 'static` — not `Send + Sync` — because a `WorkerService::execute`
/// call takes its `ExecutionChannel` by value (design.md D9): the Worker
/// owns the one instance for the lifetime of that one execution, so no
/// concurrent-access bound is required beyond what moving it across a
/// thread (`local-infer`'s mandated `spawn_blocking`) demands.
///
/// `emit` is an RPITIT with an explicit `+ Send` bound — written as
/// `impl Future<..> + Send`, never a bare `async fn` — because a bare
/// `async fn` in a trait produces a Future with no bound at all, which is
/// unusable from a `spawn_blocking`-moved or otherwise `Send`-required
/// context (design.md D9). This is the same reason `WorkerService`'s three
/// methods are written the same way.
pub trait ExecutionChannel: Send + 'static {
    /// Publishes one `ExecutionEvent`. Returns `Err(ChannelClosed)` if the
    /// Runtime's `Receiver` half is gone; a closed channel never prevents
    /// the Worker from reporting its outcome — `execute`'s return value
    /// (`ExecutionReport`) is unaffected either way, and a Worker MAY ignore
    /// a failed `emit` and continue running to a normal, fully-reported
    /// completion (design.md D9 Consequences).
    fn emit(
        &self,
        event: ExecutionEvent,
    ) -> impl core::future::Future<Output = Result<(), ChannelClosed>> + Send;
}

/// The Runtime's `Receiver` half of an `ExecutionChannel` is gone: further
/// `emit` calls cannot be delivered. This is never fatal to the execution
/// itself — the Worker still owes an `ExecutionReport` via `execute`'s
/// return value, so a closed channel never prevents reporting (design.md D9
/// Consequences). A Worker MAY instead choose to abort after a failed
/// `emit`; `impl From<ChannelClosed> for WorkerError` (`error.rs`) exists
/// for exactly that choice.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ChannelClosed;

impl core::fmt::Display for ChannelClosed {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        write!(f, "the execution channel's receiver has been dropped")
    }
}

#[cfg(test)]
mod tests {
    use super::ChannelClosed;

    #[test]
    fn channel_closed_display_is_not_empty() {
        let closed = ChannelClosed;
        assert!(!format!("{closed}").is_empty());
    }

    #[test]
    fn channel_closed_is_copy_and_compares_equal() {
        let a = ChannelClosed;
        let b = a;
        assert_eq!(a, b);
    }
}
