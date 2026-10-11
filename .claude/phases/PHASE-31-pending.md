# Phase 31 — Leg-history cost controls (tiered)
Status: PENDING

## Goal
Cut legislative-history agent cost per bill while keeping or improving grounding accuracy.

## Tasks
- [ ] `leg-history-tier` command: Full (landmark/federal/headline) = 4 lanes; Standard = spine + 1 combined lane with search/fetch caps; tier stored and overridable per bill
- [ ] Combined-lane researcher prompt variant with explicit caps (~8 searches / ~12 fetches)
- [ ] Pre-ground quotes (`ground_items`) inside `build-verifier-input`; verifier receives only string-matched quotes
- [ ] Media: ≤3 items from researcher; deterministic filter drops generic index/history/vote-list URLs
- [ ] Persist gate drops + per-run counts to `data/runs/<ts>/metrics.json`; `leg-history-stats` summary command
- [ ] Update `zwiad-leg-history.md` command for tiers
- [ ] Tests for tiering, pre-grounding, media filter, metrics
- [ ] DECISIONS.md entry

## Acceptance Criteria
- One Full and one Standard bill run end to end; metrics.json shows agent counts; Standard uses ≤3 agent calls
- No loss of grounding strictness (D43: gate never loosened)

## Decisions Made This Phase
