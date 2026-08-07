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
// model artifacts. Since `worker-grpc-client-adapter`, `main.rs` always
// wires `WorkerKind::Ray` (task 3.8), so exercising the real dispatcher
// here means spawning the same real-TCP fake `tibios-ray` server
// `RayDispatch`'s conformance tests use (design.md D3, D4) and handing the
// binary its endpoint via `TIBIOS_RAY_ENDPOINT`. Under `llamacpp`, a
// feature-gated engine needing an external asset this environment cannot
// provide (e.g. `TIBIOS_LOCAL_INFER_MODEL_PATH` pointing at a real GGUF
// file, which CI does not set) is out of scope here — not because the
// binary is wrong, but because "does inference actually complete" belongs
// to that engine's own Tier-3 operator-run tests. Revisit this gate, in
// the same spirit, for every future local engine that depends on external
// artifacts.
#[cfg(not(feature = "llamacpp"))]
#[tokio::test]
async fn running_the_runtime_binary_prints_an_end_of_stream_event_and_a_completed_report() {
    let endpoint = runtime_worker_test_harness::spawn_fake_ray_server().await;

    // `Command::output()` blocks the calling OS thread; on the default
    // current-thread `#[tokio::test]` runtime that thread is also the only
    // one polling the fake server's `tokio::spawn`ed background task, so
    // calling it directly here would starve that task and the child
    // process would hang waiting for a `SubmitJob` response that never
    // comes. `spawn_blocking` runs it on a separate thread instead.
    let output = tokio::task::spawn_blocking(move || {
        Command::new(env!("CARGO_BIN_EXE_runtime"))
            .env("TIBIOS_RAY_ENDPOINT", endpoint)
            .output()
    })
    .await
    .expect("the blocking task must not panic")
    .expect("the runtime binary must be spawnable");

    assert!(
        output.status.success(),
        "the runtime binary must exit successfully, stderr:\n{}",
        String::from_utf8_lossy(&output.stderr)
    );

    let stdout = String::from_utf8(output.stdout).expect("stdout must be valid UTF-8");

    // The fake `tibios-ray` server (`runtime-worker-test-harness`) emits no
    // business events — only the terminal report — so this only asserts
    // what `runtime-composition-root/spec.md`'s scenario actually requires:
    // draining events (zero, here) and printing a terminal report.
    assert!(
        stdout.contains("Completed"),
        "expected stdout to contain a `Completed` terminal report, got:\n{stdout}"
    );
}
