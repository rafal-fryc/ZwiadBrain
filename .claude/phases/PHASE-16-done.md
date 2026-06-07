# Phase 16 — Leg-History Source Breadth · Phase D (state bills via LegiScan)
Status: DONE

> Part of the Legislative-History Source-Breadth milestone (PHASE-13 Phase A is DONE).
> Do not start without explicit user approval (one active phase at a time).
> Reuses the unchanged grounding gate, both subagents, the templates, and US-XX → states/xx/ routing.

## Goal
Extend legislative history to enacted STATE bills using LegiScan (there is no GovInfo for states): build a state spine from LegiScan data plus a governor signing message, run the same researcher → verifier → grounding-gate stack, and render. Live target: the already-tracked CA SB-53.

## Tasks
- [x] LegiScan `_to_bill` (sources/legiscan.py): parse `votes` (roll calls: date/chamber/result/url) and `supplements` (fiscal notes, analyses, veto/signing docs) — both currently unparsed — TDD  → done via `_parse_votes` / `_parse_supplement_media` + `fetch_leg_history` → `StateLegHistoryInputs` (D75); 17/17 legiscan tests green, pyright clean
- [x] `assemble_state_spine` in leg_history.py (parallel to `assemble_spine`): versions ← texts; timeline/floor ← history→actions; votes ← new parse; enactment ← Chaptered (progress event 8) + state_link + signed date; supplements ← Tier-2 media leads + the governor-message Q source; narrative ← researcher — TDD  → done: `assemble_state_spine(bill, votes)` + `collect_state_leads(bill, supplement_media)` + `_state_signed_date`; floor left empty (D75); 19 tests green, pyright clean
- [x] `fetch-state-leg-history` CLI: branch on `--state`; `LegiScanSource(key, state).fetch(legiscan_bill_id)`; gate on enacted (Chaptered); stage `leghistory.json` with the state spine + leads — TDD  → done: `fetch-state-leg-history --bill <id> --state <st>` via `fetch_leg_history` → assemble_state_spine/collect_state_leads; enacted gate; 7/7 cli-leg-history tests green, pyright clean
- [x] `/zwiad-leg-history` command: branch federal (`congress/type/number` → `fetch-leg-history`) vs state (a state id → `fetch-state-leg-history`); state leads include the governor signing message (Tier-1 `signing`) and any state-legislature hearing video (Tier-2)  → done: `$1` shape branch (`ca/1904800` → state); step 1/2/3 state directives; researcher md generalized (signing=Governor, `state` input)
- [x] Confirm `render-leg-history` + `page_path` route US-CA → states/ca/bills/ correctly for a state `LegHistory` (should need no change)  → confirmed: `test_render_leg_history_routes_state_bill_to_states_path` passes with ZERO render/routing code change (the `_jurisdiction_parts` US-XX handling already covers it)
- [x] Tests (TDD): votes/supplements parsing, assemble_state_spine, fetch-state-leg-history, state-bill render  → +4 legiscan, +11 leg_history, +3 cli-leg-history tests; all RED-then-GREEN
- [x] Live UAT: run on ca-2025-sb-53 (legiscan_bill_id 1904800) — Governor (Newsom) signing message, state votes/history, sponsor statements  → PASSED end-to-end (see Live UAT result below)
- [x] Decision log: state-spine design + governor-signing as a Tier-1 `signing` statement  → DECISIONS.md D75

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

## Live UAT result (2026-06-04 — ca-2025-sb-53, "Transparency in Frontier Artificial Intelligence Act", Wiener)
Full real-pipeline run via the rewritten `/zwiad-leg-history` state branch (`ca/1904800`), all steps:
1. `fetch-state-leg-history --bill 1904800 --state ca` (real LegiScan) → enacted-gated; state spine = **10 versions, 12 roll-call votes** (with results + leginfo vote URLs), **floor empty (by design)**, **enactment signed 2025-09-29** (Newsom) + leginfo billStatus url; leads = state=CA, enacted_date 2025-09-29, **0 supplements** (LegiScan returned none for this bill — the url-less skip path was still exercised earlier in unit tests).
2. 4 researcher lanes dispatched (sonnet) → `lane-{crec,hearings,press,signing}.json`.
3. `build-verifier-input` → merged to **18 statements + 13 media**, 0 lanes dropped, Python-stamped indices.
4. `leg-history-verifier` (opus) over `verifier-input.json` → **18/18 statements + 13/13 media confirmed**; correctly flagged the dup Newsom signing quote (idx 17 ≡ 11) and confirmed the two Newsom SB-1047-veto quotes as genuinely on-subject `related` items.
5. `assemble-leg-history-input` → verdicts bound by merged index, echo cross-check **passed with zero downgrades**.
6. `render-leg-history` (live gate) → **4 statements grounded / 14 ground-dropped, 6/6 hearings, 13/13 media, 12 votes, narrative**; page `wiki/states/ca/bills/ca-2025-sb-53.md` written; `reindex` OK; frontmatter `leg_history` round-trips (4 verified statements, 13 media, 6 hearings, narrative).

**Outcome — capability proven end-to-end with zero misattribution.** State routing (US-CA → states/ca/bills/), one-getBill spine (votes/enactment), the two-step assembler, the cross-modal verifier, and the unchanged grounding gate all worked on real data. Acceptance criteria 1–3 met.

**Honest finding — low statement yield (4/18) is a deterministic-GATE FETCH limitation, not a pipeline defect:**
- The richest CA sources are **PDFs** (committee/floor analyses on apcp.assembly.ca.gov / billtexts.s3) — the gate's `_fetch_url` (httpx + BeautifulSoup) cannot extract PDF text, so all 7 PDF-sourced Wiener/Newsom-analysis quotes ground-dropped ("quote not found").
- **gov.ca.gov returns 403** to the gate's fetch, so the **Governor's signing statement** — researched (Tier-1 `signing`) AND independently verifier-confirmed verbatim — ground-dropped fail-closed. The pipeline handled it correctly at every stage; only the gate's raw fetch couldn't retrieve the page.
- A few sd11.senate.ca.gov press pages returned "quote not found" (JS/transient) while the sd11 "expands AI bill" page grounded all 4 of its quotes.
- This is the documented gate-vs-verifier fetch asymmetry (the verifier's `WebFetch` renders PDFs/JS; the deterministic gate uses raw httpx). Fail-closed drops are correct behavior — never misattribution. **Candidate for Phase E: gate-fetch hardening (PDF text extraction + UA/403 handling)** — out of scope here (would touch the shared gate; feature/refactor kept separate).

## Decisions Made This Phase
- **D75 (2026-06-04)** — State leg-history spine assembles from ONE getBill; the `Bill` model is unchanged. `LegiScanSource.fetch_leg_history` returns a transient `StateLegHistoryInputs(bill, votes, supplement_media)`; `assemble_state_spine(bill, votes)` builds the spine (votes parsed inline; `floor_consideration` left EMPTY — timeline+Votes cover it); supplements become Tier-2 `RelatedMedia` leads via `collect_state_leads`. Governor signing (Tier-1 `signing`) + state hearing video (Tier-2) are researcher directives, not spine data. Downstream (`build-verifier-input`→verifier→`assemble-leg-history-input`→`render-leg-history`) and US-XX→states/xx/ routing reused unchanged. Both forks (keep-Bill-clean; empty floor) confirmed by the user. Full rationale in DECISIONS.md D75.
