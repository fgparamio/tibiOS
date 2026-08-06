//! `ExecutionEvent` and its six payloads: the values a Worker publishes
//! through its `ExecutionChannel` while performing one execution
//! (`18-worker-model.md:88`). Each payload is a Worker-owned domain type,
//! never the generated wire struct — the private-mirror debt this change
//! retires (`worker-wire-adapter/spec.md`).

use std::collections::BTreeMap;

use runtime_primitives::ObjectId;

/// One chunk of raw output produced during an execution, carried with its
/// sequence number so an out-of-order transport can still be reassembled
/// correctly by the Runtime.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OutputChunk {
    /// The raw output bytes for this chunk.
    pub data: Vec<u8>,
    /// This chunk's position in the output stream, starting at zero.
    pub sequence: u64,
}

/// A human-readable progress update emitted while an execution is running.
#[derive(Debug, Clone, PartialEq)]
pub struct Progress {
    /// How much of the execution is complete, in the range `0.0..=1.0`.
    pub fraction_complete: f64,
    /// A human-readable description of the current step.
    pub message: String,
}

/// A non-fatal warning surfaced during an execution. Distinct from a
/// failure: the execution continues after emitting one.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Warning {
    /// The human-readable warning text.
    pub message: String,
}

/// A checkpoint the Worker created during an execution, naming the
/// already-resolved Logical Object it wrote the checkpoint to.
/// `checkpoint_object_id` has no meaningful empty/absent domain variant, so
/// it is a non-optional `ObjectId` here, mirroring `convert.rs`'s existing
/// resolution of the wire's `Option`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CheckpointCreated {
    /// The identity of the Logical Object the checkpoint was written to.
    pub checkpoint_object_id: ObjectId,
}

/// A snapshot of execution metrics, keyed by metric name. `BTreeMap`, not
/// `HashMap`, so iteration order is stable and equality is reproducible in
/// tests (`18-worker-model.md:13` — "Execution is deterministic"; design.md
/// D10 Consequences).
#[derive(Debug, Clone, PartialEq)]
pub struct MetricsSnapshot {
    /// The metrics carried by this snapshot, keyed by metric name.
    pub metrics: BTreeMap<String, f64>,
}

/// Marks the end of the event stream for one execution. Carries no data —
/// the terminal `ExecutionReport` follows separately, as `execute`'s return
/// value, never as a further event (design.md D10 Consequences).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct EndOfStream;

/// The closed set of values a Worker publishes through its
/// `ExecutionChannel` while performing one execution. Exactly six variants,
/// corresponding one-to-one to the six arms of the frozen wire contract's
/// `ExecutionEvent` oneof (`worker.proto`). This enum MUST NOT gain a
/// seventh variant and MUST NOT collapse or merge any of the six
/// (`runtime-worker/spec.md` — "ExecutionEvent Is A Closed Six-Arm Enum").
#[derive(Debug, Clone, PartialEq)]
pub enum ExecutionEvent {
    /// A chunk of raw output.
    OutputChunk(OutputChunk),
    /// A progress update.
    Progress(Progress),
    /// A non-fatal warning.
    Warning(Warning),
    /// A checkpoint was created.
    CheckpointCreated(CheckpointCreated),
    /// A snapshot of execution metrics.
    MetricsSnapshot(MetricsSnapshot),
    /// The event stream has ended.
    EndOfStream(EndOfStream),
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use runtime_primitives::ObjectId;

    use super::{
        CheckpointCreated, EndOfStream, ExecutionEvent, MetricsSnapshot, OutputChunk, Progress,
        Warning,
    };

    /// Exhaustive match over `ExecutionEvent`'s variants: a seventh arm
    /// added later breaks this build (`runtime-worker/spec.md` — "ExecutionEvent
    /// Is A Closed Six-Arm Enum").
    fn describe(event: &ExecutionEvent) -> &'static str {
        match event {
            ExecutionEvent::OutputChunk(_) => "output_chunk",
            ExecutionEvent::Progress(_) => "progress",
            ExecutionEvent::Warning(_) => "warning",
            ExecutionEvent::CheckpointCreated(_) => "checkpoint_created",
            ExecutionEvent::MetricsSnapshot(_) => "metrics_snapshot",
            ExecutionEvent::EndOfStream(_) => "end_of_stream",
        }
    }

    #[test]
    fn execution_event_matches_exhaustively_over_all_six_variants() {
        let events = vec![
            ExecutionEvent::OutputChunk(OutputChunk {
                data: vec![1, 2, 3],
                sequence: 0,
            }),
            ExecutionEvent::Progress(Progress {
                fraction_complete: 0.5,
                message: "halfway".to_string(),
            }),
            ExecutionEvent::Warning(Warning {
                message: "careful".to_string(),
            }),
            ExecutionEvent::CheckpointCreated(CheckpointCreated {
                checkpoint_object_id: ObjectId::new(),
            }),
            ExecutionEvent::MetricsSnapshot(MetricsSnapshot {
                metrics: BTreeMap::new(),
            }),
            ExecutionEvent::EndOfStream(EndOfStream),
        ];

        let described: Vec<&'static str> = events.iter().map(describe).collect();
        assert_eq!(
            described,
            vec![
                "output_chunk",
                "progress",
                "warning",
                "checkpoint_created",
                "metrics_snapshot",
                "end_of_stream",
            ]
        );
    }

    #[test]
    fn metrics_snapshot_preserves_insertion_via_btreemap_ordering() {
        let mut metrics = BTreeMap::new();
        metrics.insert("a".to_string(), 1.0);
        metrics.insert("b".to_string(), 2.0);
        let snapshot = MetricsSnapshot {
            metrics: metrics.clone(),
        };
        assert_eq!(snapshot.metrics, metrics);
        assert_eq!(snapshot.metrics.keys().collect::<Vec<_>>(), vec!["a", "b"]);
    }
}
