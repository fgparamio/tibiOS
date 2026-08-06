//! Integrity of the vendored `proto/` tree, guarded by
//! `PROTO_MANIFEST.sha256`. Design: `worker-grpc-adapter/design.md` D8.
//!
//! Two invariants, deliberately separated: *integrity* (does the vendored
//! copy match its own checksum manifest?) always runs; *freshness* (has the
//! umbrella repo moved?) only runs when the umbrella tree is reachable.

use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

/// `crates/runtime-worker` -> the workspace root (`tibios-core/`).
fn workspace_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .expect("crates/runtime-worker has two ancestors up to the workspace root")
        .to_path_buf()
}

fn proto_root() -> PathBuf {
    workspace_root().join("proto")
}

fn manifest_path() -> PathBuf {
    proto_root().join("PROTO_MANIFEST.sha256")
}

/// Recursively collect every `.proto` file under `root`, returned as paths
/// relative to `root`, using `/`-separated components (matching the
/// manifest's `shasum -a 256` format regardless of host OS).
fn find_proto_files_relative_to(root: &Path) -> BTreeSet<String> {
    let mut found = BTreeSet::new();
    walk(root, root, &mut found);
    found
}

fn walk(root: &Path, dir: &Path, found: &mut BTreeSet<String>) {
    let entries = std::fs::read_dir(dir)
        .unwrap_or_else(|e| panic!("failed to read directory {}: {e}", dir.display()));
    for entry in entries {
        let entry = entry.expect("directory entry should be readable");
        let path = entry.path();
        if path.is_dir() {
            walk(root, &path, found);
        } else if path.extension().is_some_and(|ext| ext == "proto") {
            let relative = path
                .strip_prefix(root)
                .expect("walked path is under root")
                .components()
                .map(|c| c.as_os_str().to_string_lossy().into_owned())
                .collect::<Vec<_>>()
                .join("/");
            found.insert(relative);
        }
    }
}

/// Parse `PROTO_MANIFEST.sha256`'s `shasum -a 256` format: one line per
/// file, `<64-hex><two spaces><path relative to proto/>`.
fn parse_manifest() -> Vec<(String, String)> {
    let contents = std::fs::read_to_string(manifest_path())
        .unwrap_or_else(|e| panic!("failed to read {}: {e}", manifest_path().display()));
    contents
        .lines()
        .filter(|line| !line.trim().is_empty())
        .map(|line| {
            let (digest, path) = line.split_once("  ").unwrap_or_else(|| {
                panic!("manifest line does not match `<hex><two spaces><path>`: {line:?}")
            });
            (digest.to_string(), path.to_string())
        })
        .collect()
}

fn sha256_hex(path: &Path) -> String {
    let bytes =
        std::fs::read(path).unwrap_or_else(|e| panic!("failed to read {}: {e}", path.display()));
    let digest = Sha256::digest(&bytes);
    digest.iter().map(|b| format!("{b:02x}")).collect()
}

#[test]
fn manifest_covers_every_vendored_proto_file() {
    let on_disk = find_proto_files_relative_to(&proto_root());
    let manifest: BTreeSet<String> = parse_manifest().into_iter().map(|(_, path)| path).collect();

    let on_disk_only: Vec<_> = on_disk.difference(&manifest).collect();
    let manifest_only: Vec<_> = manifest.difference(&on_disk).collect();

    assert!(
        on_disk_only.is_empty() && manifest_only.is_empty(),
        "PROTO_MANIFEST.sha256 drifted from proto/: on-disk-but-unlisted={on_disk_only:?}, \
         listed-but-missing={manifest_only:?}. Regenerate with: \
         `cd proto && fd -e proto -t f . | sort | xargs shasum -a 256 > PROTO_MANIFEST.sha256`"
    );
}

#[test]
fn vendored_proto_digests_match_the_manifest() {
    let mut mismatches = Vec::new();
    for (expected_digest, relative_path) in parse_manifest() {
        let file = proto_root().join(&relative_path);
        let actual_digest = sha256_hex(&file);
        if actual_digest != expected_digest {
            mismatches.push(format!(
                "{relative_path}: manifest={expected_digest} actual={actual_digest}"
            ));
        }
    }
    assert!(
        mismatches.is_empty(),
        "vendored proto file(s) do not match PROTO_MANIFEST.sha256:\n{}\n\
         Regenerate with: `cd proto && fd -e proto -t f . | sort | xargs shasum -a 256 > PROTO_MANIFEST.sha256`",
        mismatches.join("\n")
    );
}

#[test]
fn vendored_proto_matches_umbrella_source_when_present() {
    let umbrella_root = std::env::var_os("TIBIOS_PROTO_UPSTREAM")
        .map(PathBuf::from)
        .unwrap_or_else(|| workspace_root().join("..").join("proto"));

    if !umbrella_root.is_dir() {
        eprintln!(
            "vendored_proto_matches_umbrella_source_when_present: umbrella proto/ not found at \
             {} — skipping freshness check (integrity is still guarded by the other two tests)",
            umbrella_root.display()
        );
        return;
    }

    let vendored = find_proto_files_relative_to(&proto_root());
    let umbrella = find_proto_files_relative_to(&umbrella_root);

    let vendored_only: Vec<_> = vendored.difference(&umbrella).collect();
    let umbrella_only: Vec<_> = umbrella.difference(&vendored).collect();
    assert!(
        vendored_only.is_empty() && umbrella_only.is_empty(),
        "vendored proto/ and umbrella proto/ list different files: vendored-only={vendored_only:?}, \
         umbrella-only={umbrella_only:?}"
    );

    let mut mismatches = Vec::new();
    for relative_path in &vendored {
        let vendored_file = proto_root().join(relative_path);
        let umbrella_file = umbrella_root.join(relative_path);
        let vendored_bytes = std::fs::read(&vendored_file)
            .unwrap_or_else(|e| panic!("failed to read {}: {e}", vendored_file.display()));
        let umbrella_bytes = std::fs::read(&umbrella_file)
            .unwrap_or_else(|e| panic!("failed to read {}: {e}", umbrella_file.display()));
        if vendored_bytes != umbrella_bytes {
            mismatches.push(relative_path.clone());
        }
    }
    assert!(
        mismatches.is_empty(),
        "vendored proto file(s) differ from the umbrella source byte-for-byte: {mismatches:?}. \
         Re-vendor, regenerate PROTO_MANIFEST.sha256, and commit both."
    );
}
