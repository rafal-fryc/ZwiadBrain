# Phase 16 — Leg-History Source Breadth · Phase D (state bills via LegiScan)
Status: PENDING

> Part of the Legislative-History Source-Breadth milestone (PHASE-13 Phase A is DONE).
> Do not start without explicit user approval (one active phase at a time).
> Reuses the unchanged grounding gate, both subagents, the templates, and US-XX → states/xx/ routing.

## Goal
Extend legislative history to enacted STATE bills using LegiScan (there is no GovInfo for states): build a state spine from LegiScan data plus a governor signing message, run the same researcher → verifier → grounding-gate stack, and render. Live target: the already-tracked CA SB-53.

## Tasks
- [ ] LegiScan `_to_bill` (sources/legiscan.py): parse `votes` (roll calls: date/chamber/result/url) and `supplements` (fiscal notes, analyses, veto/signing docs) — both currently unparsed — TDD
- [ ] `assemble_state_spine` in leg_history.py (parallel to `assemble_spine`): versions ← texts; timeline/floor ← history→actions; votes ← new parse; enactment ← Chaptered (progress event 8) + state_link + signed date; supplements ← Tier-2 media leads + the governor-message Q source; narrative ← researcher — TDD
- [ ] `fetch-state-leg-history` CLI: branch on `--state`; `LegiScanSource(key, state).fetch(legiscan_bill_id)`; gate on enacted (Chaptered); stage `leghistory.json` with the state spine + leads — TDD
- [ ] `/zwiad-leg-history` command: branch federal (`congress/type/number` → `fetch-leg-history`) vs state (a state id → `fetch-state-leg-history`); state leads include the governor signing message (Tier-1 `signing`) and any state-legislature hearing video (Tier-2)
- [ ] Confirm `render-leg-history` + `page_path` route US-CA → states/ca/bills/ correctly for a state `LegHistory` (should need no change)
- [ ] Tests (TDD): votes/supplements parsing, assemble_state_spine, fetch-state-leg-history, state-bill render
- [ ] Live UAT: run on ca-2025-sb-53 (legiscan_bill_id 1904800) — Governor (Newsom) signing message, state votes/history, sponsor statements
- [ ] Decision log: state-spine design + governor-signing as a Tier-1 `signing` statement

## Acceptance Criteria
- An enacted state bill (SB-53) renders a legislative history: state spine (versions/timeline/votes/enactment) + grounded statements incl. the governor signing message, reusing the unchanged gate
- Jurisdiction routing writes wiki/states/ca/bills/ca-2025-sb-53.md correctly; `leg_history` round-trips through frontmatter
- Full gate green (pytest + ruff + pyright); UAT page reviewed

## Files to touch
- src/zwiadbrain/sources/legiscan.py · src/zwiadbrain/pipeline/leg_history.py · src/zwiadbrain/cli.py
- .claude/commands/zwiad-leg-history.md · (researcher/verifier prompts already state-capable from Phase A — adjust only if needed)
- tests/test_legiscan.py · tests/test_leg_history.py · tests/test_cli_leg_history.py

## Notes / Risks
- Enacted gate for state bills = Chaptered (LegiScan progress event 8), not a federal "Became Public Law" action.
- LegiScan text/data is CC BY 4.0 (D68/D69 context) — attribution applies to stored state content.
- Phase E (deferred): advisory fuzzy candidate-rescue to recover near-miss verbatim quotes (no gate change — surfaces the page's real span for verbatim re-copy); and CA leginfo deep integration (committee analyses / vote records). Open only on demonstrated need.

## Decisions Made This Phase
(append as you go)
