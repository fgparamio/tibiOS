// Generated from `proto/` by `build.rs` via `tonic_build`'s single-file
// `include_file(...)` mode (design D5, D8). Lint relaxation for this
// generated content lives on the `mod grpc;` declaration in
// `adapters/mod.rs`, not here.
include!(concat!(env!("OUT_DIR"), "/tibios_worker_grpc.rs"));

mod convert;
mod pending_submission;
mod ray_worker;

// The only item this private tree ever surfaces upward: an opaque
// Composition-Root factory, re-exported one level at a time up through
// `adapters/mod.rs` and `lib.rs` (`runtime-worker/spec.md`'s
// Composition-Root factory exception). Never `pub use ray_worker::*` and
// never the `RayWorker` type itself.
pub use ray_worker::new_ray_worker;
