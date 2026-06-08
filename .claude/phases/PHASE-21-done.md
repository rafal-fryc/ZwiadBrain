# Phase 21 — CA committee analyses → spine committee_reports (via LegiScan)
Status: DONE

> Phase E continuation. D75 left state `committee_reports` empty. Scope locked to
> committee analyses only (operator). Investigation changed the SOURCE from the
> originally-planned leginfo HTML scrape to the LegiScan supplements already fetched.

## Goal
Give enacted CA state bills a real "Committee Reports / Analyses" section by surfacing
their committee/floor analyses deterministically — without a brittle leginfo scrape.

## Approach change — RESOLVED (operator, 2026-06-07)
Read-before-touch revealed CA committee analyses ALREADY arrive in every `getBill` as
supplements (`type:"Analysis"`, `type_id` 2) whose `state_link` IS the leginfo analysis URL.
So they are promoted from the stable LegiScan API — NO leginfo HTML scraping, NO new network
call. Logged as D80. (The fuller leginfo scope — roll-call votes, chapter citation — stays
deferred.)

## What shipped
- `legiscan._supplement_is_analysis` (`type_id == 2`, fallback to `type` "Analysis") +
  `_parse_committee_analyses` -> `list[CommitteeReport]` (`citation`=title, `url`=state_link/
  leginfo then the LegiScan mirror; url-less skipped).
- `_parse_supplement_media` now EXCLUDES analyses (no double-listing as Tier-2 leads).
- `StateLegHistoryInputs.committee_analyses`; populated in `fetch_leg_history`.
- `assemble_state_spine(bill, votes, committee_reports=None)` -> sets spine `committee_reports`.
- CLI `fetch-state-leg-history` threads `inputs.committee_analyses` into the spine.

## Tasks
- [x] LegiScan adapter: identify + map Analysis supplements to `CommitteeReport`
- [x] Promote to spine `committee_reports`; exclude from Tier-2 `supplement_media`
- [x] Thread through `StateLegHistoryInputs` -> `assemble_state_spine` -> CLI staged JSON
- [x] TDD with recorded `getBill_leghistory.json` fixture (no live network in unit tests)
- [~] Live UAT on a real CA bill — DEFERRED: needs a LegiScan key + network. The end-to-end
      staged-JSON CLI test proves the thread-through; the committee_reports render path is the
      same shared field/template federal bills already use.
- [x] Decision log entry (D80)

## Acceptance Criteria
- [x] A CA bill's `Analysis` supplements appear in `spine.committee_reports`, not Tier-2 media
- [x] Fiscal notes / misc / url-less supplements are NOT promoted
- [x] All new logic deterministic and fixture-tested; no new network calls
- [x] Full gate green: pytest 775 (+4), ruff clean, pyright at the unchanged 20-baseline

## Notes
- Gate logic (`ground_items`/`ground_related`/`_normalize_text`/`_page_text`) untouched; this
  phase only changed state-spine assembly + the LegiScan supplement mapping.
- Updated the existing `test_fetch_state_leg_history_stages_state_spine_and_leads` to the new
  spec (supplement_media 2->1; committee_reports now carries "Assembly Floor Analysis") — an
  intentional behavior change, not a make-it-pass edit.

## Decisions Made This Phase
- **D80 (2026-06-07)** — CA committee analyses promoted from LegiScan supplements (type_id 2)
  to spine committee_reports; no leginfo scrape. Full rationale in DECISIONS.md D80.
