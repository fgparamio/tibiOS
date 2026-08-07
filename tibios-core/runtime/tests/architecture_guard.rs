//! Architecture Guard — machine-checks two invariant kinds: (1) the
//! workspace's real dependency graph (workspace-crate edges AND per-crate
//! external-crate allowlists) matches `design.md`'s Allowed Edge Matrix and
//! `EXTERNAL_ALLOWED` table, per the `workspace-manifest` and
//! `runtime-composition-root` specs; and (2) `runtime-worker`'s generated
//! gRPC transport code stays contained inside its private `src/adapters/`
//! module tree and never leaks into its public API, per
//! `openspec/changes/worker-grpc-adapter/design.md` D6-D7.
//!
//! `runtime` hosts this test because it already legitimately depends on
//! every other crate (the sole deliberate exception to the narrow-dependency
//! rule), so no additional crate is created just to read `cargo metadata`.

use std::collections::BTreeSet;

use cargo_metadata::{DependencyKind, MetadataCommand};

/// `p` = `runtime-primitives`; every other name is `runtime-<domain>`.
/// This table IS the Allowed Edge Matrix from `design.md` — changing it is
/// a deliberate, reviewed architectural edit, not a quick fix to a red test.
const ALLOWED: &[(&str, &[&str])] = &[
    ("runtime-primitives", &[]),
    ("runtime-object", &["runtime-primitives"]),
    (
        "runtime-scheduler",
        &["runtime-primitives", "runtime-object"],
    ),
    (
        "runtime-allocation",
        &["runtime-primitives", "runtime-scheduler", "runtime-object"],
    ),
    (
        "runtime-admission",
        &["runtime-primitives", "runtime-state"],
    ),
    (
        "runtime-worker",
        &["runtime-primitives", "runtime-allocation", "runtime-object"],
    ),
    ("runtime-network", &["runtime-primitives"]),
    ("runtime-storage", &["runtime-primitives"]),
    ("runtime-security", &["runtime-primitives"]),
    ("runtime-observability", &["runtime-primitives"]),
    (
        "runtime-state",
        &[
            "runtime-primitives",
            "runtime-object",
            "runtime-scheduler",
            "runtime-network",
        ],
    ),
    (
        "runtime-replication",
        &["runtime-primitives", "runtime-object", "runtime-storage"],
    ),
    ("runtime-deployment", &["runtime-primitives"]),
    (
        "runtime-api",
        &[
            "runtime-primitives",
            "runtime-admission",
            "runtime-object",
            "runtime-state",
            "runtime-allocation",
            "runtime-storage",
            "runtime-network",
        ],
    ),
    (
        "runtime-federation",
        &[
            "runtime-primitives",
            "runtime-network",
            "runtime-replication",
            "runtime-api",
        ],
    ),
];

/// Every workspace member's external (non-workspace) dependency allowlist —
/// one row for all 16 members, exhaustive (design `worker-grpc-adapter/design.md`
/// D6). A crate absent from this table is itself a violation (see
/// `every_crate_declares_exactly_its_allowed_external_dependencies`), which is
/// what makes "and nowhere else" hold without a separate negative test.
///
/// `runtime`'s `cargo_metadata` dependency is a **dev-dependency** (this
/// file's own test tooling) and is therefore out of scope for this table —
/// see the `Normal | Build` kind filter below.
const EXTERNAL_ALLOWED: &[(&str, &[&str])] = &[
    ("runtime-primitives", &["serde", "ulid"]),
    ("runtime-object", &[]),
    ("runtime-scheduler", &[]),
    ("runtime-allocation", &[]),
    ("runtime-admission", &[]),
    ("runtime-worker", &["prost", "tonic", "tonic-build"]),
    ("runtime-network", &[]),
    ("runtime-storage", &[]),
    ("runtime-security", &[]),
    ("runtime-observability", &[]),
    ("runtime-state", &[]),
    ("runtime-replication", &[]),
    ("runtime-deployment", &[]),
    ("runtime-api", &[]),
    ("runtime-federation", &[]),
    ("runtime", &["tokio", "llama-cpp-2"]),
];

/// External crates whose presence signals generated transport code (design
/// D6): allowed for exactly one crate, `runtime-worker` — see
/// `transport_dependencies_are_allowlisted_for_exactly_one_crate`.
const TRANSPORT_CRATES: &[&str] = &["prost", "tonic", "tonic-build"];

/// External crates whose presence signals an async runtime dependency
/// (`runtime-composition-root/spec.md` — "Runtime Is The Sole Crate
/// Permitted An Async Runtime Dependency"): allowed for exactly one crate,
/// `runtime` — see `async_runtime_is_allowlisted_for_exactly_one_crate`.
const ASYNC_RUNTIME_CRATES: &[&str] = &["tokio"];

/// External crates whose presence signals a native inference backend
/// (`local-infer-llamacpp-engine/spec.md`): allowed for exactly one crate,
/// `runtime` — see `inference_engine_dependencies_are_allowlisted_for_exactly_one_crate`.
const INFERENCE_ENGINE_CRATES: &[&str] = &["llama-cpp-2"];

/// Every expected workspace member, including `runtime` itself.
const EXPECTED_MEMBERS: &[&str] = &[
    "runtime-primitives",
    "runtime-object",
    "runtime-scheduler",
    "runtime-allocation",
    "runtime-admission",
    "runtime-worker",
    "runtime-network",
    "runtime-storage",
    "runtime-security",
    "runtime-observability",
    "runtime-state",
    "runtime-replication",
    "runtime-deployment",
    "runtime-api",
    "runtime-federation",
    "runtime",
];

fn workspace_root() -> std::path::PathBuf {
    std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("the `runtime` crate has a parent directory (the workspace root)")
        .to_path_buf()
}

fn workspace_metadata() -> cargo_metadata::Metadata {
    MetadataCommand::new()
        .manifest_path(workspace_root().join("Cargo.toml"))
        .no_deps()
        .exec()
        .expect("cargo metadata should succeed")
}

/// Compares a crate's actual dependency set against its allowed set and, if
/// they differ, returns a message naming both the unexpected (forbidden) and
/// missing (dropped) edges. Returns `None` when the sets match exactly.
///
/// This is the guard's core assertion logic, pulled out so it can be
/// exercised directly with synthetic data (see the `guard_logic_*` tests
/// below) as well as with real `cargo metadata` output.
fn diff_dependencies(
    crate_name: &str,
    actual: &BTreeSet<&str>,
    allowed: &BTreeSet<&str>,
) -> Option<String> {
    let unexpected: Vec<&str> = actual.difference(allowed).copied().collect();
    let missing: Vec<&str> = allowed.difference(actual).copied().collect();

    if unexpected.is_empty() && missing.is_empty() {
        None
    } else {
        Some(format!(
            "{crate_name}: unexpected={unexpected:?} missing={missing:?}"
        ))
    }
}

#[test]
fn workspace_has_exactly_the_expected_members() {
    let metadata = workspace_metadata();

    let actual: BTreeSet<&str> = metadata.packages.iter().map(|p| p.name.as_str()).collect();
    let expected: BTreeSet<&str> = EXPECTED_MEMBERS.iter().copied().collect();

    assert_eq!(
        actual, expected,
        "workspace member set drifted from the expected 16 crates"
    );
}

#[test]
fn every_domain_crate_declares_exactly_its_allowed_workspace_dependencies() {
    let metadata = workspace_metadata();

    let member_names: BTreeSet<&str> = metadata.packages.iter().map(|p| p.name.as_str()).collect();

    let mut violations = Vec::new();

    for package in &metadata.packages {
        // `runtime` is the sole deliberate exception: it may depend on all
        // 15 domain crates, so it is exempt from the narrow-dependency check.
        if package.name.as_str() == "runtime" {
            continue;
        }

        let actual: BTreeSet<&str> = package
            .dependencies
            .iter()
            .filter(|d| matches!(d.kind, DependencyKind::Normal | DependencyKind::Build))
            .map(|d| d.name.as_str())
            .filter(|name| member_names.contains(name))
            .collect();

        let allowed: BTreeSet<&str> = match ALLOWED
            .iter()
            .find(|(name, _)| *name == package.name.as_str())
        {
            Some((_, deps)) => deps.iter().copied().collect(),
            None => {
                violations.push(format!(
                    "{}: not present in the ALLOWED matrix",
                    package.name
                ));
                continue;
            }
        };

        if let Some(violation) = diff_dependencies(package.name.as_str(), &actual, &allowed) {
            violations.push(violation);
        }
    }

    // No crate may depend on `runtime` — the other half of the Golden Rule.
    for package in &metadata.packages {
        if package.name.as_str() == "runtime" {
            continue;
        }
        if package.dependencies.iter().any(|d| d.name == "runtime") {
            violations.push(format!("{}: must not depend on runtime", package.name));
        }
    }

    assert!(
        violations.is_empty(),
        "architecture guard violations:\n{}",
        violations.join("\n")
    );
}

/// Spec scenario "Runtime may depend on all 15 domain crates" + "Runtime is
/// exempt from the narrow check": `runtime` legitimately declares every
/// domain crate as a dependency, and that is never flagged as a violation
/// because the narrow-dependency loop above explicitly skips it.
#[test]
fn runtime_depends_on_all_domain_crates_without_violation() {
    let metadata = workspace_metadata();

    let member_names: BTreeSet<&str> = metadata.packages.iter().map(|p| p.name.as_str()).collect();

    let runtime = metadata
        .packages
        .iter()
        .find(|p| p.name.as_str() == "runtime")
        .expect("runtime must be a workspace member");

    let runtime_deps: BTreeSet<&str> = runtime
        .dependencies
        .iter()
        .filter(|d| matches!(d.kind, DependencyKind::Normal | DependencyKind::Build))
        .map(|d| d.name.as_str())
        .filter(|name| member_names.contains(name))
        .collect();

    let all_domain_crates: BTreeSet<&str> = EXPECTED_MEMBERS
        .iter()
        .copied()
        .filter(|name| *name != "runtime")
        .collect();

    assert_eq!(
        runtime_deps, all_domain_crates,
        "runtime should depend on all 15 domain crates"
    );
    // `runtime` is exempt from `ALLOWED`; asserting it has no entry there
    // documents that the narrow-dependency check never applies to it.
    assert!(
        !ALLOWED.iter().any(|(name, _)| *name == "runtime"),
        "runtime must not appear in the narrow-dependency ALLOWED matrix"
    );
}

/// Spec scenarios "External deps stay within the allowlist" and
/// "Build-dependency stays within the allowlist" (`runtime-worker/spec.md`),
/// generalized to all 16 members via `EXTERNAL_ALLOWED` (design D6).
#[test]
fn every_crate_declares_exactly_its_allowed_external_dependencies() {
    let metadata = workspace_metadata();

    let member_names: BTreeSet<&str> = metadata.packages.iter().map(|p| p.name.as_str()).collect();

    let mut violations = Vec::new();

    for package in &metadata.packages {
        let external: BTreeSet<&str> = package
            .dependencies
            .iter()
            .filter(|d| matches!(d.kind, DependencyKind::Normal | DependencyKind::Build))
            .map(|d| d.name.as_str())
            .filter(|name| !member_names.contains(name))
            .collect();

        let allowed: BTreeSet<&str> = match EXTERNAL_ALLOWED
            .iter()
            .find(|(name, _)| *name == package.name.as_str())
        {
            Some((_, deps)) => deps.iter().copied().collect(),
            None => {
                violations.push(format!(
                    "{}: not present in the EXTERNAL_ALLOWED matrix",
                    package.name
                ));
                continue;
            }
        };

        if let Some(violation) = diff_dependencies(package.name.as_str(), &external, &allowed) {
            violations.push(violation);
        }
    }

    assert!(
        violations.is_empty(),
        "external dependency allowlist violations:\n{}",
        violations.join("\n")
    );
}

/// Table-only test (no `cargo metadata`): guards the `EXTERNAL_ALLOWED`
/// TABLE itself, not just crate metadata — catches someone pasting `tonic`
/// into a second row, which per-crate equality checks alone cannot catch
/// (design D6).
#[test]
fn transport_dependencies_are_allowlisted_for_exactly_one_crate() {
    for transport_crate in TRANSPORT_CRATES {
        let owning_rows: Vec<&str> = EXTERNAL_ALLOWED
            .iter()
            .filter(|(_, deps)| deps.contains(transport_crate))
            .map(|(name, _)| *name)
            .collect();

        assert_eq!(
            owning_rows,
            vec!["runtime-worker"],
            "expected `{transport_crate}` to be allowlisted for exactly `runtime-worker`, found: {owning_rows:?}"
        );
    }
}

/// Spec scenario "tokio is allowlisted for runtime alone"
/// (`runtime-composition-root/spec.md`): table-only test (no `cargo
/// metadata`), mirroring `transport_dependencies_are_allowlisted_for_exactly_one_crate`
/// — guards the `EXTERNAL_ALLOWED` TABLE itself, catching a `tokio` entry
/// pasted into a second row.
#[test]
fn async_runtime_is_allowlisted_for_exactly_one_crate() {
    for async_runtime_crate in ASYNC_RUNTIME_CRATES {
        let owning_rows: Vec<&str> = EXTERNAL_ALLOWED
            .iter()
            .filter(|(_, deps)| deps.contains(async_runtime_crate))
            .map(|(name, _)| *name)
            .collect();

        assert_eq!(
            owning_rows,
            vec!["runtime"],
            "expected `{async_runtime_crate}` to be allowlisted for exactly `runtime`, found: {owning_rows:?}"
        );
    }
}

/// Spec scenario "A table-only test pins the bindings crate to runtime
/// alone" (`workspace-manifest/spec.md`): table-only test (no `cargo
/// metadata`), mirroring `async_runtime_is_allowlisted_for_exactly_one_crate`
/// — guards the `EXTERNAL_ALLOWED` TABLE itself, catching a `llama-cpp-2`
/// entry pasted into a second row.
#[test]
fn inference_engine_dependencies_are_allowlisted_for_exactly_one_crate() {
    for inference_engine_crate in INFERENCE_ENGINE_CRATES {
        let owning_rows: Vec<&str> = EXTERNAL_ALLOWED
            .iter()
            .filter(|(_, deps)| deps.contains(inference_engine_crate))
            .map(|(name, _)| *name)
            .collect();

        assert_eq!(
            owning_rows,
            vec!["runtime"],
            "expected `{inference_engine_crate}` to be allowlisted for exactly `runtime`, found: {owning_rows:?}"
        );
    }
}

/// Spec scenario "The bindings crate is present in cargo metadata
/// regardless of feature activation" + "The feature is off unless
/// explicitly requested" (`workspace-manifest/spec.md`,
/// `local-infer-llamacpp-engine/spec.md`): via `cargo_metadata`, `runtime`'s
/// `llama-cpp-2` dependency has `optional == true`, `runtime`'s `features`
/// map contains a `llamacpp` key, and `features["default"]` does not list
/// it.
#[test]
fn the_inference_engine_dependency_is_optional_and_off_by_default() {
    let metadata = workspace_metadata();

    let runtime = metadata
        .packages
        .iter()
        .find(|p| p.name.as_str() == "runtime")
        .expect("runtime must be a workspace member");

    let dependency = runtime
        .dependencies
        .iter()
        .find(|d| d.name == "llama-cpp-2")
        .expect("runtime must declare a llama-cpp-2 dependency");

    assert!(
        dependency.optional,
        "runtime's llama-cpp-2 dependency must be declared optional = true"
    );

    assert!(
        runtime.features.contains_key("llamacpp"),
        "runtime's [features] table must declare a `llamacpp` feature, found: {:?}",
        runtime.features.keys().collect::<Vec<_>>()
    );

    let default_features = runtime
        .features
        .get("default")
        .cloned()
        .unwrap_or_default();
    assert!(
        !default_features.iter().any(|f| f == "llamacpp"),
        "the `llamacpp` feature must not be a member of runtime's default feature set, found: {default_features:?}"
    );
}

/// Meta-verification (spec scenario "Drift is caught"): proves the guard's
/// core comparison logic actually fails, naming the crate and the
/// unexpected dependency, when a crate gains an edge outside its allowed
/// set. Uses a synthetic actual/allowed pair rather than mutating a real
/// crate's `Cargo.toml`, so the guard against regressions in this logic
/// runs on every `cargo test`, not just once by hand.
#[test]
fn guard_logic_catches_an_unexpected_edge() {
    let actual: BTreeSet<&str> = ["runtime-primitives", "runtime-object"]
        .into_iter()
        .collect();
    let allowed: BTreeSet<&str> = ["runtime-primitives"].into_iter().collect();

    let violation = diff_dependencies("runtime-deployment", &actual, &allowed);

    let message = violation.expect("an extra edge beyond the allowed set must be reported");
    assert!(message.contains("runtime-deployment"));
    assert!(message.contains("runtime-object"));
}

/// Meta-verification (spec scenario "Missing required edge is caught"):
/// proves the guard's core comparison logic fails, naming the crate and the
/// dropped dependency, when a crate loses an edge its allowed set requires.
#[test]
fn guard_logic_catches_a_missing_edge() {
    let actual: BTreeSet<&str> = ["runtime-primitives"].into_iter().collect();
    let allowed: BTreeSet<&str> = ["runtime-primitives", "runtime-object"]
        .into_iter()
        .collect();

    let violation = diff_dependencies("runtime-scheduler", &actual, &allowed);

    let message = violation.expect("a dropped required edge must be reported");
    assert!(message.contains("runtime-scheduler"));
    assert!(message.contains("runtime-object"));
}

// ---------------------------------------------------------------------------
// Source-token containment scan (design `worker-grpc-adapter/design.md` D7).
//
// Rather than trying to compute `runtime-worker`'s real public API (which
// would require signature parsing and risks false negatives), these tests
// assert a STRONGER invariant: no transport-crate token appears anywhere in
// the crate's source tree outside `src/adapters/`. That containment implies
// the public-API property by construction.
// ---------------------------------------------------------------------------

/// The `runtime-worker` crate's `src/` directory, relative to the workspace
/// root.
const WORKER_SRC: &str = "crates/runtime-worker/src";

/// Tokens that name transport-crate-generated or transport-crate-dependent
/// code. Any of these appearing outside `src/adapters/` means generated
/// transport code has leaked into the crate's public surface.
const TRANSPORT_TOKENS: &[&str] = &[
    "tonic::",
    "prost::",
    "tonic_build::",
    "include_proto!",
    "OUT_DIR",
];

/// Recursively collect every `.rs` file under `dir`, skipping any
/// subdirectory literally named `adapters` — that private module tree is
/// exactly what's allowed to reference transport types (design D7).
fn rust_files_excluding_adapters(dir: &std::path::Path) -> Vec<std::path::PathBuf> {
    let mut found = Vec::new();
    collect_rust_files_excluding_adapters(dir, &mut found);
    found
}

/// Recursively collect every `.rs` file under `dir`, with no subdirectory
/// exclusion — the plain counterpart to `rust_files_excluding_adapters`,
/// used by scans that need every file in a subtree (design
/// `worker-local-infer-adapter/design.md` D12).
fn rust_files(dir: &std::path::Path) -> Vec<std::path::PathBuf> {
    let mut found = Vec::new();
    collect_rust_files(dir, &mut found);
    found
}

fn collect_rust_files(dir: &std::path::Path, found: &mut Vec<std::path::PathBuf>) {
    let entries = std::fs::read_dir(dir)
        .unwrap_or_else(|e| panic!("failed to read directory {}: {e}", dir.display()));
    for entry in entries {
        let entry = entry.expect("directory entry should be readable");
        let path = entry.path();
        if path.is_dir() {
            collect_rust_files(&path, found);
        } else if path.extension().is_some_and(|ext| ext == "rs") {
            found.push(path);
        }
    }
}

fn collect_rust_files_excluding_adapters(
    dir: &std::path::Path,
    found: &mut Vec<std::path::PathBuf>,
) {
    let entries = std::fs::read_dir(dir)
        .unwrap_or_else(|e| panic!("failed to read directory {}: {e}", dir.display()));
    for entry in entries {
        let entry = entry.expect("directory entry should be readable");
        let path = entry.path();
        if path.is_dir() {
            if path.file_name().and_then(|n| n.to_str()) == Some("adapters") {
                continue;
            }
            collect_rust_files_excluding_adapters(&path, found);
        } else if path.extension().is_some_and(|ext| ext == "rs") {
            found.push(path);
        }
    }
}

/// True if `identifier` appears in `line` as a whole identifier (not as a
/// substring of a longer identifier).
fn contains_identifier(line: &str, identifier: &str) -> bool {
    let bytes = line.as_bytes();
    let ident_len = identifier.len();
    let mut start = 0;
    while let Some(offset) = line[start..].find(identifier) {
        let idx = start + offset;
        let before_ok = idx == 0 || !is_identifier_byte(bytes[idx - 1]);
        let after_idx = idx + ident_len;
        let after_ok = after_idx >= bytes.len() || !is_identifier_byte(bytes[after_idx]);
        if before_ok && after_ok {
            return true;
        }
        start = idx + ident_len;
    }
    false
}

fn is_identifier_byte(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b == b'_'
}

/// Lowercased, case-insensitive SUBSTRING match of `term` in `line` — unlike
/// `contains_identifier`, this deliberately does NOT require word
/// boundaries, so it subsumes `llama_cpp`, `llama_cpp_2`, `llamacpp`,
/// `LlamaModel`, `LlamaBackend`, `LLAMA_*` (design D14). Used ONLY by
/// `engine_names_stay_inside_the_engine_module`; `contains_identifier`
/// stays unmodified everywhere else (whole-identifier matching is correct
/// for `local_infer_engine_names_no_async_runtime` and
/// `local_infer_engine_declares_no_async_surface`, where `async` must not
/// flag `async_runtime_is_allowlisted_for_exactly_one_crate`).
fn line_contains_engine_name_term(line: &str, term: &str) -> bool {
    line.to_ascii_lowercase().contains(&term.to_ascii_lowercase())
}

/// True if `line` is a build-configuration attribute line whose only
/// offending engine-name term is the `llamacpp` feature name itself (design
/// D14 part 2). The feature gate is a Composition-Root build concept and
/// may be named where builds are configured (`#[cfg(feature = "llamacpp")]`
/// outside `engine/`); the engine's API may never leave `engine/`. Masking
/// out `llamacpp` and re-checking for any of the three engine-name terms
/// keeps this general: a `#[cfg]` line that ALSO names `llama_cpp_2` or
/// `ggml` directly is still caught.
fn line_is_exempt_engine_name_cfg_attribute(line: &str) -> bool {
    let trimmed = line.trim_start();
    if !trimmed.starts_with("#[cfg") {
        return false;
    }
    let masked = trimmed.to_ascii_lowercase().replace("llamacpp", "");
    !["llama", "ggml", "candle"]
        .iter()
        .any(|term| masked.contains(term))
}

/// True if `line` names the `adapters` identifier and is not a comment line.
/// Comment lines are skipped first — a doc comment mentioning "adapters" in
/// prose (e.g. `/// converted in the adapters/ tree, see docs`) must not
/// count as a re-export, matching the comment-skip already applied by
/// `runtime_worker_transport_types_stay_inside_the_private_adapter_module`.
fn line_names_adapters_identifier(line: &str) -> bool {
    if line.trim_start().starts_with("//") {
        return false;
    }
    contains_identifier(line, "adapters")
}

#[test]
fn line_names_adapters_identifier_skips_comment_lines_but_not_real_code() {
    assert!(
        !line_names_adapters_identifier("/// converted in the adapters/ tree, see docs"),
        "a doc comment mentioning `adapters` in prose must not count as an occurrence"
    );
    assert!(
        line_names_adapters_identifier("mod adapters;"),
        "the literal `mod adapters;` declaration must still be counted"
    );
}

/// Spec scenario "Public API carries no tonic/prost path"
/// (`runtime-worker/spec.md`): no transport token appears in `src/` outside
/// `adapters/`.
#[test]
fn runtime_worker_transport_types_stay_inside_the_private_adapter_module() {
    let worker_src = workspace_root().join(WORKER_SRC);
    let mut violations = Vec::new();

    for file in rust_files_excluding_adapters(&worker_src) {
        let contents = std::fs::read_to_string(&file)
            .unwrap_or_else(|e| panic!("failed to read {}: {e}", file.display()));
        for (line_number, line) in contents.lines().enumerate() {
            if line.trim_start().starts_with("//") {
                continue;
            }
            for token in TRANSPORT_TOKENS {
                if line.contains(token) {
                    violations.push(format!(
                        "{}:{}: contains transport token `{token}` outside adapters/",
                        file.display(),
                        line_number + 1
                    ));
                }
            }
        }
    }

    assert!(
        violations.is_empty(),
        "transport tokens leaked outside the private adapter module:\n{}",
        violations.join("\n")
    );
}

/// Spec scenario "No re-export escapes the private module, except opaque
/// Composition-Root factories" (`runtime-worker/spec.md`): every occurrence
/// of the `adapters` identifier outside `src/adapters/` itself is either the
/// bare `mod adapters;` declaration in `lib.rs`, or a single-item `pub use
/// adapters::<name>;` re-export naming a Composition-Root factory function —
/// never a glob, never a nested path, never the module or an adapter type
/// itself. Each named factory is then required to actually exist as a `pub
/// fn`/`pub async fn` somewhere under `src/adapters/` whose signature line
/// names no transport token and returns an opaque `impl <port>` type,
/// closing the `pub use crate::adapters::…` hole that the token scan alone
/// would miss. Comment lines are skipped before scanning, matching
/// `runtime_worker_transport_types_stay_inside_the_private_adapter_module`'s
/// own comment-skip behavior, so a doc comment mentioning "adapters" in
/// prose (plausible once new public modules under `execution/`/`ports/`
/// start documenting what they are *not*) never trips this guard.
#[test]
fn runtime_worker_never_reexports_the_adapter_module() {
    let worker_src = workspace_root().join(WORKER_SRC);
    let mut mod_declarations = Vec::new();
    let mut factory_names = Vec::new();

    for file in rust_files_excluding_adapters(&worker_src) {
        let contents = std::fs::read_to_string(&file)
            .unwrap_or_else(|e| panic!("failed to read {}: {e}", file.display()));
        for (line_number, line) in contents.lines().enumerate() {
            if !line_names_adapters_identifier(line) {
                continue;
            }
            let trimmed = line.trim();
            if trimmed == "mod adapters;" {
                mod_declarations.push((file.clone(), line_number + 1));
                continue;
            }
            let name = trimmed
                .strip_prefix("pub use adapters::")
                .and_then(|rest| rest.strip_suffix(';'))
                .unwrap_or_else(|| {
                    panic!(
                        "unexpected `adapters` occurrence at {}:{} — only a bare `mod adapters;` \
                         declaration or a single-item `pub use adapters::<name>;` factory \
                         re-export is allowed, found: {trimmed:?}",
                        file.display(),
                        line_number + 1
                    )
                });
            assert!(
                !name.is_empty() && !name.contains(['*', ':']),
                "factory re-export at {}:{} must name exactly one item, no glob and no nested \
                 path, found: {trimmed:?}",
                file.display(),
                line_number + 1
            );
            factory_names.push((file.clone(), line_number + 1, name.to_string()));
        }
    }

    assert_eq!(
        mod_declarations.len(),
        1,
        "expected exactly one `mod adapters;` declaration in runtime-worker's non-adapters \
         source tree, found: {mod_declarations:?}"
    );
    assert_eq!(
        mod_declarations[0].0.file_name().and_then(|n| n.to_str()),
        Some("lib.rs"),
        "the `mod adapters;` declaration must live in lib.rs, found it in {}",
        mod_declarations[0].0.display()
    );

    let adapters_dir = worker_src.join("adapters");
    let adapters_files = rust_files(&adapters_dir);
    for (file, line_number, name) in &factory_names {
        let signature_prefix_fn = format!("pub fn {name}(");
        let signature_prefix_async_fn = format!("pub async fn {name}(");

        let signature_line = adapters_files.iter().find_map(|adapter_file| {
            let contents = std::fs::read_to_string(adapter_file)
                .unwrap_or_else(|e| panic!("failed to read {}: {e}", adapter_file.display()));
            contents.lines().find_map(|line| {
                let trimmed = line.trim_start();
                (trimmed.starts_with(&signature_prefix_fn)
                    || trimmed.starts_with(&signature_prefix_async_fn))
                .then(|| trimmed.to_string())
            })
        });

        let signature_line = signature_line.unwrap_or_else(|| {
            panic!(
                "factory `{name}` re-exported at {}:{} has no matching `pub fn {name}(` or \
                 `pub async fn {name}(` declaration anywhere under {}",
                file.display(),
                line_number,
                adapters_dir.display()
            )
        });

        for token in TRANSPORT_TOKENS {
            assert!(
                !signature_line.contains(token),
                "factory `{name}`'s signature must name no transport token, but contains \
                 {token:?}: {signature_line:?}"
            );
        }
        assert!(
            signature_line.contains("impl "),
            "factory `{name}`'s signature must return an opaque `impl <port>` type, found: \
             {signature_line:?}"
        );
    }
}

/// Spec scenario "Generated code module is not public"
/// (`runtime-worker/spec.md`): `adapters/mod.rs` declares a non-`pub` `mod
/// grpc;`, and `adapters/grpc/mod.rs` includes the generated code exactly
/// once.
#[test]
fn runtime_worker_generated_code_is_included_once_in_a_private_module() {
    let adapters_mod = workspace_root()
        .join(WORKER_SRC)
        .join("adapters")
        .join("mod.rs");
    let adapters_mod_contents = std::fs::read_to_string(&adapters_mod)
        .unwrap_or_else(|e| panic!("failed to read {}: {e}", adapters_mod.display()));

    assert!(
        adapters_mod_contents
            .lines()
            .any(|line| line.trim() == "mod grpc;"),
        "expected a bare, non-pub `mod grpc;` declaration in {}",
        adapters_mod.display()
    );
    assert!(
        !adapters_mod_contents.contains("pub mod grpc"),
        "the generated-code module must not be declared `pub` in {}",
        adapters_mod.display()
    );

    let grpc_mod = workspace_root()
        .join(WORKER_SRC)
        .join("adapters")
        .join("grpc")
        .join("mod.rs");
    let grpc_mod_contents = std::fs::read_to_string(&grpc_mod)
        .unwrap_or_else(|e| panic!("failed to read {}: {e}", grpc_mod.display()));

    let include_lines: Vec<&str> = grpc_mod_contents
        .lines()
        .filter(|line| line.contains("include!("))
        .collect();

    assert_eq!(
        include_lines.len(),
        1,
        "expected exactly one generated-code `include!` line in {}, found: {include_lines:?}",
        grpc_mod.display()
    );
    assert!(
        include_lines[0].contains("OUT_DIR"),
        "the generated-code include must pull from OUT_DIR, found: {}",
        include_lines[0]
    );
}

/// Spec scenario "private_interfaces lint is denied"
/// (`runtime-worker/spec.md`): `lib.rs` carries the literal
/// `#![deny(private_interfaces, private_bounds)]` crate attribute.
#[test]
fn runtime_worker_denies_private_interfaces_and_bounds_lints() {
    let lib_rs = workspace_root().join(WORKER_SRC).join("lib.rs");
    let contents = std::fs::read_to_string(&lib_rs)
        .unwrap_or_else(|e| panic!("failed to read {}: {e}", lib_rs.display()));

    assert!(
        contents.contains("#![deny(private_interfaces, private_bounds)]"),
        "expected the literal `#![deny(private_interfaces, private_bounds)]` crate attribute in {}",
        lib_rs.display()
    );
}

/// Spec scenario "Doc comment cites the owning doc"
/// (`runtime-worker/spec.md`, "Crate Doc Comment Cites the Owning Document"):
/// `lib.rs`'s crate-level doc comment must reference `18-worker-model.md`.
#[test]
fn runtime_worker_doc_comment_cites_the_owning_document() {
    let lib_rs = workspace_root().join(WORKER_SRC).join("lib.rs");
    let contents = std::fs::read_to_string(&lib_rs)
        .unwrap_or_else(|e| panic!("failed to read {}: {e}", lib_rs.display()));

    assert!(
        contents.contains("18-worker-model.md"),
        "expected the crate doc comment in {} to cite `18-worker-model.md`",
        lib_rs.display()
    );
}

// ---------------------------------------------------------------------------
// Local-Infer engine containment scans (`worker-local-infer-adapter/design.md`
// D12): D0-b means the engine subtree earns no new `EXTERNAL_ALLOWED` row of
// its own (`runtime` already carries `tokio`), so these source-containment
// scans are the machine-checked stand-in for that row — the direct
// enforcement of `worker-local-infer-adapter/spec.md`'s "The Engine Port Is
// Wholly Synchronous, Std-Only..." requirement.
// ---------------------------------------------------------------------------

/// The Local-Infer engine subtree, relative to the workspace root — must
/// never name `tokio`, `async`, or `await` anywhere in it (design D12).
const LOCAL_INFER_ENGINE_SRC: &str = "runtime/src/worker/local_infer/engine";

/// Scans exactly `files` for any of `identifiers`, skipping comment lines
/// and matching whole identifiers only (`contains_identifier`) — the same
/// convention the transport-token scan above uses. Returns one violation
/// message per offending line. Extracted from `find_identifier_occurrences`
/// (task 3.10) so a caller can hand-assemble a file list — e.g. a subtree
/// scan that itself excludes a nested subdirectory — instead of being
/// limited to "every file under one directory."
fn find_identifier_occurrences_in_files(
    files: &[std::path::PathBuf],
    identifiers: &[&str],
) -> Vec<String> {
    let mut violations = Vec::new();
    for file in files {
        let contents = std::fs::read_to_string(file)
            .unwrap_or_else(|e| panic!("failed to read {}: {e}", file.display()));
        for (line_number, line) in contents.lines().enumerate() {
            if line.trim_start().starts_with("//") {
                continue;
            }
            for identifier in identifiers {
                if contains_identifier(line, identifier) {
                    violations.push(format!(
                        "{}:{}: contains forbidden identifier `{identifier}`",
                        file.display(),
                        line_number + 1
                    ));
                }
            }
        }
    }
    violations
}

/// Scans every `.rs` file under `dir` (via `rust_files`, no subdirectory
/// exclusion) for any of `identifiers` — thin wrapper over
/// `find_identifier_occurrences_in_files`.
fn find_identifier_occurrences(dir: &std::path::Path, identifiers: &[&str]) -> Vec<String> {
    find_identifier_occurrences_in_files(&rust_files(dir), identifiers)
}

/// Hardened counterpart to `find_identifier_occurrences_in_files` (design
/// D14): scans `files` for any of `terms` using `line_contains_engine_name_term`
/// (case-insensitive substring, not whole-identifier) instead of
/// `contains_identifier`. Comment lines are skipped, matching every other
/// scan's convention. Used only by `engine_names_stay_inside_the_engine_module`.
fn find_engine_name_occurrences_in_files(
    files: &[std::path::PathBuf],
    terms: &[&str],
) -> Vec<String> {
    let mut violations = Vec::new();
    for file in files {
        let contents = std::fs::read_to_string(file)
            .unwrap_or_else(|e| panic!("failed to read {}: {e}", file.display()));
        for (line_number, line) in contents.lines().enumerate() {
            if line.trim_start().starts_with("//") {
                continue;
            }
            if line_is_exempt_engine_name_cfg_attribute(line) {
                continue;
            }
            for term in terms {
                if line_contains_engine_name_term(line, term) {
                    violations.push(format!(
                        "{}:{}: contains forbidden engine-name term `{term}`",
                        file.display(),
                        line_number + 1
                    ));
                }
            }
        }
    }
    violations
}

/// Spec scenario "A whole-subtree token scan finds no tokio:: path and no
/// async/await keyword" (`worker-local-infer-adapter/spec.md`): no `tokio`
/// identifier anywhere under `local_infer/engine/`. Written before any
/// violation was ever possible — the engine subtree is `std`-only by
/// construction (Phase 1.1/1.2) — so this test proves the invariant is
/// mechanically enforced going forward, not merely true by accident today.
#[test]
fn local_infer_engine_names_no_async_runtime() {
    let engine_src = workspace_root().join(LOCAL_INFER_ENGINE_SRC);
    let violations = find_identifier_occurrences(&engine_src, &["tokio"]);

    assert!(
        violations.is_empty(),
        "the local-infer engine subtree must never name `tokio`:\n{}",
        violations.join("\n")
    );
}

/// Spec scenario "A whole-subtree token scan finds no tokio:: path and no
/// async/await keyword" (`worker-local-infer-adapter/spec.md`): no `async`
/// or `await` identifier anywhere under `local_infer/engine/` — the
/// machine-checked stand-in for design D5's amended canon wording ("Internal
/// implementations may be synchronous").
#[test]
fn local_infer_engine_declares_no_async_surface() {
    let engine_src = workspace_root().join(LOCAL_INFER_ENGINE_SRC);
    let violations = find_identifier_occurrences(&engine_src, &["async", "await"]);

    assert!(
        violations.is_empty(),
        "the local-infer engine subtree must declare no async surface (no `async`/`await`):\n{}",
        violations.join("\n")
    );
}

/// Spec scenario "No engine-specific name appears outside the engine module,
/// including in local_infer/mod.rs" (`worker-local-infer-adapter/spec.md`):
/// `llama`, `llama_cpp`, `ggml`, `candle` must never appear anywhere in
/// `crates/runtime-worker/src/` or `runtime/src/`, excluding the engine
/// subtree itself (`LOCAL_INFER_ENGINE_SRC`) — the one place a real
/// inference backend's name is expected to eventually appear (design D12).
/// Reuses `rust_files` (task 1.8) and `find_identifier_occurrences_in_files`
/// (task 3.10) rather than adding a third file-walk helper.
#[test]
fn engine_names_stay_inside_the_engine_module() {
    let root = workspace_root();
    let engine_src = root.join(LOCAL_INFER_ENGINE_SRC);

    let mut files = rust_files(&root.join("crates/runtime-worker/src"));
    files.extend(
        rust_files(&root.join("runtime/src"))
            .into_iter()
            .filter(|path| !path.starts_with(&engine_src)),
    );

    let violations =
        find_engine_name_occurrences_in_files(&files, &["llama", "ggml", "candle"]);

    assert!(
        violations.is_empty(),
        "engine-specific names must stay inside `local_infer/engine/`:\n{}",
        violations.join("\n")
    );
}

/// Meta-verification (design D14, spec "The existing containment scan still
/// passes with llamacpp.rs added to the engine subtree"): proves the
/// hardened engine-name scan actually catches a split identifier —
/// `use llama_cpp_2::LlamaModel;` — that `contains_identifier`'s
/// whole-identifier matching lets through today (`"llama"` and
/// `"llama_cpp"` both fail because the next byte is `_`). Mirrors
/// `guard_logic_catches_an_unexpected_edge`'s synthetic-data precedent
/// rather than mutating a real crate's source.
///
/// RED: `line_contains_engine_name_term` does not exist yet, so this test
/// fails to compile.
#[test]
fn hardened_engine_name_scan_catches_a_split_identifier() {
    let line = "use llama_cpp_2::LlamaModel;";

    let caught = ["llama", "ggml", "candle"]
        .iter()
        .any(|term| line_contains_engine_name_term(line, term));

    assert!(
        caught,
        "expected the hardened scan to catch `use llama_cpp_2::LlamaModel;`, \
         which whole-identifier matching lets through (next byte after `llama`/`llama_cpp` is `_`)"
    );
}

/// Spec/design D14 part 2: a `#[cfg(feature = "llamacpp")]` attribute line
/// is a false positive under plain substring matching (`"llama"` is a
/// substring of `"llamacpp"`) but names a Composition-Root build concept,
/// not the engine's API — it must be exempted from the hardened scan.
///
/// RED: `line_is_exempt_engine_name_cfg_attribute` does not exist yet, so
/// this test fails to compile.
#[test]
fn cfg_attribute_lines_are_exempt_from_the_engine_name_scan() {
    let line = "#[cfg(feature = \"llamacpp\")]";

    assert!(
        line_is_exempt_engine_name_cfg_attribute(line),
        "a `#[cfg(...)]` attribute line whose only offending term is the feature name \
         must be exempted from the hardened engine-name scan"
    );
}

/// Deferred from PR1's 1.5 (tasks.md 2.11, design D14 item 3): every line
/// outside the engine subtree that names the `llamacpp` feature must be a
/// bounded `#[cfg(...)]` build-configuration line — never a leaked engine
/// identifier — and `local_infer/mod.rs`'s compile-time engine-selection
/// hook (D10, task 2.10) must be one of them.
///
/// D14's original wording ("exactly one line, in `local_infer/mod.rs`")
/// predates task 1.18's later, separately-approved discovery that
/// `worker/any.rs` needed its own `#[cfg(not(feature = "llamacpp"))]` gate,
/// for the same underlying reason (the real-dispatcher conformance tests
/// cannot complete without an operator-supplied model). That gate is a
/// legitimate, documented allowance, not a leak — so this test asserts the
/// invariant D14 actually cares about (every occurrence is a named, bounded
/// `#[cfg(...)]` line) rather than a count a prior, approved change already
/// exceeds.
///
/// RED until task 2.10 adds the hook line to `local_infer/mod.rs`.
#[test]
fn the_feature_gate_is_named_on_exactly_one_line_outside_the_engine_subtree() {
    let root = workspace_root();
    let engine_src = root.join(LOCAL_INFER_ENGINE_SRC);

    let mut files = rust_files(&root.join("crates/runtime-worker/src"));
    files.extend(
        rust_files(&root.join("runtime/src"))
            .into_iter()
            .filter(|path| !path.starts_with(&engine_src)),
    );

    let mut occurrences: Vec<(std::path::PathBuf, usize, String)> = Vec::new();
    for file in &files {
        let contents = std::fs::read_to_string(file)
            .unwrap_or_else(|e| panic!("failed to read {}: {e}", file.display()));
        for (line_number, line) in contents.lines().enumerate() {
            if line.trim_start().starts_with("//") {
                continue;
            }
            if line.to_ascii_lowercase().contains("llamacpp") {
                occurrences.push((file.clone(), line_number + 1, line.to_string()));
            }
        }
    }

    assert!(
        !occurrences.is_empty(),
        "expected at least one line outside the engine subtree to name the `llamacpp` \
         feature (the `local_infer/mod.rs` selection hook)"
    );

    let non_cfg: Vec<&(std::path::PathBuf, usize, String)> = occurrences
        .iter()
        .filter(|(_, _, line)| !line.trim_start().starts_with("#[cfg"))
        .collect();
    assert!(
        non_cfg.is_empty(),
        "every `llamacpp` occurrence outside the engine subtree must be a bounded \
         `#[cfg(...)]` attribute line:\n{}",
        non_cfg
            .iter()
            .map(|(path, line_number, line)| format!(
                "{}:{line_number}: {line}",
                path.display()
            ))
            .collect::<Vec<_>>()
            .join("\n")
    );

    let names_mod_rs = occurrences.iter().any(|(path, _, _)| {
        path.strip_prefix(&root).unwrap_or(path)
            == std::path::Path::new("runtime/src/worker/local_infer/mod.rs")
    });
    assert!(
        names_mod_rs,
        "the compile-time engine-selection hook must name `llamacpp` in \
         `local_infer/mod.rs`, found only:\n{}",
        occurrences
            .iter()
            .map(|(path, line_number, line)| format!(
                "{}:{line_number}: {line}",
                path.display()
            ))
            .collect::<Vec<_>>()
            .join("\n")
    );
}
