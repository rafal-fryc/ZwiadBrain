# Phase 14 — Leg-History Source Breadth · Phase B (Related Media + video transcripts)
Status: DONE

> Part of the Legislative-History Source-Breadth milestone (PHASE-13 Phase A is DONE).
> Do not start without explicit user approval (one active phase at a time).
> Builds on D69/D70/D71. The D36/D43 grounding gate stays unchanged byte-for-byte.

## Goal
Add a Tier-2 `RelatedMedia` model so hearing videos / reference links persist as labeled media (no attributed quote), and add a transcript path so a spoken quote can become a Tier-1 verified statement only when an official transcript — or `youtube-transcript-api` captions — carries the verbatim words.

## Tasks
- [x] Add `RelatedMedia` model (title, url, kind: video|page|other, publisher, date, relation, note) and `LegHistory.related_media: list[RelatedMedia]` (models.py) — TDD
- [x] Tier-2 grounding `ground_related` (leg_history.py): URL-200 + verifier identity/relevance confirmation; never carries a quote — TDD (new `RelatedGroundingResult`; `DroppedItem.kind` widened to include `"media"`)
- [x] Render a "Related Media" block (templates.py `_leg_history`) — implemented as its own `### Related Media` section right AFTER "Related (Subject Matter)" (so the "not about this bill" caveat never mislabels an on-bill video); omit when empty — TDD
- [x] Persist `related_media` to frontmatter (schema.py); carry it across refresh in `preserve_leg_history` (refresh.py) — TDD
- [x] Transcript helper (sources/transcripts.py): `youtube_video_id` + `fetch_captions` (DI, fail-closed) + `make_gate_fetch` wrapper. Wired into render-leg-history so a YouTube `source_url` resolves to caption text; the gate is unchanged (only the `fetch` arg changes) — TDD
- [x] `youtube-transcript-api` added as a **locked** dependency (`>=1.2,<2`) — dry-run resolves clean (no typer downgrade) and passes `pyright --strict` (typed), so the D68 optional fallback is NOT triggered (D73)
- [x] Researcher prompt: emit hearing videos as `related_media`; emit a video quote only when a transcript/captions ground it
- [x] Verifier prompt: Tier-2 identity check for `related_media` (+ object output with `statements`/`related_media` arrays)
- [x] Decision log: D72 (RelatedMedia + transcript-preference/caption-fallback) + D73 (youtube-transcript-api locked)
- [x] CLI render-leg-history wiring + orchestrator command (`zwiad-leg-history.md`) updated end-to-end (not in original file list, but required for the pipeline to produce media)

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
- **D72** — `RelatedMedia` is a first-class Tier-2 model (no quote, separate `ground_related` gate = URL-200 + verifier identity), own `### Related Media` render section, persisted + refresh-carried; spoken quotes ground via transcript-preferred / YouTube-caption-fallback with the D36 gate byte-for-byte unchanged (only the `fetch` callable changes).
- **D73** — `youtube-transcript-api` is locked (`>=1.2,<2`), not optional like Docling: it resolves clean (no typer<0.22 conflict) and is typed (passes `pyright --strict`). Helper still lazy-imports + fails closed so a stripped env degrades to Tier-2 media.
- Renderer placement deviation: the phase said "within/beside" the Related (Subject Matter) section; implemented as a sibling `### Related Media` section immediately after it, so the subject-matter caveat is never wrongly applied to an `on_bill` video. Anti-misleading goal met.
- Scope addition (flagged): the render-leg-history CLI wiring and the `zwiad-leg-history` orchestrator command were updated (staging gains `related_media` + `media_verdicts`; verifier output becomes an object) — not in the original "Files to touch" list, but required for the feature to work end-to-end.

## Gate status
- Offline gate GREEN: pytest **699 passed**, ruff clean, `pyright --strict` 0 errors.
- Invariant verified by `git diff`: `ground_items` + `_normalize_text` byte-for-byte unchanged (only `DroppedItem.kind` widened); the cli.py statement echo cross-check unchanged (only `fetch=_fetch_url` → `fetch=gate_fetch`).
- **Live UAT on 118/hr/2670: WAIVED by operator (2026-06-02).** The acceptance criterion (≥1 hearing video renders as Related Media via the real pipeline) was NOT exercised this phase; the phase is closed on the offline gate at the operator's explicit direction to move to the next phase. Outstanding validation: the researcher actually emitting `related_media` and a live video rendering on the real page. Runbook when revisited: `/zwiad-leg-history 118/hr/2670`.
