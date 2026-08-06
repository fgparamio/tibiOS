"""Value types for a concrete published model (`design.md` Key Contracts).

`BackendSupport` is keyed by (backend, footprint tier), not by backend
alone (design decision MC5) — the proposal stated both "footprint is a
function of quantization" and a single scalar `min_vram_bytes` per
backend, a latent contradiction. A `ModelDescriptor` may therefore carry
several `BackendSupport` rows for the same `BackendId`, one per tier
(e.g. one row for `q4_k_m`, another for `q8_0` on `llama_cpp`).
`quantizations` on a row holds the schemes that share one
`min_vram_bytes` — `awq` and `gptq` at 4 bits do, `fp16` does not.

`Quantization` is reused from `selection/policy.py`, not mirrored — the
transitive module edge `catalog -> selection -> execution` that follows
is accepted and unavoidable (see `catalog/catalog.py`'s resolution guard,
design decision MC9, which is written against the type surface for
exactly this reason).
"""

from dataclasses import dataclass

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import ModelFamily
from tibios_ray.catalog.names import PublishedModelName
from tibios_ray.selection.policy import Quantization


@dataclass(frozen=True, slots=True, kw_only=True)
class BackendSupport:
    """One (backend, footprint tier) row of a model's serving table
    (design decision MC5). `min_vram_bytes` is advisory, derived as
    `parameter_count * bits / 8 * 1.2` rounded up to a whole GiB (MC13);
    nothing in this change makes an admission decision from it."""

    backend: BackendId
    quantizations: frozenset[Quantization]
    min_vram_bytes: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelDescriptor:
    """One concrete published model. `family` is redundant with
    `family_of(name)` by construction — `ModelCatalog` rejects any entry
    where they disagree (`FamilyMismatchError`) — and is stated
    explicitly anyway so entry tables are readable without mentally
    running the FLC.

    `parameter_count` is *total* parameters, including inactive experts
    on a MoE model, because that is what determines resident VRAM.
    `context_window` is the natively published window, not an extended
    one."""

    name: PublishedModelName
    family: ModelFamily
    parameter_count: int
    context_window: int
    serving: frozenset[BackendSupport]
