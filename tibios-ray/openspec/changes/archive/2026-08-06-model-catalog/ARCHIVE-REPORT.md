# Archive Report: model-catalog

**Date Archived**: 2026-08-06
**Change Name**: model-catalog
**Status**: COMPLETE
**Verdict**: PASS WITH WARNINGS (Ready for archive)

## Summary

The `model-catalog` SDD change has been successfully completed and archived. All 61 tasks across 8 slices (plus post-verify addendum) were delivered, with 722/722 tests passing, zero CRITICAL findings, and three WARNING-level findings addressed in a post-verify addendum before archive.

## Specifications Merged

| Spec | Action | Details |
|------|--------|---------|
| `model-catalog/spec.md` | NEW | Created `openspec/specs/model-catalog/spec.md` from delta spec. This is a new specification — no existing main spec existed for this domain. |

## Archives Preserved

- **Proposal**: `proposal.md` (archived with historical field name references `min_vram_bytes` intact as planning history)
- **Design**: `design.md` (archived with historical field name references `min_vram_bytes` intact as planning history)
- **Tasks**: `tasks.md` (archived; post-verify addendum A.1-A.3 documented but historical artifact preserved)
- **Verify Report**: `verify-report.md` (archived; includes detailed findings and closure notes)
- **Specification**: `specs/model-catalog/spec.md` (archived; reflects final corrected scenario text per A.3)

## Implementation Complete

- 12 source modules created under `src/tibios_ray/catalog/`
- 15 test modules created under `tests/unit/catalog/`
- 45+ concrete model entries across 17 families
- Zero production wiring — catalog remains inert reference data

## Post-Verify Addendum

Three WARNINGs from the initial verify-report verdict were closed without reopening:

- **A.1** (closes WARNING #1): Renamed `BackendSupport.min_vram_bytes` → `min_vram_gb` across all code; documentation retained old name as planning history
- **A.2** (closes WARNING #2): Corrected DeepSeek-V3/R1 fp8 footprint from 805 → 806 per MC13 formula
- **A.3** (closes WARNING #3): Updated `spec.md` scenario text to match implemented MC7 behavior

All changes passed 722/722 tests.

## Key Decision: Field Name History

Proposal.md, design.md, and pre-fix spec.md retain their historical references to `min_vram_bytes` (the original field name). This is INTENTIONAL — they document the planning and decision history of a completed change. The field was renamed to `min_vram_gb` during archive (post-verify addendum A.1), but documentation artifacts are preserved as-is to maintain audit trail. This follows the convention for archived changes: artifacts are immutable records of the process, not live documentation.

## Next Steps

The change is ready for production integration. The catalog is verified internally (no conflicts with descriptors, all 17 advertised families have entries) but has zero production callers — it awaits Object Store metadata query support (cross-repo, out of scope) before wiring into selection logic.

---

**Archive Location**: `openspec/changes/archive/2026-08-06-model-catalog/`

**Engram Observation IDs** (for traceability):
- Proposal: obs-id-68
- Spec: obs-id-69
- Design: obs-id-70
- Tasks: obs-id-71
- Verify-Report: obs-id-84
- Apply-Progress: obs-id-72
- Archive-Report: (this archive report)
