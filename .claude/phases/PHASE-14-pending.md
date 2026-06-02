# Phase 14 — Leg-History Source Breadth · Phase B (Related Media + video transcripts)
Status: PENDING

> Part of the Legislative-History Source-Breadth milestone (PHASE-13 Phase A is DONE).
> Do not start without explicit user approval (one active phase at a time).
> Builds on D69/D70/D71. The D36/D43 grounding gate stays unchanged byte-for-byte.

## Goal
Add a Tier-2 `RelatedMedia` model so hearing videos / reference links persist as labeled media (no attributed quote), and add a transcript path so a spoken quote can become a Tier-1 verified statement only when an official transcript — or `youtube-transcript-api` captions — carries the verbatim words.

## Tasks
- [ ] Add `RelatedMedia` model (title, url, kind: video|page|other, publisher, date, relation, note) and `LegHistory.related_media: list[RelatedMedia]` (models.py) — TDD
- [ ] Tier-2 grounding `ground_related` (leg_history.py): URL-200 + verifier identity/relevance confirmation; never carries a quote — TDD
- [ ] Render a "Related Media" block (templates.py `_leg_history`), within/beside the "Related (Subject Matter)" section; omit when empty — TDD
- [ ] Persist `related_media` to frontmatter; carry it across refresh in `preserve_leg_history` (refresh.py) — TDD
- [ ] Transcript helper: prefer an official transcript URL; fall back to captions via `youtube-transcript-api`. A video-derived `Statement.source_url` points at the transcript/caption text the existing gate fetches + verbatim-matches (gate unchanged) — TDD
- [ ] Add `youtube-transcript-api` as a locked dependency — verify it carries no heavy/conflicting pins (avoid the typer<0.22 trap, D68); if it conflicts, treat it as an optional operator-installed extra like Docling
- [ ] Researcher prompt: emit a video quote only when a transcript/captions ground it; otherwise emit the video as `RelatedMedia`
- [ ] Verifier prompt: Tier-2 identity check ("is this the claimed hearing video / page") for `RelatedMedia`
- [ ] Decision log: RelatedMedia design + the transcript-preference/caption-fallback rule

## Acceptance Criteria
- Hearing videos render as Related Media; a spoken quote persists only when a transcript/captions verbatim-confirm it (auto-captions usually fail → fail-closed, by design)
- `ground_items`/`_normalize_text`/echo cross-check unchanged byte-for-byte; `related_media` survives a refresh
- Full gate green (pytest + ruff + pyright); live UAT re-run on 118/hr/2670 shows at least one hearing video as Related Media

## Files to touch
- src/zwiadbrain/models.py · src/zwiadbrain/pipeline/leg_history.py · src/zwiadbrain/wiki/templates.py · src/zwiadbrain/pipeline/refresh.py
- new transcript helper (e.g. src/zwiadbrain/sources/transcripts.py) · pyproject.toml (youtube-transcript-api)
- .claude/agents/leg-history-researcher.md · .claude/agents/leg-history-verifier.md
- tests/test_models.py · tests/test_render.py · tests/test_leg_history.py · tests/test_refresh.py

## Notes / Risks
- Auto-captions are not verbatim (no punctuation/casing) → they will usually fail the strict gate; this is expected fail-closed behavior, not a bug. Prefer official transcripts.
- `youtube-transcript-api` availability/ToS and missing-caption cases must degrade to Tier-2 media (no quote).

## Decisions Made This Phase
(append as you go)
