"""No-`local-infer`-routing guard — a permanent, discoverable pytest test
(not a one-off manual `rg` sweep), enforcing the binding Boundary Rule
established across `ray-worker-runtime` (`proposal.md`'s Boundary Rules,
`25-ai-runtime.md`'s Anti-Patterns):

    From the Runtime's perspective there is no difference between
    `local-infer` and tibios-ray. No size/cost routing rule (e.g.
    "if model < X then local-infer") may exist anywhere in this repo —
    that decision belongs exclusively to tibios-core's Scheduling
    Capability Filter, and tibios-ray must never encode or anticipate it.

Unlike the naming audit (`test_naming_audit.py`), this rule is NOT a
closed, exactly-enumerable identifier check — "a routing decision" has no
single AST shape. This test therefore combines two independent,
AST-based (not raw-text) heuristics and is explicit about their limits:

1. **Literal `local-infer` / `local_infer` mentions** — flags any string
   *constant* in the scanned source whose value contains `local-infer` or
   `local_infer` (case-insensitive), UNLESS that constant is a module,
   class, or function **docstring** — mirroring `test_naming_audit.py`'s
   exemption for prose that quotes the binding rule itself as
   documentation. Comments are never a concern here in the first place:
   the Python AST never contains them, so a `# no local-infer here`
   comment cannot trip this check by construction.

2. **Size/cost-threshold-shaped comparisons** — flags any `ast.Compare`
   node, anywhere in the scanned source, that compares a numeric literal
   against a name or attribute whose identifier matches
   `size|cost|threshold|param|billion|gb` (case-insensitive) using an
   ordering operator (`<`, `<=`, `>`, `>=`). This is the generic shape of
   `if model_size < 4_000_000_000: ...` or `cost > budget_threshold`.

### What this deliberately does NOT catch (honest limits, not exhaustive)

- Threshold logic hidden behind indirection: comparing against a
  variable/attribute that does not itself carry a size/cost/threshold-ish
  name (e.g. `if n < 4e9`), or a threshold value read from config/env
  rather than a literal.
- Routing encoded without a `Compare` node at all — e.g. a precomputed
  lookup table/dict keyed by a size bucket, or delegating the decision to
  an external call whose body isn't in the scanned tree.
- A `local-infer` mention built via string concatenation, f-string
  interpolation from parts, or any other value that isn't a single
  literal `ast.Constant`.
- False positives are structurally possible: an unrelated numeric
  comparison against a variable that happens to match the keyword regex
  (e.g. a legitimate `batch_size < max_batch_size` inside this repo's own
  execution bookkeeping, nothing to do with Worker routing) would also be
  flagged. Given zero legitimate use of this vocabulary exists in the
  scanned packages today (Phase 1 "Foundation" is skeleton/interfaces
  only, no real batching/sizing logic yet), this tradeoff is accepted —
  the same way `test_naming_audit.py` accepts a coarse, package-wide
  scope over a narrower one. If a legitimate size/cost comparison is ever
  added, this test's regex may need a scoped exemption at that point.

This test scans exactly the surface `proposal.md` names as bound by the
rule: `execution/`, `backends/`, `selection/`, `capabilities/`,
`runtime/`, `testing/`, `worker.py`, and `server.py`.
"""

import ast
import re
from pathlib import Path

import tibios_ray

_SRC_ROOT = Path(tibios_ray.__file__).resolve().parent

_AUDITED_PACKAGES: tuple[str, ...] = (
    "execution",
    "backends",
    "selection",
    "capabilities",
    "runtime",
    "testing",
)

_AUDITED_MODULES: tuple[str, ...] = (
    "worker.py",
    "server.py",
)

_LOCAL_INFER_PATTERN = re.compile(r"local[-_]infer", re.IGNORECASE)
_SIZE_COST_KEYWORD = re.compile(r"(size|cost|threshold|param|billion|gb)", re.IGNORECASE)
_THRESHOLD_OPS = (ast.Lt, ast.LtE, ast.Gt, ast.GtE)

_DocstringOwner = ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef


def _docstring_constant_ids(tree: ast.AST) -> set[int]:
    """`id()` of every `ast.Constant` that is a module/class/function
    docstring — the same "documentation quoting the rule" exemption
    `test_naming_audit.py` grants to prose, applied here to string
    literals instead of identifiers."""
    exempt: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, _DocstringOwner) and node.body:
            first = node.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                exempt.add(id(first.value))
    return exempt


def _local_infer_string_violations(tree: ast.AST, exempt_ids: set[int]) -> list[str]:
    violations: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in exempt_ids
            and _LOCAL_INFER_PATTERN.search(node.value)
        ):
            violations.append(node.value)
    return violations


def _operand_identifier(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _numeric_constant_value(node: ast.expr) -> int | float | None:
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int | float)
        and not isinstance(node.value, bool)
    ):
        return node.value
    return None


def _threshold_violations(tree: ast.AST) -> list[str]:
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        operands = [node.left, *node.comparators]
        for left, op, right in zip(operands[:-1], node.ops, operands[1:], strict=True):
            if not isinstance(op, _THRESHOLD_OPS):
                continue
            for name_side, const_side in ((left, right), (right, left)):
                name = _operand_identifier(name_side)
                numeric_value = _numeric_constant_value(const_side)
                if name and numeric_value is not None and _SIZE_COST_KEYWORD.search(name):
                    violations.append(f"{name} {op.__class__.__name__} {numeric_value!r}")
    return violations


def _iter_audited_files() -> list[Path]:
    files: list[Path] = []
    for package in _AUDITED_PACKAGES:
        package_dir = _SRC_ROOT / package
        assert package_dir.is_dir(), f"expected package directory {package_dir}"
        files.extend(sorted(package_dir.rglob("*.py")))
    for module_name in _AUDITED_MODULES:
        module_path = _SRC_ROOT / module_name
        assert module_path.is_file(), f"expected module file {module_path}"
        files.append(module_path)
    return files


def test_no_local_infer_literal_mentions_outside_documentation() -> None:
    violations: dict[str, list[str]] = {}

    for path in _iter_audited_files():
        tree = ast.parse(path.read_text())
        exempt_ids = _docstring_constant_ids(tree)
        found = _local_infer_string_violations(tree, exempt_ids)
        if found:
            violations[str(path.relative_to(_SRC_ROOT))] = found

    assert not violations, (
        "found literal 'local-infer'/'local_infer' mentions outside "
        "docstrings (proposal.md Boundary Rules / 25-ai-runtime.md "
        f"Anti-Patterns — no such routing may exist here): {violations}"
    )


def test_no_size_or_cost_threshold_shaped_routing_conditional() -> None:
    violations: dict[str, list[str]] = {}

    for path in _iter_audited_files():
        tree = ast.parse(path.read_text())
        found = _threshold_violations(tree)
        if found:
            violations[str(path.relative_to(_SRC_ROOT))] = found

    assert not violations, (
        "found a size/cost-threshold-shaped comparison (e.g. "
        "'model_size < 4_000_000_000') — this shape is reserved for "
        "tibios-core's Scheduling Capability Filter; tibios-ray must "
        f"never encode or anticipate a local-infer routing rule: {violations}"
    )
