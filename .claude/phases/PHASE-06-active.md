# Phase 06 — Watchlist refresh (Pass A) + PHASE-05 leftovers
Status: ACTIVE

> Full design: `docs/superpowers/specs/2026-05-28-phase06-watchlist-refresh-design.md`.
> Full plan: `docs/superpowers/plans/2026-05-28-phase06-watchlist-refresh.md`.
> Decisions to log this phase: D39 (re-classify on refresh, narrowly overrides D9) and D40 (`leg_history.narrative` persists to frontmatter, extends D37).
> TDD throughout (test first, watch it fail, implement, watch it pass, commit). Atomic commits per task.

## Goal
Ship `/zwiad-refresh`: a deterministic-Python + subagent slash command that re-fetches every tracked federal bill, dispatches classifier/summarizer/amendment-explainer only on real change, preserves PHASE-05 leg-history (hearings/statements/narrative) across the refresh, and flips out-of-scope bills to `tracking: false` without deletion. Also closes PHASE-05's `Enactment.statutes_at_large` and grounding-gate-recall gaps.

## Tasks
- [ ] T1 — models: cursor fields + FlipOutAudit + StatutesAtLarge
- [ ] T2 — congress source: map bare update dates + per-amendment date
- [ ] T3 — enrich: compute summary_hash + amendments_count
- [ ] T4 — schema: round-trip new fields + leg_history.narrative
- [ ] T5 — templates: flipped-out audit marker + Statutes-at-Large link
- [ ] T6 — pipeline/refresh.py: pure functions
- [ ] T7 — cli `fetch-refreshable`
- [ ] T8 — cli `render-refreshed`
- [ ] T9 — slash command `/zwiad-refresh`
- [ ] L1 — GovInfo Statutes-at-Large fetch + spine wire-through
- [ ] L2 — grounding gate BeautifulSoup text-extract
- [ ] T10 — DECISIONS.md D39 + D40
- [ ] T11 — quality gate + version bump 0.6.0 + tag
- [ ] T12 — interactive UAT (Pass A + L1 + L2)

## Acceptance Criteria
- [ ] `/zwiad-refresh` on the existing 118-hr-2670 page reports `unchanged` and leaves `git status` clean.
- [ ] On a deliberately-stale fixture or live bill, `/zwiad-refresh` refreshes only the changed bill; subagents dispatch only where triggers fired; `leg_history.hearings/statements/narrative` survive byte-for-byte.
- [ ] IN→OUT classifier verdict sets `tracking: false`, prepends the flipped-out audit marker, keeps `topics` intact, never deletes the page.
- [ ] `Enactment.statutes_at_large` populates for 118-hr-2670 and renders as a clickable link.
- [ ] A JS-rendered `.senate.gov` press-release fixture previously rejected by the gate is now accepted; a genuinely-absent quote is still rejected.
- [ ] ruff + pyright (strict) + pytest all green.
- [ ] DECISIONS.md carries D39 + D40.
- [ ] v0.6.0 tagged.

## Decisions Made This Phase
(append as the phase runs)
- D39 — `/zwiad-refresh` re-classifies on every text-changed bill, narrowly overriding D9 for routine refresh. Justification + trade-offs in the spec §11.
- D40 — `LegHistory.narrative` persists to frontmatter alongside hearings/statements, extending D37's partial-persistence carve-out. Justification + trade-offs in the spec §11.
