# Phase 25 — Orchestration & campaign tracking
Status: PENDING

## Goal
Wire the new enacted discovery into deliberate, per-unit campaign orchestration: two thin slash commands plus a resumable campaign tracker and a leg-history follow-up queue.

## Tasks
- [ ] `.claude/commands/zwiad-backfill-enacted.md` (federal: fetch-enacted → classify → apply-verdicts → record-rejects → batch-summarize → apply-summaries → [amendments] → render → reindex, stop before commit)
- [ ] `.claude/commands/zwiad-backfill-enacted-state.md` (state analog; loops sessions for the state/year)
- [ ] `docs/backfill/enacted-campaign.md` — unit checklist (all federal + state units, status + counts)
- [ ] `docs/backfill/leg-history-queue.md` — flagged significant laws for later per-law `/zwiad-leg-history`
- [ ] DECISIONS.md entries D84 (enacted-first discovery) + D85 (per-unit batching) ; README/ARCHITECTURE notes

## Acceptance Criteria
- Both slash commands run the full resumable flow against enacted discovery and stop before commit for review.
- The campaign tracker enumerates every (jurisdiction × period) unit with a status; the leg-history queue captures flagged laws.
- D84/D85 logged; ARCHITECTURE/README mention the enacted campaign commands.

## Acceptance gate
Do not start until PHASE-24 is DONE and user-approved.
