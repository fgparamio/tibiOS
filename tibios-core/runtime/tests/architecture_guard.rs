//! Architecture Guard — machine-checks that the workspace's real dependency
//! graph matches the Allowed Edge Matrix in `design.md`, per the
//! `workspace-manifest` and `runtime-composition-root` specs.
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

/// `runtime-primitives`' external (non-workspace) dependency allowlist.
const PRIMITIVES_EXTERNAL: &[&str] = &["serde", "ulid"];

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

#[test]
fn primitives_external_dependencies_are_allowlisted() {
    let metadata = workspace_metadata();

    let member_names: BTreeSet<&str> = metadata.packages.iter().map(|p| p.name.as_str()).collect();

    let primitives = metadata
        .packages
        .iter()
        .find(|p| p.name.as_str() == "runtime-primitives")
        .expect("runtime-primitives must be a workspace member");

    let external: BTreeSet<&str> = primitives
        .dependencies
        .iter()
        .filter(|d| matches!(d.kind, DependencyKind::Normal | DependencyKind::Build))
        .map(|d| d.name.as_str())
        .filter(|name| !member_names.contains(name))
        .collect();

    let allowlist: BTreeSet<&str> = PRIMITIVES_EXTERNAL.iter().copied().collect();

    assert_eq!(
        external, allowlist,
        "runtime-primitives external dependencies drifted from the allowlist"
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
