# Phase 23 — Federal enacted discovery
Status: DONE

## Goal
Add enacted-only federal discovery (`CongressSource.discover_laws` over `/law/{congress}/pub` + a `fetch-enacted-candidates` CLI) so the prior-years backfill never enriches a non-enacted bill.

## Tasks
- [x] Task 1 — `/law/{congress}/pub` discovery fixture + live shape confirmation
- [x] Task 2 — extract shared `_sweep_candidates` from `discover` (refactor, no behavior change)
- [x] Task 3 — `CongressSource.discover_laws`
- [x] Task 4 — `fetch-enacted-candidates` CLI (recall default, `--classify-all`, `--skip-existing`)
- [x] Task 5 — full quality gate + live smoke + ARCHITECTURE note

## Acceptance Criteria
- [x] `discover_laws(congress)` returns enacted-public-law candidates in `congress/type/number` id format.
- [x] `fetch-enacted-candidates --congress N` stages only topical enacted laws (recall default); `--classify-all` stages all; `--skip-existing` honors wiki + reject ledger.
- [x] Existing suite stays green (837 tests pass); new source + CLI tests pass; ruff + pyright clean.
- [x] Live smoke against the 118th confirmed `/law/118/pub` (274 enacted public laws reported); staged bills all have `enacted: true`.

## Decisions Made This Phase
- `/law/{congress}/pub` confirmed live as the enacted-only source: `{bills, pagination}` shape identical to `/bill`, so `_to_candidate` and the shared `_sweep_candidates` loop are reused directly.
- Recall default = two-stage `recall_filter` with `max_probe = len(scanned)` (probe the whole enacted set, no truncation); `--classify-all` bypasses recall for zero recall risk.
- `load_reference(topics)` loaded only in the recall (non-`--classify-all`) path — the `--classify-all` escape hatch does not depend on `topics.yaml`.
- Task 4's independent two-stage review was deferred (session usage limit) and folded into the final whole-phase review, which passed (Ready to merge).

## Reviews
- Tasks 2, 3: independent spec + code-quality review — passed.
- Task 4: controller-verified at commit time (gate green); independent review folded into final review.
- Final whole-phase review (opus, base b945ac4 → 7c51de5): Ready to merge, no Critical/Important issues; one optional Minor note (clarify `limit` also caps Stage-2 probe count).

## Plan
docs/superpowers/plans/2026-06-08-enacted-backfill-phase-23-federal-discovery.md
