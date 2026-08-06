# Archive Report: capability-providers

**Change**: capability-providers (roadmap Phase 2 of archived `ray-worker-runtime`)
**Archived**: 2026-08-06
**Artifact Store Mode**: hybrid (file + Engram)
**Archive Location**: `openspec/changes/archive/2026-08-06-capability-providers/`

---

## SDD Cycle Summary

The `capability-providers` change is now complete, implemented, verified, and archived. All 7 slices of work (6 Provider modules + errors module, plus post-verify addendum) have been delivered, tested, and merged. The change fulfills roadmap Phase 2: make the Worker's capability catalog truthful and real before Phase 4's engine integration.

---

## Artifact Traceability (Engram Topic Keys + Observation IDs)

All artifacts are persisted in both the hybrid filesystem archive and Engram. The observation IDs below enable recovery of full content across sessions.

| Artifact | Topic Key | Observation ID | Status |
|----------|-----------|---|---|
| Proposal | `sdd/capability-providers/proposal` | #51 | Archived |
| Specification | `sdd/capability-providers/spec` | #52 | Merged to main spec |
| Design | `sdd/capability-providers/design` | #54 | Archived |
| Tasks | `sdd/capability-providers/tasks` | #57 | Archived |
| Apply Progress | `sdd/capability-providers/apply-progress` | #58 | Archived |
| Verification Report | `sdd/capability-providers/verify-report` | #66 | Archived |
| Archive Report | `sdd/capability-providers/archive-report` | *(this save)* | Creating now |

---

## Specs Synced to Main

**New Specification**:
- **Source**: `openspec/changes/capability-providers/specs/capability-providers/spec.md`
- **Destination**: `openspec/specs/capability-providers/spec.md` (new spec directory)
- **Action**: Full spec copied (not a delta; this is the spec's first archive)
- **Content**: Defines all 7 Providers, their descriptors, registry behavior, and binding invariants

---

## Archive Contents

The entire change folder has been moved to `openspec/changes/archive/2026-08-06-capability-providers/` with the following structure:

```
2026-08-06-capability-providers/
├── ARCHIVE-REPORT.md          (this file)
├── proposal.md                (Phase 1: intent, scope, risks, rollback)
├── design.md                  (Arch decisions CP1-CP8, FLC rule, testing strategy)
├── tasks.md                   (35 tasks: 7 slices + 1 post-verify addendum, all complete)
├── verify-report.md           (PASS WITH WARNINGS: 0 CRITICAL, 2 WARNINGs, 2 SUGGESTIONs)
└── specs/
    └── capability-providers/
        └── spec.md            (Requirements: descriptors, registration, failure, invariants)
```

All artifacts preserved exactly as they were at completion and verification time. No modifications made during archive.

---

## Implementation Summary

- **Total tasks**: 35 (7 slices × 5 tasks each, +1 post-verify)
- **Test suite**: 284 tests, all passing (277 original + 7 new zero-declared-fields parametrized cases)
- **Code changes**: ~1035 lines across 7 modules + errors module + 9 test modules
- **Providers delivered**: 7 across 6 source modules
  - Chat (chat.py)
  - Embedding (embedding.py)
  - Rerank (rerank.py)
  - Vision (vision.py)
  - Speech Transcription (speech.py)
  - Speech Synthesis (speech.py)
  - OCR (ocr.py)

---

## Verification Verdict

**PASS WITH WARNINGS** (per `sdd/capability-providers/verify-report`, ID #66)

- **Critical Issues**: 0 — No blockers to archive
- **Warnings** (process/robustness, not functional):
  1. "Providers hold no backend reference" had no dedicated automated regression test before this change. This gap was **closed post-verify** (task A.1 in tasks.md) by adding `test_provider_declares_no_fields` to the conformance harness, parametrized over all 7 Providers. Mutation-tested and confirmed green (284/284 tests).
  2. Git history does not independently preserve RED-before-GREEN commits per slicing. Each slice lands as one squashed commit. TDD compliance rests on apply-progress narrative. No correctness defect; audit trail is weakened only.
- **Suggestions** (nice to have):
  1. Zero-field regression guard added and permanent (closed WARNING #1).
  2. Design's Open Questions remain open (gemma dual-capability, paligemma/mixtral, Provider construction cost) — correctly deferred for Phase 3 or `proto-worker-contract`.

---

## Open Items & Known Limitations

### Not Yet Wired
- **Worker integration**: Blocked on `.proto` contract (`proto-worker-contract` sibling change in `tibios-core`). Providers will not be instantiated in `worker.py` until that change lands and Phase 4 begins.
- **Real backend/engine dispatch**: Phase 4. All seven Providers currently raise `NoBackendAvailableError` unconditionally (by design).

### Design Deferred (Correctly)
- Phase 3: Model Catalog (metadata beyond catalog data)
- Phase 4: Real backend integration and execution
- Phase 4: New backend protocols for vision, speech synthesis, and OCR

### Catalog Quirks (Intentional)
- `gemma` appears under both `chat.generate` and `vision.understand` — truthful because Gemma 3 is natively multimodal. No test enforces cross-Provider family uniqueness.
- Family labels follow the Family Label Convention (FLC), a pure function of published lineage names, enabling exact matching across Phase 3's Model Catalog without a synonym table.

---

## Quality Metrics

| Metric | Result |
|--------|--------|
| Type Check (pyright) | 0 errors, 0 warnings, 0 informations |
| Linting (ruff) | All checks passed |
| Test Coverage | 284 tests passed (no coverage tool configured) |
| Strict TDD | PASS (with caveat: squashed git history) |
| Design Coherence | 9/9 architecture decisions followed |
| Spec Compliance | 8/9 scenarios fully compliant; 1/9 structurally true, now with automated guard |

---

## Rollback & Recovery

**Purely additive change**: Seven new source modules, nine new test modules, one `__init__.py` export edit. No frozen module modified, no contract reshaped, no spec requirement changed.

- **Rollback**: `git revert` of all 7 slice commits + post-verify addendum commit restores the archived `ray-worker-runtime` state exactly.
- **Recovery**: Full artifact content available in Engram via observation IDs listed above (hybrid mode). Files archived in `openspec/changes/archive/2026-08-06-capability-providers/` for team review.

---

## SDD Cycle Close

The `capability-providers` change has moved through the complete SDD workflow:

1. ✅ **Proposal** (sdd-propose) — intent, scope, approach, risks
2. ✅ **Specification** (sdd-spec) — formal requirements and scenarios
3. ✅ **Design** (sdd-design) — architecture decisions, contracts, testing strategy
4. ✅ **Tasks** (sdd-tasks) — 7 work slices, delivery strategy (auto-chain)
5. ✅ **Implementation** (sdd-apply) — 7 PRs delivered, all merged; post-verify addendum
6. ✅ **Verification** (sdd-verify) — PASS WITH WARNINGS, no critical blockers
7. ✅ **Archive** (sdd-archive) — this report, specs synced, change folder archived

**Status**: Ready for the next change. No follow-up needed unless Phase 3 or Phase 4 work is immediately required.

---

## Files Archived

- `openspec/changes/archive/2026-08-06-capability-providers/proposal.md` — 84 lines
- `openspec/changes/archive/2026-08-06-capability-providers/design.md` — 342 lines
- `openspec/changes/archive/2026-08-06-capability-providers/tasks.md` — 94 lines
- `openspec/changes/archive/2026-08-06-capability-providers/verify-report.md` — 123 lines
- `openspec/changes/archive/2026-08-06-capability-providers/specs/capability-providers/spec.md` — 89 lines

**Also created during archive**:
- `openspec/specs/capability-providers/spec.md` — main spec (merged from delta)

---

## Archive Date

2026-08-06 — corresponds to today's date when the archive was finalized.

