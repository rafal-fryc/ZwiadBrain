# Phase 18 — Near-duplicate statement dedup (speaker-normalized, post-grounding)
Status: DONE

> Phase E continuation. Closes the dedup gap surfaced in PHASE-17's SB-53 UAT:
> the press-lane "Gavin Newsom" and signing-lane "Gov. Gavin Newsom" near-dup
> (identical quote) grounds twice because merge dedup keys on the exact
> `(speaker, quote)` tuple.

## Goal
Collapse near-duplicate statements that differ only by speaker honorific/title or
quote typography, so the same quote is listed once — WITHOUT ever dropping a
groundable copy in favor of an ungroundable one.

## Tasks
- [x] `_normalize_speaker(speaker)` in leg_history.py — lowercase, curly->ASCII, periods
      to spaces, strip leading honorifics/titles via `_SPEAKER_HONORIFICS`, guard never
      empties the name
- [x] Pure helper `dedup_statements(statements)` keyed by
      `(_normalize_speaker(speaker), _normalize_text(quote))`, first-wins, order-stable
- [x] Apply it in render-leg-history to `result.statements` (POST-grounding, not at merge)
      so the surviving copy is always one that grounded
- [x] Summary line: added a `near-dup` collapse count; input/grounded/drop reconciliation
      stays exact (gate ground-drops measured against the pre-dedup grounded set)
- [x] TDD: 6 dedup unit tests + 3 `_normalize_speaker` unit tests + 1 render-integration
      near-dup-collapse test (RED->GREEN)
- [x] Gate: pytest 753 (+9), ruff clean, no NEW pyright errors (see UAT note)
- [x] Decision log entry (D77)

## Acceptance Criteria
- [x] Two statements with the same normalized speaker+quote collapse to the first grounded one
- [x] Statements with genuinely different speakers OR different quotes are NEVER collapsed
- [x] merge_lanes exact-tuple dedup stays byte-unchanged (post-grounding dedup is additive)
- [~] No grounding-yield regression — proven by the render-integration test; the live SB-53
      re-render is DEFERRED to a batched live UAT after the fetch-layer phases (19/20)
- [x] Full gate green (pytest + ruff; pyright unchanged vs main baseline)

## UAT / gate note
- pytest: 744 -> 753 (+9). ruff: clean.
- pyright: 20 errors BOTH before and after this change. They are all pre-existing on
  clean `main` (third-party stub gaps: `frontmatter`, `youtube_transcript_api` in
  transcripts.py/schema.py/test_agents.py/test_schema.py) — NONE in files touched here.
  My changed files (leg_history.py, cli.py, test_cli.py, test_leg_history.py) are
  pyright-clean. The PHASE-17 "pyright clean" claim was evidently a scoped/CI run;
  the standing local 20-error baseline is a separate cleanup candidate, not a regression.

## Notes / Risks
- WHY post-grounding, not merge-time: merge dedup is first-wins by LANE_ORDER; the
  press-lane copy (JS-rendered URL, drops) sorts before the signing-lane copy
  (gov.ca.gov, grounds). Collapsing at merge could keep the ungroundable copy ->
  grounding regression. Deduping among ALREADY-grounded statements is regression-safe.
- Speaker normalization is paired with quote normalization in the key, so two DIFFERENT
  officials would have to share a verbatim 20+ char quote AND a normalized name to wrongly
  collapse — vanishingly unlikely; documented as accepted residual risk (D77).

## Decisions Made This Phase
- **D77 (2026-06-07)** — Near-duplicate statements collapse POST-grounding, keyed by
  normalized speaker + quote; merge_lanes exact-tuple dedup unchanged. Full rationale in
  DECISIONS.md D77.
