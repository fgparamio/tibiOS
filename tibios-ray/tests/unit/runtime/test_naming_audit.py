"""Naming audit — a permanent, discoverable pytest test (not a one-off
manual check), enforcing `worker-runtime` spec's "'Worker' Naming Is
Reserved to the Contract Entity" requirement:

    No class, module, protocol, or identifier inside tibios-ray, other
    than the entity implementing the gRPC Worker Contract itself, MAY be
    named "Worker" ... for a capability-specific unit.

This scans the Python *identifiers* (class/function/parameter/import/
assignment names) actually defined or referenced in
`capabilities/`, `selection/`, `backends/`, and `runtime/` — not raw
text — so a docstring that quotes the binding rule itself (e.g. "Worker"
is reserved exclusively for...") never counts as a violation; only real
code identifiers do.

`runtime/` is exempt for exactly one identifier: `WorkerRuntime` — the
sanctioned single exception (`design.md`, `worker-runtime` spec) because
it directly drives the Worker Contract lifecycle. Nothing else in
`runtime/`, and nothing at all in `capabilities/`, `selection/`, or
`backends/`, may contain "Worker" as an identifier.
"""

import ast
from pathlib import Path

import tibios_ray

_SRC_ROOT = Path(tibios_ray.__file__).resolve().parent

_AUDITED_PACKAGES: tuple[tuple[str, frozenset[str]], ...] = (
    ("capabilities", frozenset()),
    ("selection", frozenset()),
    ("backends", frozenset()),
    ("runtime", frozenset({"WorkerRuntime"})),
)


def _identifiers(source: str) -> set[str]:
    """All identifiers a module defines or references: class/function
    names, parameter names, assignment targets, and import names."""
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            names.add(node.name)
        elif isinstance(node, ast.alias):
            names.add(node.asname or node.name.rsplit(".", 1)[-1])
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def test_naming_audit_zero_worker_identifiers_outside_the_contract_entity() -> None:
    violations: dict[str, set[str]] = {}

    for package, allowed in _AUDITED_PACKAGES:
        package_dir = _SRC_ROOT / package
        assert package_dir.is_dir(), f"expected package directory {package_dir}"
        for path in sorted(package_dir.rglob("*.py")):
            found = {
                name
                for name in _identifiers(path.read_text())
                if "Worker" in name and name not in allowed
            }
            if found:
                violations[str(path.relative_to(_SRC_ROOT))] = found

    assert not violations, (
        "found 'Worker' identifiers outside the sanctioned WorkerRuntime "
        f"contract entity (worker-runtime spec naming audit): {violations}"
    )
