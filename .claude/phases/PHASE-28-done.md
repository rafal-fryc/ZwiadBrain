# Phase 28 — Accuracy-fix campaign (2026-07-01 audit)
Status: ACTIVE

## Goal
Apply every CONFIRMED accuracy fix (Priority 1–4) from `docs/accuracy-fixes-TODO.md` to the wiki pages, in both frontmatter and mirrored body, then reindex — without touching the "Suspected" list or pipeline-derived values.

## Note on PHASE-26
PHASE-26 (enacted-laws backfill campaign) remains open but is paced across sessions;
this accuracy pass is a distinct, self-contained workstream inserted ahead of it per user request.

## Tasks
- [ ] Federal: 118-hr-2670, 119-hr-9076, 119-s-146
- [ ] California (2019/2021): ab-1130, ab-1146, ab-1281, ab-1355, ab-1564, ab-825, ab-2273
- [ ] California (2023/2025): ab-1824, ab-1836, ab-2602, ab-2013, ab-3030, ab-801, sb-362, sb-793, sb-1223, sb-833, ab-1064, ab-1337(summary only), ab-979, sb-53
- [ ] Texas: sb-2013, sb-15, sb-2116, hb-4, sb-768, sb-2105
- [ ] New York: a-5635, s-2659, s-7676, s-7694
- [ ] Colorado: hb-1197, hb-1041, sb-171, hb-1139, sb-205, hb-1104
- [ ] Illinois: hb-4875, hb-2557, hb-2954, sb-2979, hb-3773 + ILGA link migration (all IL)
- [ ] Virginia: hb-2024, hb-707, hb-714, hb-2307
- [ ] Washington: hb-1071, hb-1155
- [ ] P4 systematic: chamber House→Assembly (CA), source_type CREC→state, Conference Sub→Governor's substitute (VA)
- [ ] reindex + git diff review

## SKIP (pipeline/refresh-only — hand to user, do NOT hand-edit)
- Off-by-one Senate-floor Ayes in Status & Timeline: ca-2023 ab-2013/ab-1824/ab-1836/ab-2602/ab-801
- Stale refreshes: ca-2025-sb-354, ca-2025-ab-1337 (June-2026 actions), va-2026-sb-85, wa-2025-hb-1671
- CO 2026 epoch dates (1969-12-31): hb-1139, hb-1210, sb-189
- Entire "Suspected issues to adjudicate" section

## Acceptance Criteria
- Every checked P1–P4 content item applied in BOTH frontmatter and body.
- Verbatim quotes preserved except the specified typo/misattribution fixes.
- reindex run clean; diffs reviewed; nothing committed (left for user review).

## Decisions Made This Phase
- 2026-07-02: Refresh-only items deferred to pipeline, not hand-edited (would be overwritten on next refresh).
- 2026-07-02: Suspected-issues list excluded from scope (not confirmed; needs user adjudication).
