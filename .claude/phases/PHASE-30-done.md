# Phase 30 — Relevance & pull correctness
Status: DONE

## Goal
Make enacted-law discovery and classification correct by construction, so hand overrides and silent misses stop.

## Tasks
- [x] Encode D86/D88/D91/D95 scope rulings (election-actor duty test, person-facing criminal deepfake/CSAM, government-use, data brokers, critical-infrastructure cyber) into `reference/topics.yaml` — narrowing-only, so NO `scope_version` bump (D116)
- [x] Regression set A (70 tracker-gap bills) — 36/38 overrides auto-rejected, 28/32 in-scope held; 6 mismatches ruled on by the user (D117)
- [x] Regression set B: known misses — 3/4 now land IN automatically (PL 118-50 via its data-broker snippet, NY SHIELD and WA MHMD via text snippets). CIRCIA still OUT: the 117-hr-2471 CRS summary never mentions it, so no input repair can surface it (documented limitation; omnibus riders still need the law-brain / tracker cross-checks).
- [x] CLI `stage-classifier-batches`: formalize ~15-bill batching and seed-hit snippets from text sidecars when the summary is thin (≈ title) or oversized (replaces ad hoc `mega_*.json`)
- [x] Update `classifier.md` for batch input/output; update both enacted commands to use the new step
- [x] Fix silent `[:limit]` truncation (`cli.py` federal + state enacted fetches): fail loudly or page fully
- [x] Make `--classify-all` the federal enacted default (D87)
- [x] Tests for batching, snippet selection, truncation guard
- [x] DECISIONS.md entry (D116)

## Acceptance Criteria
- Regression set lands correctly with zero manual overrides (or each remaining one documented)
- No enacted fetch can drop candidates without an error
- pytest green

## Decisions Made This Phase

- 2026-10-11 — **User decision:** encode the D86/D91 election-actor and person-facing criminal
  rules into `reference/topics.yaml`, reversing the PHASE-29 per-bill-override choice (38 hand
  overrides). `scope_version` bumps; existing rejects are only marked stale (D96), not re-run.
- 2026-10-11 — User rulings on regression mismatches (D117): VA HB 797 / SB 384 removed to the
  reject ledger; VA HB 580 kept. TX HB 581 flipped IN on enacted text (operator duties).
  NE LB 383 unresolved — enacted text extracts but the social-media act sections were not
  located; left OUT pending manual review.
- 2026-10-11 — Found while testing thin-summary repair: Docling `max_num_pages` rejected every
  PDF over 12 pages (44 empty sidecars). Fixed on `fix/docling-page-range` (D119), user-approved.
- 2026-10-11 — On `fix/docling-page-range` (user-approved): 20 empty sidecars recovered and 16
  summaries rewritten from enacted text; `truststore` added for UT/CT TLS chains and the text-layer
  pass raised to 60 pages (D120). Merge that branch before regression set B so thin-summary
  repair can actually fetch text.
- 2026-10-11 — Closed. Both branches squash-merged to main (732f500, cc6df70). Known
  limitations carried forward: omnibus riders absent from the CRS summary (CIRCIA class);
  12 sidecars still empty on portal issues (VA/IN JS pages, IL/MT/TN dead links, CO endpoint);
  NE LB 383 unresolved; 16 FTC enforcement sidecars stashed (stash@{0}) pending approval.
