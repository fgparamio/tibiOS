# Vendored Worker gRPC Contract

This directory is a **manually vendored, byte-identical copy** of the frozen
`.proto` contract owned by the umbrella repository at `../TibiOS/proto/`
(relative to this repo's parent directory). `tibios-core` is a downstream
consumer, not the source of truth.

- **Upstream path**: `../TibiOS/proto/tibios/{primitives/v1/identity.proto,worker/v1/worker.proto}`
- **Vendoring is manual and unchecked at copy-time.** Nobody verifies, at the
  moment a contributor runs `cp`, that the copy matches upstream — that check
  happens later, at test time, via `crates/runtime-worker/tests/proto_drift.rs`
  (`vendored_proto_matches_umbrella_source_when_present`), and only when the
  umbrella checkout is present alongside this one.
- The two facts that **are** checked, always, in any clone: every vendored
  `.proto` file is listed in `PROTO_MANIFEST.sha256`, and every listed digest
  matches the file's current contents. That is an integrity guarantee ("is
  this the copy that was reviewed?"), not a freshness guarantee ("has
  upstream moved?").

## Installing `protoc`

`crates/runtime-worker/build.rs` requires the system protobuf compiler to
generate Rust code from the vendored `.proto` files. Install it for your OS:

```sh
# macOS
brew install protobuf

# Debian / Ubuntu
apt-get install -y protobuf-compiler
```

If `protoc` is installed somewhere not on `PATH`, point at it explicitly:

```sh
PROTOC=/path/to/protoc cargo check -p runtime-worker
```

## Regenerating / verifying the manifest

No project tooling is required — these are plain `shasum` commands run from
this directory:

```sh
# Regenerate the manifest after vendoring new or updated .proto files
cd proto && fd -e proto -t f . | sort | xargs shasum -a 256 > PROTO_MANIFEST.sha256

# Verify the vendored tree matches the manifest
cd proto && shasum -a 256 -c PROTO_MANIFEST.sha256
```

## Re-vendoring the contract

Updating the contract is a **three-step, reviewable ritual**. Do all three in
the same commit so the diff shows the `.proto` change and the digest change
together:

1. Re-vendor: copy the updated file(s) from `../TibiOS/proto/` into the
   matching path under this `proto/` tree.
2. Regenerate the manifest (see command above).
3. Commit both the vendored file(s) and `PROTO_MANIFEST.sha256` together.
