//! Smoke test (design.md D10, Slice 3): `runtime` stays binary-only, so this
//! integration test cannot import its modules — it instead runs the actual
//! built binary via `Command::new(env!("CARGO_BIN_EXE_runtime"))` and
//! inspects its stdout, proving the real `cargo run -p runtime` success
//! criterion end-to-end, not a library approximation
//! (`runtime-composition-root/spec.md` — "Runtime Wires One Real Execution
//! End-To-End", scenario "cargo run -p runtime prints a terminal report").

#[cfg(not(feature = "llamacpp"))]
use std::process::Command;

// This end-to-end smoke test requires a production engine with external
// model artifacts. `main.rs` hardcodes `WorkerKind::LocalInfer`, so the
// spawned binary intentionally runs the real dispatcher against whatever
// engine `default_engine()` selects for the active feature set. When a
// feature-gated engine needs an external asset this environment cannot
// provide (e.g. `llamacpp` needs `TIBIOS_LOCAL_INFER_MODEL_PATH` pointing
// at a real GGUF file, which CI does not set), the binary cannot complete
// an execution and this test is out of scope here — not because the
// binary is wrong, but because "does inference actually complete" belongs
// to that engine's own Tier-3 operator-run tests. Revisit this gate, in
// the same spirit, for every future local engine that depends on external
// artifacts.
#[cfg(not(feature = "llamacpp"))]
#[test]
fn running_the_runtime_binary_prints_an_end_of_stream_event_and_a_completed_report() {
    let output = Command::new(env!("CARGO_BIN_EXE_runtime"))
        .output()
        .expect("the runtime binary must be spawnable");

    assert!(
        output.status.success(),
        "the runtime binary must exit successfully, stderr:\n{}",
        String::from_utf8_lossy(&output.stderr)
    );

    let stdout = String::from_utf8(output.stdout).expect("stdout must be valid UTF-8");

    assert!(
        stdout.contains("EndOfStream"),
        "expected stdout to contain an `EndOfStream` event, got:\n{stdout}"
    );
    assert!(
        stdout.contains("Completed"),
        "expected stdout to contain a `Completed` terminal report, got:\n{stdout}"
    );
}
