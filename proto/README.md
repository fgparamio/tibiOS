# proto/

Source of truth for the TibiOS Worker gRPC Contract.

This directory defines the protocol shared by:

- [`tibios-core`](../tibios-core) (Rust) — vendors a copy under `tibios-core/proto/`, generated from here via `build.rs`.
- [`tibios-ray`](../tibios-ray) (Python) — the other side of the same contract.

Neither repo owns this directory; both build against the same frozen definition so neither language's tooling or release cadence leaks into the other's.

See `tibios-core/proto/README.md` for the vendoring/re-vendoring ritual (manual copy + `PROTO_MANIFEST.sha256` integrity check).
