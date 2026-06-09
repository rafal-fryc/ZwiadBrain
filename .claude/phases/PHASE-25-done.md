# Phase 25 — Orchestration & campaign tracking
Status: DONE

## Goal
Wire the new enacted discovery into deliberate, per-unit campaign orchestration: two thin slash commands plus a resumable campaign tracker and a leg-history follow-up queue.

## Tasks
- [x] `.claude/commands/zwiad-backfill-enacted.md` (federal: fetch-enacted → classify → apply-verdicts → record-rejects → batch-summarize → apply-summaries → [amendments] → render → reindex, stop before commit)
- [x] `.claude/commands/zwiad-backfill-enacted-state.md` (state analog; resolves --year → session)
- [x] `docs/backfill/enacted-campaign.md` — unit checklist (3 federal + ~21 state units, status + counts)
- [x] `docs/backfill/leg-history-queue.md` — flagged significant laws for later per-law `/zwiad-leg-history`
- [x] DECISIONS.md entries D84 (enacted-first discovery) + D85 (per-unit batching) ; README/ARCHITECTURE notes

## Acceptance Criteria
- [x] Both slash commands run the full resumable flow against enacted discovery and stop before commit for review.
- [x] The campaign tracker enumerates every (jurisdiction × period) unit with a status; the leg-history queue captures flagged laws.
- [x] D84/D85 logged; ARCHITECTURE/README mention the enacted campaign commands.

## Verification
- All CLI commands/flags referenced by the slash commands verified to exist (`fetch-enacted-candidates`, `fetch-state-enacted-candidates`, `apply-verdicts`, `record-rejects`, `apply-summaries`, `render-classified`, `reindex`); subagent names (`classifier`, `batch-summarizer`, `amendment-explainer`) match `.claude/agents/`.
- Consistency review (subagent) vs the proven `zwiad-backfill.md`/`zwiad-scan-states.md`: structurally consistent, correct `--scope` per command, `Edit` in allowed-tools for the tracker update; two minor wording nits fixed ("staged" → working-tree; clarified the no-session error-recovery note).
- Full suite still green (849 tests) — PHASE-25 is markdown-only, no code change.

## Notes
PHASE-25 is markdown/docs authoring (orchestration prompts + tracker + DECISIONS), so no TDD/code-review loop applied — verified by CLI-surface check + a consistency review subagent instead.

## Plan
Per the spec (§6, §8, §12); no separate bite-sized plan doc — the deliverables are fully specified there.
