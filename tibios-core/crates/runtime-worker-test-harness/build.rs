//! Codegen entry point for this harness's own copy of the Worker gRPC
//! contract — compiled independently from `runtime-worker`'s copy (own
//! `OUT_DIR`, own generated types), exactly mirroring `runtime-worker/build.rs`.
//! Deliberate duplication, not a shared dependency: this crate must never
//! reach into `runtime-worker`'s private generated module tree.

use std::env;
use std::path::{Path, PathBuf};

/// The name of the file `include_file(...)` writes into `OUT_DIR`. Must
/// match the `include!` in `src/lib.rs`.
const GENERATED_INCLUDE_FILE: &str = "tibios_worker_grpc.rs";

fn main() {
    println!("cargo:rerun-if-env-changed=PROTOC");
    preflight_protoc();

    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let proto_root = manifest_dir.join("..").join("..").join("proto");

    let identity_proto = proto_root
        .join("tibios")
        .join("primitives")
        .join("v1")
        .join("identity.proto");
    let worker_proto = proto_root
        .join("tibios")
        .join("worker")
        .join("v1")
        .join("worker.proto");
    let manifest = proto_root.join("PROTO_MANIFEST.sha256");

    println!("cargo:rerun-if-changed={}", identity_proto.display());
    println!("cargo:rerun-if-changed={}", worker_proto.display());
    println!("cargo:rerun-if-changed={}", manifest.display());

    tonic_build::configure()
        .build_server(true)
        .compile_well_known_types(true)
        .include_file(GENERATED_INCLUDE_FILE)
        .compile_protos(&[identity_proto, worker_proto], &[proto_root])
        .expect(
            "failed to compile the Worker gRPC contract from proto/ — see the \
             underlying protoc/prost error above",
        );
}

/// Fail fast, with an actionable message, if `protoc` is not reachable —
/// either via the `PROTOC` env var or on `PATH`.
fn preflight_protoc() {
    if env::var_os("PROTOC").is_some() {
        return;
    }
    if path_contains_protoc() {
        return;
    }
    panic!(
        "runtime-worker-test-harness needs the protobuf compiler (`protoc`) to \
         generate the Worker gRPC contract from proto/.\n\
         Install it:\n\
         \x20\x20macOS:          brew install protobuf\n\
         \x20\x20Debian/Ubuntu:  apt-get install -y protobuf-compiler\n\
         Or point at an existing binary:\n\
         \x20\x20PROTOC=/path/to/protoc cargo check -p runtime-worker-test-harness\n\
         Background: proto/README.md"
    );
}

/// Scan `PATH` for a `protoc` (or `protoc.exe`) executable.
fn path_contains_protoc() -> bool {
    let Some(path_var) = env::var_os("PATH") else {
        return false;
    };
    let exe_name = if cfg!(windows) {
        "protoc.exe"
    } else {
        "protoc"
    };
    env::split_paths(&path_var).any(|dir| is_executable_file(&dir.join(exe_name)))
}

fn is_executable_file(path: &Path) -> bool {
    path.is_file()
}
