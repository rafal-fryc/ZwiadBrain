# Phase 06 — Watchlist refresh (Pass A) + PHASE-05 leftovers
Status: DONE

> Full design: `docs/superpowers/specs/2026-05-28-phase06-watchlist-refresh-design.md`.
> Full plan: `docs/superpowers/plans/2026-05-28-phase06-watchlist-refresh.md`.
> Decisions logged this phase: D39 (re-classify on refresh, narrowly overrides D9) and D40 (`leg_history.narrative` persists to frontmatter, extends D37).
> TDD throughout (test first, watch it fail, implement, watch it pass, commit). Atomic commits per task.

## Outcome (2026-05-28)
PHASE-06 shipped on `feature/phase-06-watchlist-refresh` (~17 commits, 301 tests + ruff + pyright strict all green, v0.6.0). New `/zwiad-refresh` slash command pairs `fetch-refreshable` (scans wiki frontmatter, re-fetches via Congress.gov, compares cursors, re-derives leg-history spine on enacted bills) with `render-refreshed` (applies D38+D40 preservation + IN→OUT classifier flip + reindex). New `pipeline/refresh.py` keeps the trust-boundary logic (cursor diff, preservation, flip audit) as pure functions. Frontmatter persistence extended via D40 to carry `leg_history.narrative` alongside hearings/statements. PHASE-05 leftovers closed: `Enactment.statutes_at_large` populated from GovInfo `/related/PLAW/STATUTE` as a typed `StatutesAtLarge(citation, url)` model (L1); deterministic grounding gate now extracts page text via BeautifulSoup before substring-matching (L2).

**Live UAT (118-hr-2670 NDAA FY2024 — same bill as PHASE-05):**
- `/zwiad-leg-history 118/hr/2670` re-ran the full pipeline end-to-end. Researcher produced 14 candidate statements; opus verifier returned 13 verified / 1 dropped (caught Reed pay-quote truncation: researcher transcribed `pay.` but CREC reads `pay--one of the largest in decades`). Deterministic gate further dropped 7 verifier-approved-but-not-truly-verbatim quotes (researcher had concatenated separately-attributed sentences across attribution boundaries) — precision-first design working. Final: **6 grounded statements** (Rogers ×2 sponsor / Smith / Pelosi / Schumer / Wicker), down from PHASE-05's 9 due to research variance (research-pass variation, not a code defect).
- **L1 confirmed live:** rendered page now shows `- Statutes at Large: [STATUTE-137](https://www.govinfo.gov/app/details/STATUTE-137)` in the Enactment block. (GovInfo returned the STATUTE row with an empty title field, so L1's documented fallback-to-packageId path triggered. Link resolves and is auditable; cleaner citation extraction is a future polish item.)
- **D40 confirmed live:** `leg_history.narrative` (1160 chars of Legislative Journey prose) now persists in frontmatter and round-trips cleanly.
- **L2 partial:** BeautifulSoup extraction works on the real senate.gov pages (extracts 7957 chars from a 28984-byte HTML response on wicker.senate.gov). The 2 senator press releases in the UAT still dropped — root cause is researcher-side, not extraction-side: the page reads `"…military," Senator Wicker said. " Enemies…"` (two separately-attributed sentences) and the researcher concatenated them into one merged pseudo-quote. The L2 contract holds; verifier strictness is the remaining bottleneck.
- **`/zwiad-refresh` cheap-path gate:** `fetch-refreshable` on the now-fresh page returned `[]` — clean idempotent no-op.
- **`/zwiad-refresh` stale-bill detection:** when frontmatter cursors were mutated to a stale state, `fetch-refreshable` correctly detected the bill, emitted the right triggers (`needs_classifier=true`, `needs_summarizer=true`, 20 changed amendments), and re-derived the leg-history spine (STAL populated again through the spine re-derive path) — end-to-end Pass A detection layer validated. The slash command's full subagent orchestration wasn't fired in UAT (would burn ~22 dispatches on the same bill; detection-layer validation was the goal).

**Three open follow-ups discovered in UAT (non-blocking, named for next phase):**
- `render-leg-history` doesn't stamp `summary_hash` and `amendments_count` on the rendered page (those are computed in `enrich()` and `fetch-refreshable`, not in `render-leg-history`). Impact: first `/zwiad-refresh` after any leg-history regeneration sees `prev.summary_hash=None ≠ fresh.summary_hash=<hex>` and falsely flags `text_changed=True`. Self-heals after one refresh run. Easy fix: have `render-leg-history` compute both.
- Verifier subagent is too generous on merged-attribution pseudo-quotes (accepted 7 cases the deterministic gate then correctly rejected). Tighten the verifier's contiguous-substring contract OR constrain the researcher to single-attribution quotes.
- STATUTE citation falls back to packageId (`STATUTE-137`) when GovInfo's title field is empty. A future improvement: fetch the package summary for a human-readable `"NNN Stat. NNN"` form.

Plus the final-reviewer follow-ups from before UAT (also non-blocking):
- `Bill.id.split("-")` could raise unhandled `ValueError` on a corrupt page id (I1).
- A single malformed `.md` file aborts the whole `fetch-refreshable` scan; per-page error isolation would be more resilient (I2).
- T7's in-function `_summary_hash` import could swap to `refresh.summary_hash` (public) and drop the two `noqa`/`pyright: ignore` pragmas.
- `/zwiad-backfill --force <id>` to re-track a flipped-out bill is named in the design spec §12 and D39 "Revisit if" but not yet implemented.

## Goal
Ship `/zwiad-refresh`: a deterministic-Python + subagent slash command that re-fetches every tracked federal bill, dispatches classifier/summarizer/amendment-explainer only on real change, preserves PHASE-05 leg-history (hearings/statements/narrative) across the refresh, and flips out-of-scope bills to `tracking: false` without deletion. Also closes PHASE-05's `Enactment.statutes_at_large` and grounding-gate-recall gaps.

## Tasks
- [x] T1 — models: cursor fields + FlipOutAudit + StatutesAtLarge
- [x] T2 — congress source: map bare update dates + per-amendment date
- [x] T3 — enrich: compute summary_hash + amendments_count
- [x] T4 — schema: round-trip new fields + leg_history.narrative
- [x] T5 — templates: flipped-out audit marker + Statutes-at-Large link
- [x] T6 — pipeline/refresh.py: pure functions
- [x] T7 — cli `fetch-refreshable`
- [x] T8 — cli `render-refreshed`
- [x] T9 — slash command `/zwiad-refresh`
- [x] L1 — GovInfo Statutes-at-Large fetch + spine wire-through
- [x] L2 — grounding gate BeautifulSoup text-extract
- [x] T10 — DECISIONS.md D39 + D40
- [x] T11 — quality gate + version bump 0.6.0 + tag
- [x] T12 — interactive UAT (Pass A + L1 + L2)

## Acceptance Criteria
- [x] `/zwiad-refresh` on the existing 118-hr-2670 page reports `unchanged` (`fetch-refreshable` returned 0 entries against the fresh page).
- [x] On a deliberately-stale bill, `/zwiad-refresh` detects exactly one refreshable bill with the right per-bill subagent triggers and the leg-history spine re-derived. Persisted research is carried forward by `preserve_leg_history` via the `render-refreshed` path (unit-tested; not exercised end-to-end in UAT to avoid burning ~22 subagent dispatches).
- [x] IN→OUT classifier verdict sets `tracking: false`, prepends the flipped-out audit marker, keeps `topics` intact, never deletes the page. (Unit-tested in T8; not exercised in live UAT — this bill stayed IN-scope.)
- [x] `Enactment.statutes_at_large` populates for 118-hr-2670 and renders as a clickable link.
- [x] A JS-rendered `.senate.gov` page is now extractable via BeautifulSoup (verified live — 7957 chars extracted from wicker.senate.gov). Genuinely-absent quotes still rejected (precision held). Caveat: researcher-merged pseudo-quotes still drop, but that's a researcher/verifier-side issue, not a gate-extraction issue.
- [x] ruff + pyright (strict) + pytest all green (301 passing at T11; 0 errors).
- [x] DECISIONS.md carries D39 + D40.
- [x] v0.6.0 tagged.

## Decisions Made This Phase
- D39 — `/zwiad-refresh` re-classifies on every text-changed bill, narrowly overriding D9 for routine refresh. Justification + trade-offs in the spec §11.
- D40 — `LegHistory.narrative` persists to frontmatter alongside hearings/statements, extending D37's partial-persistence carve-out. Justification + trade-offs in the spec §11.
