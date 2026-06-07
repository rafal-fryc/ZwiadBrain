# Phase 13 — Legislative-History Source Breadth (Phase A: Federal)
Status: DONE

## Goal
Broaden federal legislative-history coverage (signing statements, sponsors' past/subject-matter statements, hearing/video references) and split the page into "On This Bill" vs "Related (Subject Matter)" — without changing the D36 grounding gate.

## Tasks
- [x] models.py: add `"signing"` to `Statement.source_type`; add `relation: Literal["on_bill","related"] = "on_bill"` to `Statement` and `Hearing` (TDD)
- [x] templates.py `_leg_history`: on-bill items in existing sections; `related` items under a new "Related (Subject Matter)" section (TDD)
- [x] leg_history.py `ground_items` + cli.py `render-leg-history`: `relation` rides through `model_copy` unchanged — NO code change needed, gate untouched (verified by diff)
- [x] `.claude/agents/leg-history-researcher.md`: lane-aware (crec|hearings|press|signing); signing statements; sponsor past/subject-matter; hearing video links; `relation` tag; D70 sponsor/official clamp
- [x] `.claude/agents/leg-history-verifier.md`: add `on_subject` check for `related` items (folds into `verified` fail-closed); echo fields unchanged
- [x] `.claude/commands/zwiad-leg-history.md`: fan-out researcher per lane; merge in fixed order; single verifier pass with subject context (preserve index↔verdict contract); assemble + render
- [x] DECISIONS.md: D69 (tiered model), D70 (sponsor/official clamp), D71 (fan-out)
- [x] Full gate: pytest (656) + ruff + pyright green; `leg_history.py` shows no diff
- [x] Live UAT on 118/hr/2670: 4 lanes → 29 raw → 27 merged statements + 13 hearings → verifier (27/27) → gate grounded **18 statements** (incl. 4 Biden signing statements) + **13 hearings** (incl. YouTube markup videos), dropped 9 fail-closed (4× altoday 403, 5× rollcall/defensenews/senate paywall "quote not found"); "Related (Subject Matter)" section populated with 4 related defense hearings. Baseline was 9 statements / 0 hearings.

## Deviation note
The approved plan said "split the Statements/Hearings into 'On This Bill' and 'Related (Subject Matter)' subsections." Implemented as: on-bill items stay in the existing sections (implicitly "this bill's record") and a single labeled **"Related (Subject Matter)"** section gathers related statements + hearings. This keeps on-bill-only pages byte-identical to before and adds the labeled section only when related items exist — the anti-misleading goal is met by the explicit "Related" label.

## Acceptance Criteria
- Rendered leg-history page shows "On This Bill" and "Related (Subject Matter)" subsections; empty ones omitted
- `ground_items` gate logic, `_normalize_text`, and the echo cross-check are byte-for-byte unchanged (verified by diff)
- New unit tests (signing source_type, relation round-trip, renderer split) pass; full suite + ruff + pyright green
- Every persisted statement — on-bill or related — still passed the unchanged verbatim gate

## Decisions Made This Phase
- D69 — tiered trust model (Tier-1 quote / Tier-2 media) + on-bill/related page split; D36 gate unchanged.
- D70 — `related` items bounded by the sponsor/official relevance clamp, enforced via the verifier's `on_subject` → `verified`.
- D71 — research fans out by source lane (single lane-aware researcher, dispatched per lane; only `crec` writes the narrative).
- Relation rides through the pipeline via Pydantic `model_copy` defaults — no change to `ground_items`/`render-leg-history` needed (gate preserved byte-for-byte).
