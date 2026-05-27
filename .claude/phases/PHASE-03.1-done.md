# Phase 03.1 — Federal discovery recall (inserted)
Status: DONE

> Activated and completed 2026-05-27 after the Phase-04 UAT surfaced the recall gap.

## Outcome (2026-05-27)
Two-stage recall built and gated green (97 pytest, ruff, pyright strict): `topics.yaml`/`loader`
`policy_areas`; `Source.fetch_policy_area` (Congress: one core-detail GET); `pipeline.recall_filter`
(Stage 1 title keyword ∪ Stage 2 bounded policyArea probe, cap to `limit`); `fetch-candidates` now
scans wide (250) and runs `recall_filter` (default seeds + broad policyArea allowlist; explicit `--seed`
stays Stage-1-only). Offline e2e proves a title-miss bill is recovered via its `policyArea`. DECISIONS #33.
**Deferred:** comprehensive historical backfill via offset pagination (logged in #33) — left for a future
phase; v1 recalls from the newest-updated 250 + the probe. Live re-validation (seeded `fetch-candidates
--congress 118`) is the user's to run with a key.

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

## Verified API capability (Task 1, done 2026-05-27)
Per the official Congress.gov v3 bill-endpoint docs:
- **No keyword/full-text search** on `/bill` — only congress + bill-type filtering. PLAN.md's "keyword text search" was never real.
- List items carry **title + `latestAction` + dates only**; `policyArea`/`subjects` exist only on the per-bill **detail** fetch.
- The list is cheap (≤250 items/request) and supports **offset** pagination and a **`fromDateTime`/`toDateTime`** since-window.

## Approach (confirmed with user) — two-stage recall
- **Stage 1 — wide list scan (free):** paginate `/bill/{congress}` (250/page, offset) up to a scan cap, or use the `fromDateTime` since-window; keyword-filter on **title** (Stage-1 = the existing `keyword_filter`). Wide-scan alone fixes the 0-result.
- **Stage 2 — bounded policyArea probe:** for bills Stage 1 didn't keep, fetch the core detail (1 GET each, bounded by `max_probe=250`) and keep those whose `policyArea` ∈ the `topics.yaml` allowlist. Catches topical bills whose titles lack a seed.
- Candidates = Stage 1 ∪ Stage 2, capped to the output `limit`; full enrichment + the Claude classifier run only on the final candidates.
- **Params (confirmed):** broad `policy_areas` allowlist (6 entries); `max_probe = 250`.

## Tasks
- [x] Verify the API (above).
- [x] `reference/topics.yaml` + `reference/loader.py`: add a `policy_areas` allowlist; `Reference` gains `policy_areas`.
- [ ] `cli.py` `fetch-candidates`: scan **wide** (one request, up to 250) instead of `limit×5`. (`discover` already returns ≤250/request and honors `since`→`fromDateTime`; no discover code change for v1.)
- [ ] `sources/base.py` + `sources/congress.py`: add `fetch_policy_area(native_id) -> str | None` (core-detail GET) to the `Source` protocol; Congress implements it.
- [ ] `pipeline/discover.py`: add `recall_filter(candidates, source, *, seeds, policy_areas, limit, max_probe)` doing Stage 1 (title keyword) ∪ Stage 2 (policyArea probe, bounded by `max_probe`), capped to `limit`.
- [ ] `cli.py` `fetch-candidates`: wire `discover` (wide scan) → `recall_filter` (seeds + policy_areas from `topics.yaml`) → stage to `candidates.json`.
- [ ] DECISIONS.md: record the verified API limitation + the two-stage recall design + the deferral below.

> **Deferred (noted, not built here):** comprehensive historical backfill via offset pagination over a whole congress. v1 recalls from the **newest-updated 250** bills + the policyArea probe — this fixes the acute "0 candidates" failure and adds real recall within the window, but topical bills not recently updated in a historical congress are still out of reach until pagination lands. Logged for a future phase.

## Acceptance Criteria
- [ ] Offline (respx + fake source): `recall_filter` surfaces a title-miss bill via its `policyArea`, keeps title matches, and probes at most `max_probe` bills.
- [ ] `fetch_policy_area` returns the bill's `policyArea` name from the core detail (respx).
- [ ] Offline e2e: a `fetch-candidates` run where a topical bill has no title seed but an allowlisted `policyArea` lands it in `candidates.json`.
- [ ] The verified API capability + two-stage design + pagination deferral are recorded in DECISIONS.md.
- [ ] pytest + ruff + pyright (strict) all green.
- [ ] Live re-validation (user, with key): seeded `fetch-candidates --congress 118 --limit 5` returns topical bills.

## Decisions Made This Phase
(append during the phase)
