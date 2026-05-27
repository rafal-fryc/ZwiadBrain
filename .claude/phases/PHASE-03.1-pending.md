# Phase 03.1 — Federal discovery recall (inserted)
Status: PENDING

> Inserted after the Phase-04 UAT surfaced it. Do NOT start until the Phase-04 UAT
> is complete and the user approves starting this phase (one active phase at a time).

## Goal
Make federal discovery reliably surface topical (AI/privacy/cyber) bills, instead of
missing them because they fall outside the newest-updated window or carry no seed in
their title.

## Root cause (observed in the Phase-04 UAT, 2026-05-27)
`fetch-candidates --congress 118 --limit 5` returned **0** candidates. Three compounding
causes, all in Phase-03 discovery (the Phase-04 LLM pipeline is fine — it was simply
starved of input):
1. **Wrong axis.** `CongressSource.discover` queries `/bill/{congress}` with `sort=updateDate desc`
   and no keyword/full-text search. For a historical congress (118th ended Jan 2025),
   "newest-updated" is an arbitrary cluster (currently finance/housing), unrelated to our topics.
2. **Title-only filter.** `keyword_filter` matches the bill *title* only; the candidate object
   carries no summary at discovery time. In-scope bills without a seed phrase in the title are invisible.
3. **Tiny window.** `limit 5 × oversample 5 = 25` bills examined. Measured topical hit rate over
   the API's 250-item single-request max was ~3/250 (~1.2%) → expected ~0.3 hits in 25 → 0 is normal.
   (This is the same gap the Phase-03 smoke test saw: seeded run → 0, no-seed "worked" only by keeping
   the newest 5 regardless of topic. Phase-03 was marked done because the no-filter path met its AC.)

## Tasks
- [ ] **Verify the API first.** Confirm against the live Congress.gov v3 docs/endpoints whether bill
  discovery supports any keyword/query parameter or a `fromDateTime`/`toDateTime` since-window. (PLAN.md
  claimed "keyword text search" — confirm or refute; that assumption drives the fix.)
- [ ] Choose a recall strategy from the findings: (a) use a real search/query param if one exists;
  (b) else paginate deeper than 250 over a since-window with `offset`; and/or (c) filter on
  `summary` + `policy_area` rather than title-only (accepting a light pre-fetch, or using fields the
  list endpoint already returns).
- [ ] Update `sources/congress.py` `discover` and/or `pipeline/discover.py` `keyword_filter` accordingly,
  keeping discovery deterministic and offline-testable (respx fixtures for pagination / since-window).
- [ ] Re-validate: a seeded `fetch-candidates --congress 118` returns a non-empty, genuinely topical set.

## Acceptance Criteria
- [ ] Seeded `fetch-candidates --congress 118 --limit 5` returns topical (AI/privacy/cyber) bills, not 0.
- [ ] The chosen recall strategy and the verified API capability are recorded in DECISIONS.md.
- [ ] Tests cover the new discovery behavior (pagination/since/summary-axis as applicable); pytest + ruff + pyright green.

## Decisions Made This Phase
(append during the phase)
