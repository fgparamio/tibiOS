//! `MpscExecutionChannel`: the Composition Root's sole concrete
//! `ExecutionChannel` implementation, backed by a real
//! `tokio::sync::mpsc::Sender` (`worker-inprocess-adapter/spec.md` —
//! "The In-Process Worker Performs Real Async Work Through A Real
//! Channel").

use runtime_worker::{ChannelClosed, ExecutionChannel, ExecutionEvent};
use tokio::sync::mpsc;

/// Publishes `ExecutionEvent`s over a bounded `tokio::sync::mpsc` channel.
/// Owns the `Sender` half only — never clones or leaks it — so dropping the
/// last live `MpscExecutionChannel` closes the channel deterministically
/// (`design.md` D9: `main.rs` must move only the `Sender` in, never a
/// clone).
///
/// `#[allow(dead_code)]`: not yet constructed from `main.rs` — that wiring
/// lands in PR 3 of this change (`design.md` D9). Remove this allow there.
#[allow(dead_code)]
pub struct MpscExecutionChannel {
    sender: mpsc::Sender<ExecutionEvent>,
}

impl MpscExecutionChannel {
    /// Builds an `MpscExecutionChannel` from the `Sender` half of a
    /// `tokio::sync::mpsc::channel`.
    #[must_use]
    #[allow(dead_code)] // see the struct's doc comment
    pub const fn new(sender: mpsc::Sender<ExecutionEvent>) -> Self {
        Self { sender }
    }
}

impl ExecutionChannel for MpscExecutionChannel {
    async fn emit(&self, event: ExecutionEvent) -> Result<(), ChannelClosed> {
        self.sender.send(event).await.map_err(|_| ChannelClosed)
    }
}

#[cfg(test)]
mod tests {
    use runtime_worker::{ExecutionChannel, ExecutionEvent, OutputChunk};
    use tokio::sync::mpsc;

    use super::MpscExecutionChannel;

    fn sample_event(sequence: u64) -> ExecutionEvent {
        ExecutionEvent::OutputChunk(OutputChunk {
            data: vec![1, 2, 3],
            sequence,
        })
    }

    #[tokio::test]
    async fn emit_delivers_the_event_to_the_receiver() {
        let (sender, mut receiver) = mpsc::channel(4);
        let channel = MpscExecutionChannel::new(sender);

        let result = channel.emit(sample_event(0)).await;

        assert!(result.is_ok());
        assert_eq!(receiver.recv().await, Some(sample_event(0)));
    }

    #[tokio::test]
    async fn emit_after_receiver_drop_returns_channel_closed() {
        let (sender, receiver) = mpsc::channel(4);
        let channel = MpscExecutionChannel::new(sender);
        drop(receiver);

        let result = channel.emit(sample_event(0)).await;

        assert_eq!(result, Err(runtime_worker::ChannelClosed));
    }

    #[tokio::test]
    async fn capacity_one_backpressure_pends_until_a_recv_makes_room() {
        let (sender, mut receiver) = mpsc::channel(1);
        let channel = MpscExecutionChannel::new(sender);

        // Fill the sole slot; the channel now has zero spare capacity.
        channel
            .emit(sample_event(0))
            .await
            .expect("first emit into an empty capacity-1 channel must succeed");

        // A second emit cannot complete until the first event is drained —
        // race it against `recv` via `select!` and assert `recv` wins.
        tokio::select! {
            biased;
            received = receiver.recv() => {
                assert_eq!(received, Some(sample_event(0)));
            }
            _ = channel.emit(sample_event(1)) => {
                panic!("emit must not complete before recv drains the full capacity-1 channel");
            }
        }

        // Now that the slot is free, the pending second emit can proceed.
        channel
            .emit(sample_event(1))
            .await
            .expect("emit after recv freed capacity must succeed");
        assert_eq!(receiver.recv().await, Some(sample_event(1)));
    }
}
